import requests
import time
import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from django.conf import settings # Para caminhos de arquivos, se necessário

# --- Importações de Visão Computacional ---
# Certifique-se de que 'opencv-contrib-python' e 'ultralytics' estão instalados.
try:
    import cv2
    from ultralytics import YOLO
    
    # Adicionar o caminho onde o Django pode encontrar 'trainer.yml' e 'haarcascade_frontalface_default.xml'
    BASE_DIR = settings.BASE_DIR 
except ImportError:
    print("AVISO: Bibliotecas de Visão Computacional (cv2/YOLO) não encontradas.")
    cv2, YOLO = None, None
# ------------------------------------------

# Importações dos seus Models e Serializers (Assumindo que estão corretas)
from .models import User, Environment, Log 
from .serializers import UserSerializer, EnvironmentSerializer, LogSerializer

# ================= CONFIGURAÇÕES DE ACESSO E HARDWARE =================
ESP32_IP = "http://192.168.4.1" # IP do LoRa32 AP
AUTHORIZED_NAME = "Israel"
# RFID de Israel (ajuste conforme o banco de dados)
AUTHORIZED_RFID = "6C3ACB33" 
# Limiar de confiança para LBPH. Abaixo deste valor, o reconhecimento é aceito.
CONFIDENCE_THRESHOLD = 80 
# O ID que você atribuiu ao rosto de Israel durante o treinamento LBPH
ISRAEL_FACE_ID = 1 

# ================= Inicialização dos Modelos de Visão Computacional =================
# ATENÇÃO: Inicialização fora da view para evitar recarregamento, 
# mas PODE bloquear o servidor web.

yolo_model = None
recognizer = None
face_cascade = None
cap = None

if cv2 and YOLO:
    try:
        # Tenta carregar os modelos
        yolo_model = YOLO("yolov8n.pt")
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        
        # Caminho para o trainer.yml e o haarcascade (ajuste o caminho se necessário)
        recognizer_path = "trainer.yml" # Assumindo que está na raiz do projeto ou em um caminho acessível
        haarcascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        
        if os.path.exists(recognizer_path):
             recognizer.read(recognizer_path)
        else:
            Log.objects.create(event=f"ERRO: Arquivo trainer.yml não encontrado em {recognizer_path}")

        face_cascade = cv2.CascadeClassifier(haarcascade_path)

        # Inicializa a Câmera
        cap = cv2.VideoCapture(0) 
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        if not cap.isOpened():
             Log.objects.create(event="ERRO: Câmera (cv2.VideoCapture(0)) não abriu.")
             cap = None
             
        Log.objects.create(event="Modelos de Visão Computacional inicializados com sucesso.")

    except Exception as e:
        Log.objects.create(event=f"ERRO CRÍTICO ao carregar modelos CV: {e}")
        yolo_model, recognizer, face_cascade, cap = None, None, None, None
        
# ================= Helpers =================

def send_led_white(status):
    """Envia comando para ligar/desligar LED branco (presença) no ESP32."""
    try:
        # A URL no script original era /led_presenca, estou mantendo a convenção do segundo código
        requests.post(f"{ESP32_IP}/led_branco", params={"status": status}, timeout=1) 
    except Exception as e:
        Log.objects.create(event=f"Error sending white LED {status}: {e}")

def send_led_blue(status):
    """Envia comando para ligar/desligar LED azul no ESP32."""
    try:
        requests.post(f"{ESP32_IP}/led_azul", params={"status": status}, timeout=1)
    except Exception as e:
        Log.objects.create(event=f"Error sending blue LED {status}: {e}")

def send_rfid_result(result, nome=""):
    """Envia o resultado do acesso (permitido/negado) para o ESP32."""
    try:
        # No script original, há led_acesso_libera e led_acesso_negada. 
        # Adaptando para a função send_rfid_result com a mensagem.
        msg = f"{result}_{nome}" if nome else result
        requests.post(f"{ESP32_IP}/rfid_result", params={"resultado": msg}, timeout=1)
    except Exception as e:
        Log.objects.create(event=f"Error sending RFID result {result}: {e}")

def get_esp32_status():
    """Retorna status do ambiente (temperatura, umidade, etc.) do ESP32."""
    try:
        resp = requests.get(f"{ESP32_IP}/status", timeout=2)
        return resp.json()
    except Exception as e:
        Log.objects.create(event=f"Error fetching ESP32 status: {e}")
        return None

def get_esp32_last_rfid():
    """Retorna o último RFID lido pelo ESP32."""
    try:
        resp = requests.get(f"{ESP32_IP}/status_rfid", timeout=2)
        return resp.json().get("ultimo_rfid", "")
    except Exception as e:
        Log.objects.create(event=f"Error fetching last RFID: {e}")
        return None

# ================= VIEWS GENÉRICAS (MANTIDAS) =================

class EnvironmentView(APIView):
    # ... (manter o código da EnvironmentView)
    renderer_classes = [JSONRenderer]
    def get(self, request):
        env = Environment.objects.first() or Environment.objects.create()
        status_esp = get_esp32_status()
        if status_esp:
            env.temperature = status_esp.get("temperatura", env.temperature)
            env.humidity = status_esp.get("umidade", env.humidity)
            env.last_rfid = status_esp.get("ultimo_rfid", env.last_rfid)
            env.save()
        serializer = EnvironmentSerializer(env)
        return Response(serializer.data)

class PresenceLEDView(APIView):
    # ... (manter o código da PresenceLEDView)
    renderer_classes = [JSONRenderer]
    def patch(self, request):
        env = Environment.objects.first() or Environment.objects.create()
        status_led = request.data.get("status", "off")
        if status_led == "on":
            env.light_white = True
            send_led_white("on")
        else:
            env.light_white = False
            send_led_white("off")
        env.save()
        Log.objects.create(event=f"LED Branco set to {status_led}")
        return Response({"light_white": env.light_white})

class BlueLEDView(APIView):
    # ... (manter o código da BlueLEDView)
    renderer_classes = [JSONRenderer]
    def patch(self, request):
        env = Environment.objects.first() or Environment.objects.create()
        status_led = request.data.get("status", "off")
        if status_led == "on":
            env.light_blue = True
            send_led_blue("on")
        else:
            env.light_blue = False
            send_led_blue("off")
        env.save()
        Log.objects.create(event=f"LED Azul set to {status_led}")
        return Response({"light_blue": env.light_blue})

class GreenRedLEDView(APIView):
    # ... (manter o código da GreenRedLEDView)
    renderer_classes = [JSONRenderer]
    def patch(self, request):
        env = Environment.objects.first() or Environment.objects.create()
        status_green = request.data.get("green", False)
        status_red = request.data.get("red", False)

        env.light_green = status_green
        env.light_red = status_red
        env.save()

        if status_green:
            send_rfid_result("permitido")
        elif status_red:
            send_rfid_result("negado")

        Log.objects.create(event=f"LED Green={status_green}, Red={status_red}")
        return Response({"light_green": env.light_green, "light_red": env.light_red})

# ================= VIEW PRINCIPAL DE ACESSO (ADAPTADA) =================

class AccessControlView(APIView):
    """
    POST: Recebe RFID lido pelo ESP32, verifica no banco de dados, 
    executa a Visão Computacional para confirmar a identidade de Israel, 
    e envia o resultado para o ESP32.
    """
    renderer_classes = [JSONRenderer]

    def post(self, request):
        # 1. Obter e Limpar o RFID
        rfid_code = request.data.get("rfid", "").replace(" ", "").upper()
        
        env = Environment.objects.first() or Environment.objects.create()
        env.last_rfid = rfid_code # Salva o último RFID lido
        env.save()
        Log.objects.create(event=f"RFID recebido para validação: {rfid_code}")

        # 2. Validação Simples do Usuário no Banco de Dados
        user = User.objects.filter(rfid=rfid_code).first()
        
        if not user or user.name != AUTHORIZED_NAME or rfid_code != AUTHORIZED_RFID:
            # Caso 1: Usuário/RFID não é o Israel esperado
            send_rfid_result("negado", "Desconhecido")
            env.light_green = False
            env.light_red = True
            env.save()
            Log.objects.create(event=f"Acesso NEGADO: RFID/Usuário inválido: {rfid_code}")
            return Response({"authorized": False, "message": "RFID não autorizado ou não correspondente a Israel."}, status=403)
            
        # 3. Execução da Visão Computacional (Verificação de Presença e Identidade)
        israel_presente = False
        
        if cap and cap.isOpened() and yolo_model and recognizer and face_cascade:
            # Tenta ler um frame da câmera
            ret, frame = cap.read()
            if not ret:
                Log.objects.create(event="Erro ao ler frame da câmera.")
                # Nega acesso se a câmera falhar
                send_rfid_result("negado", "Erro Cam")
                return Response({"authorized": False, "message": "Erro na câmera, acesso negado por segurança."}, status=503)

            # Executa YOLO para DETECTAR pessoas (classe 0)
            results = yolo_model(frame, verbose=False)
            
            for result in results:
                # O código original só precisa de um loop de detecção, não o loop de visualização
                for box in result.boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    
                    if cls == 0 and conf > 0.5:  # Se detectou uma pessoa
                        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                        person_crop = frame[y1:y2, x1:x2]

                        # Executa Reconhecimento Facial (LBPH) na área da pessoa
                        gray_crop = cv2.cvtColor(person_crop, cv2.COLOR_BGR2GRAY)
                        faces = face_cascade.detectMultiScale(gray_crop, 1.1, 5)
                        
                        for (fx, fy, fw, fh) in faces:
                            face_roi = gray_crop[fy:fy+fh, fx:fx+fw]
                            label, confidence = recognizer.predict(face_roi)
                            
                            # Se a confiança for alta e a identificação bater com Israel
                            if confidence < CONFIDENCE_THRESHOLD and label == ISRAEL_FACE_ID: 
                                israel_presente = True
                                break # Encontrou Israel, pode parar
                if israel_presente:
                    break
        else:
             Log.objects.create(event="Modelos de Visão Computacional indisponíveis.")
             send_rfid_result("negado", "Svc Indisp")
             return Response({"authorized": False, "message": "Serviço de Visão Computacional indisponível."}, status=503)

        # 4. Resultado Final da Validação
        if israel_presente:
            # Acesso Permitido: RFID Israel OK + Rosto Israel presente e confirmado
            send_rfid_result("permitido", AUTHORIZED_NAME)
            env.light_green = True
            env.light_red = False
            env.save()
            Log.objects.create(event=f"Acesso PERMITIDO: {AUTHORIZED_NAME} (RFID e Rosto confirmados)")
            return Response({"authorized": True, "message": f"Acesso liberado para {AUTHORIZED_NAME}."}, status=200)
        else:
            # Acesso Negado: RFID Israel OK, mas Rosto Israel não detectado/reconhecido
            send_rfid_result("negado", AUTHORIZED_NAME)
            env.light_green = False
            env.light_red = True
            env.save()
            Log.objects.create(event=f"Acesso NEGADO: RFID OK, mas rosto de {AUTHORIZED_NAME} não confirmado.")
            return Response({"authorized": False, "message": "RFID OK, mas o rosto de Israel não foi confirmado."}, status=403)

# ================= OUTRAS VIEWS =================

# Mantendo as views restantes para completude:
class RFIDValidationView(APIView):
    # Esta view foi substituída pela AccessControlView, mas é mantida aqui por segurança.
    renderer_classes = [JSONRenderer]

    def post(self, request):
        rfid_code = request.data.get("rfid")
        env = Environment.objects.first() or Environment.objects.create()
        env.last_rfid = rfid_code
        env.save()

        user = User.objects.filter(rfid=rfid_code).first()
        if user and user.name in env.detected_people: # 'detected_people' deve ser ajustado para usar a lógica de Visão Computacional
            # Esta lógica está incompleta sem a Visão Computacional, use AccessControlView
            send_rfid_result("permitido")
            env.light_green = True
            env.light_red = False
            env.save()
            Log.objects.create(event=f"Access PERMITTED: {user.name}")
            return Response({"authorized": True, "message": f"Access granted to {user.name}"})
        else:
            send_rfid_result("negado")
            env.light_green = False
            env.light_red = True
            env.save()
            Log.objects.create(event=f"Access DENIED: {rfid_code}")
            return Response({"authorized": False, "message": "Access denied"})

class LastRFIDView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        last_rfid = get_esp32_last_rfid()
        return Response({"last_rfid": last_rfid})

class UsersView(APIView):
    renderer_classes = [JSONRenderer]

    def get(self, request):
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)