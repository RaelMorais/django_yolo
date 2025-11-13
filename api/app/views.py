
import os
import requests

from django.conf import settings
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer

from .models import Environment, Log
from .serializers import EnvironmentSerializer

ESP32_IP = "http://192.168.4.1"     
CONFIDENCE_THRESHOLD = 80           

cv2 = None
YOLO = None
yolo_model = None
recognizer = None
face_cascade = None
cap = None

def init_cv_if_needed():

    global cv2, YOLO, yolo_model, recognizer, face_cascade, cap

    if yolo_model is not None and recognizer is not None and face_cascade is not None and cap is not None:
        return

    try:
        import cv2 as _cv2
        from ultralytics import YOLO as _YOLO

        cv2 = _cv2
        YOLO = _YOLO

        BASE_DIR = settings.BASE_DIR

        yolov8_path = os.path.join(BASE_DIR, "yolov8n.pt")
        if not os.path.exists(yolov8_path):
            Log.objects.create(event=f"ERRO: yolov8n.pt não encontrado em {yolov8_path}")
            return

        yolo_model = YOLO(yolov8_path)

        recognizer_path = os.path.join(BASE_DIR, "trainer.yml")
        recognizer_local = cv2.face.LBPHFaceRecognizer_create()

        if os.path.exists(recognizer_path):
            recognizer_local.read(recognizer_path)
        else:
            Log.objects.create(
                event=f"ERRO: Arquivo trainer.yml não encontrado em {recognizer_path}"
            )
            return

        haarcascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade_local = cv2.CascadeClassifier(haarcascade_path)

        cap_local = cv2.VideoCapture(0, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(0)
        cap_local.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap_local.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not cap_local.isOpened():
            Log.objects.create(event="ERRO: Câmera (cv2.VideoCapture(0)) não abriu.")
            return

        recognizer = recognizer_local
        face_cascade = face_cascade_local
        cap = cap_local

        Log.objects.create(event="Modelos de Visão Computacional inicializados com sucesso.")

    except Exception as e:
        Log.objects.create(event=f"ERRO CRÍTICO ao carregar modelos CV: {e}")
        yolo_model, recognizer, face_cascade, cap = None, None, None, None


def send_presence(has_people: bool):
    """
    Envia para o ESP32 se tem presença ou não.
    ESP32 expõe /presenca?tem_presenca=yes|no
    """
    try:
        status_str = "yes" if has_people else "no"
        requests.post(
            f"{ESP32_IP}/presenca",
            params={"tem_presenca": status_str},
            timeout=1
        )
        Log.objects.create(
            event=f"send_presence: enviado tem_presenca={status_str} para ESP32"
        )
    except Exception as e:
        Log.objects.create(
            event=f"ERRO em send_presence: {e}"
        )

class PeopleDetectionView(APIView):
    renderer_classes = [JSONRenderer]

    def post(self, request):
        env = Environment.objects.first() or Environment.objects.create()

        temperatura = request.data.get("temperatura")
        umidade = request.data.get("umidade")
        ultimo_rfid = request.data.get("ultimo_rfid", "")

        Log.objects.create(
            event=f"PeopleDetectionView: dados recebidos da ESP32: "
                  f"T={temperatura}, U={umidade}, RFID={ultimo_rfid}"
        )

        if temperatura is not None:
            try:
                env.temperature = float(temperatura)
            except (TypeError, ValueError):
                Log.objects.create(event=f"PeopleDetectionView: temperatura inválida recebida: {temperatura}")

        if umidade is not None:
            try:
                env.humidity = float(umidade)
            except (TypeError, ValueError):
                Log.objects.create(event=f"PeopleDetectionView: umidade inválida recebida: {umidade}")

        if ultimo_rfid:
            env.last_rfid = str(ultimo_rfid)

        init_cv_if_needed()

        if not (cap and cap.isOpened() and yolo_model and face_cascade and recognizer):
            Log.objects.create(event="PeopleDetectionView: modelos/camera indisponíveis após init.")
            env.last_update = timezone.now()
            env.save()
            return Response(
                {"detail": "Serviço de visão computacional indisponível."},
                status=503
            )

        ret, frame = cap.read()
        if not ret:
            Log.objects.create(event="PeopleDetectionView: falha ao ler frame da câmera.")
            env.last_update = timezone.now()
            env.save()
            return Response(
                {"detail": "Erro ao acessar a câmera."},
                status=503
            )

        people_boxes = []
        try:
            results = yolo_model(frame, verbose=False)
            for result in results:
                for box in result.boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    if cls == 0 and conf > 0.5:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                        people_boxes.append((x1, y1, x2, y2))
        except Exception as e:
            Log.objects.create(event=f"PeopleDetectionView: erro YOLO: {e}")
            env.last_update = timezone.now()
            env.save()
            return Response(
                {"detail": "Erro ao rodar YOLO."},
                status=500
            )

        people_count = len(people_boxes)
        has_people = people_count > 0

        detected_names = []
        try:
            if people_count > 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                for (x1, y1, x2, y2) in people_boxes:
                    person_crop = gray[y1:y2, x1:x2]
                    faces = face_cascade.detectMultiScale(person_crop, 1.1, 5)

                    if len(faces) == 0:
                        detected_names.append("Desconhecido")
                        continue

                    (fx, fy, fw, fh) = faces[0]
                    face_roi = person_crop[fy:fy+fh, fx:fx+fw]

                    label, confidence = recognizer.predict(face_roi)

                    if confidence < CONFIDENCE_THRESHOLD:
                        detected_names.append(f"ID_{label}")
                    else:
                        detected_names.append("Desconhecido")
            else:
                detected_names = []
        except Exception as e:
            Log.objects.create(event=f"PeopleDetectionView: erro no reconhecimento facial: {e}")
            detected_names = ["Pessoa"] * people_count

        env.detected_people = detected_names
        env.people_count = people_count
        env.has_presence = has_people
        env.last_update = timezone.now()
        env.save()

        # ---------- 7) Avisar ESP32 se tem presença ----------
        send_presence(has_people)

        Log.objects.create(
            event=f"PeopleDetection: count={people_count}, names={detected_names}, "
                  f"temp={env.temperature}, hum={env.humidity}, rfid={env.last_rfid}"
        )

        serializer = EnvironmentSerializer(env)
        return Response(serializer.data)

class ESP32StatusProxyView(APIView):
    """
    GET /api/esp32/status/ → faz GET em http://192.168.4.1/status
    e retorna o JSON exatamente como o ESP32 mandou.
    """
    renderer_classes = [JSONRenderer]

    def get(self, request):
        try:
            r = requests.get(f"{ESP32_IP}/status", timeout=2)
            return Response(r.json())
        except Exception as e:
            return Response({"error": str(e)}, status=500)
