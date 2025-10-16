import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from .models import User, Environment, Log
from .serializers import UserSerializer, EnvironmentSerializer, LogSerializer

ESP32_IP = "http://192.168.4.1"  # IP do LoRa32 AP

# ================= Helpers =================

def send_led_white(status):
    try:
        requests.post(f"{ESP32_IP}/led_branco", params={"status": status})
    except Exception as e:
        Log.objects.create(event=f"Error sending white LED {status}: {e}")

def send_led_blue(status):
    try:
        requests.post(f"{ESP32_IP}/led_azul", params={"status": status})
    except Exception as e:
        Log.objects.create(event=f"Error sending blue LED {status}: {e}")

def send_rfid_result(result):
    try:
        requests.post(f"{ESP32_IP}/rfid_result", params={"resultado": result})
    except Exception as e:
        Log.objects.create(event=f"Error sending RFID result {result}: {e}")

def get_esp32_status():
    try:
        resp = requests.get(f"{ESP32_IP}/status")
        return resp.json()
    except Exception as e:
        Log.objects.create(event=f"Error fetching ESP32 status: {e}")
        return None

def get_esp32_last_rfid():
    try:
        resp = requests.get(f"{ESP32_IP}/status_rfid")
        return resp.json().get("ultimo_rfid", "")
    except Exception as e:
        Log.objects.create(event=f"Error fetching last RFID: {e}")
        return None

# ================= Generic API Views =================

class EnvironmentView(APIView):
    """GET: Retorna status do ambiente e sensores"""
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
    """PATCH: Liga/desliga LED branco (YOLO detectou pessoa)"""
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
    """PATCH: Controle manual do LED azul"""
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
    """PATCH: Liga/desliga LED verde/vermelho manual (por exemplo, resultado RFID)"""
    renderer_classes = [JSONRenderer]

    def patch(self, request):
        env = Environment.objects.first() or Environment.objects.create()
        status_green = request.data.get("green", False)
        status_red = request.data.get("red", False)

        # Atualiza no banco
        env.light_green = status_green
        env.light_red = status_red
        env.save()

        # Envia resultado para ESP32 (verde = permitido, vermelho = negado)
        if status_green:
            send_rfid_result("permitido")
        elif status_red:
            send_rfid_result("negado")

        Log.objects.create(event=f"LED Green={status_green}, Red={status_red}")
        return Response({"light_green": env.light_green, "light_red": env.light_red})

class RFIDValidationView(APIView):
    """POST: Valida RFID e envia resultado para ESP32"""
    renderer_classes = [JSONRenderer]

    def post(self, request):
        rfid_code = request.data.get("rfid")
        env = Environment.objects.first() or Environment.objects.create()
        env.last_rfid = rfid_code
        env.save()

        user = User.objects.filter(rfid=rfid_code).first()
        if user and user.name in env.detected_people:
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
    """GET: Retorna último RFID lido pelo ESP32"""
    renderer_classes = [JSONRenderer]

    def get(self, request):
        last_rfid = get_esp32_last_rfid()
        return Response({"last_rfid": last_rfid})

class UsersView(APIView):
    """GET: Lista todos os usuários"""
    renderer_classes = [JSONRenderer]

    def get(self, request):
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)
