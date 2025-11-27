import os
import time
import requests
import cv2
from ultralytics import YOLO

ESP32_STATUS_URL = "http://localhost:8000/api/status/"

CONFIDENCE_THRESHOLD = 80
ID_NAMES = {1: "Israel", 2: "Maria", 3: "João"}

# Caminhos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
yolo_model = YOLO(os.path.join(BASE_DIR, "yolov8n.pt"))
recognizer_path = os.path.join(BASE_DIR, "trainer.yml")
recognizer = cv2.face.LBPHFaceRecognizer_create()
recognizer.read(recognizer_path)
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

# Câmera
def find_working_camera(max_index=5):
    for i in range(max_index + 1):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cap.release()
            return i
        cap.release()
    return None

camera_index = find_working_camera()
if camera_index is None:
    raise RuntimeError("Nenhuma câmera funcional encontrada!")
cap = cv2.VideoCapture(camera_index)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Função para enviar PATCH
def send_presence_to_django(people_count):
    try:
        data = {
            "people_count": people_count,
            "has_presence": people_count > 0
        }
        response = requests.patch(ESP32_STATUS_URL, json=data, timeout=2)
        if response.status_code != 200:
            print(f"Falha ao enviar status ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"Erro ao enviar status: {e}")


# Loop principal
while True:
    ret, frame = cap.read()
    if not ret:
        continue

    results = yolo_model(frame, verbose=False)
    people_boxes = []

    for result in results:
        for box in result.boxes:
            if int(box.cls[0]) == 0 and float(box.conf[0]) > 0.5:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                people_boxes.append((x1, y1, x2, y2))
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, "Pessoa", (x1, y1-5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)

    people_count = len(people_boxes)
    send_presence_to_django(people_count)

    cv2.putText(frame, f"Count: {people_count}", (10,30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
    cv2.imshow("Monitoramento de Pessoas", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
