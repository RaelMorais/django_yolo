# SeuApp/tasks.py
from celery import shared_task
import cv2
from ultralytics import YOLO
import requests
import time
from .models import Environment, Log # Importe seus models
from django.conf import settings

# ================= Configurações & Inicialização (Global da Task) =================
# O worker do Celery manterá este estado carregado e pronto!

# Importe suas configurações (IPs, RFIDs, etc.) ou defina-as aqui
ESP32_IP = "http://192.168.4.1"
AUTHORIZED_NAME = "Israel"
AUTHORIZED_RFID = "6C3ACB33"
CONFIDENCE_THRESHOLD = 80
ISRAEL_FACE_ID = 1

# Inicialização dos Modelos de Visão Computacional
try:
    yolo_model = YOLO("yolov8n.pt")
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read("trainer.yml") 
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        raise Exception("Câmera não abriu.")
except Exception as e:
    # A task falhará se os modelos não puderem ser carregados.
    print(f"Erro no Celery Worker ao carregar modelos CV: {e}")
    yolo_model, recognizer, face_cascade, cap = None, None, None, None


# ================= Helpers (Copiados das Views) =================
def send_rfid_result(result, nome=""):
    try:
        msg = f"{result}_{nome}" if nome else result
        requests.post(f"{ESP32_IP}/rfid_result", params={"resultado": msg}, timeout=1)
    except Exception as e:
        Log.objects.create(event=f"Celery Error sending RFID result: {e}")


@shared_task
def check_access_task(rfid_code):
    """
    Executa a lógica de Visão Computacional para confirmar acesso.
    Esta função roda no Celery Worker, fora do processo da API do Django.
    """
    
    user = User.objects.filter(rfid=rfid_code).first()
    env = Environment.objects.first() or Environment.objects.create()

    if not user or user.name != AUTHORIZED_NAME or rfid_code != AUTHORIZED_RFID:
        send_rfid_result("negado", "Desconhecido")
        env.light_green = False
        env.light_red = True
        env.save()
        Log.objects.create(event=f"Celery: Acesso NEGADO (RFID/Usuário inválido): {rfid_code}")
        return False

    israel_presente = False
    
    if cap and yolo_model and recognizer and face_cascade:
        ret, frame = cap.read()
        if not ret:
            Log.objects.create(event="Celery: Erro ao ler frame da câmera.")
            send_rfid_result("negado", "Erro Cam")
            return False

        results = yolo_model(frame, verbose=False)
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                
                if cls == 0 and conf > 0.5: # Pessoa detectada
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    person_crop = frame[y1:y2, x1:x2]

                    gray_crop = cv2.cvtColor(person_crop, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray_crop, 1.1, 5)
                    
                    for (fx, fy, fw, fh) in faces:
                        face_roi = gray_crop[fy:fy+fh, fx:fx+fw]
                        label, confidence = recognizer.predict(face_roi)
                        
                        if confidence < CONFIDENCE_THRESHOLD and label == ISRAEL_FACE_ID: 
                            israel_presente = True
                            break
            if israel_presente:
                break
  
    if israel_presente:
        send_rfid_result("permitido", AUTHORIZED_NAME)
        env.light_green = True
        env.light_red = False
        env.save()
        Log.objects.create(event=f"Celery: Acesso PERMITIDO: {AUTHORIZED_NAME} (RFID e Rosto confirmados)")
        return True
    else:
        send_rfid_result("negado", AUTHORIZED_NAME)
        env.light_green = False
        env.light_red = True
        env.save()
        Log.objects.create(event=f"Celery: Acesso NEGADO: RFID OK, mas rosto de {AUTHORIZED_NAME} não confirmado.")
        return False