import requests
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework import status
from .models import Environment
from .serializers import EnvironmentSerializer

class PeopleDetectionView(APIView):
    renderer_classes = [JSONRenderer]

    def post(self, request):
        """ Endpoint para atualizar dados de detecção de pessoas """
        env = Environment.objects.first() or Environment.objects.create()

        # Recebe dados adicionais (temperatura, umidade, RFID) e atualiza o modelo Environment
        temperatura = request.data.get("temperatura")
        umidade = request.data.get("umidade")
        ultimo_rfid = request.data.get("ultimo_rfid")
        tem_presenca = request.data.get("tem_presenca", False)

        if temperatura is not None and umidade is not None and ultimo_rfid is not None:
            env = env.update_presence(ultimo_rfid, temperatura, umidade, tem_presenca)

        return Response(EnvironmentSerializer(env).data)


class ESP32StatusProxyView(APIView):
    """
    Endpoint para atualizar ou consultar o status do Environment.
    """
    renderer_classes = [JSONRenderer]

    def patch(self, request):
        """ Atualiza apenas people_count e has_presence """
        env = Environment.objects.first() or Environment.objects.create()

        # Buscar os dados do ESP32
        esp32_url = "http://192.168.4.1/status"  # A URL do ESP32
        try:
            response = requests.get(esp32_url)
            response.raise_for_status()
            esp32_data = response.json()  # Dados do ESP32, como temperatura, umidade, RFID, etc.

            # Atualizando os dados do ambiente
            temperatura = esp32_data.get('temperatura')
            umidade = esp32_data.get('umidade')
            ultimo_rfid = esp32_data.get('ultimo_rfid')
            tem_presenca = esp32_data.get('tem_presenca')

            if temperatura is not None and umidade is not None and ultimo_rfid is not None:
                # Atualiza os dados no Django
                env.temperature = temperatura
                env.humidity = umidade
                env.last_rfid = ultimo_rfid
                env.has_presence = tem_presenca

                # Se tem presença, atualize o contador de pessoas
                if tem_presenca:
                    env.people_count += 1  # Aumenta o contador de pessoas, ou outra lógica que você preferir

                env.last_update = timezone.now()
                env.save()

        except requests.exceptions.RequestException as e:
            # Trate erros de conexão ou resposta inválida
            return Response({"error": f"Erro ao conectar com o ESP32: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(EnvironmentSerializer(env).data, status=status.HTTP_200_OK)

    def get(self, request):
        """ Retorna o status atual do Environment """
        env = Environment.objects.first()
        if not env:
            env = Environment.objects.create()
        return Response(EnvironmentSerializer(env).data, status=status.HTTP_200_OK)
