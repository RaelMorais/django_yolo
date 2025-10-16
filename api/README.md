
# Main.cpp
 #include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <SPI.h>
#include <MFRC522.h>
#include "DHT.h"

// ------------------- PINAGEM -------------------
#define LED_VERMELHO 17 // AZUL
#define LED_BRANCO   16 // VERMELHO 
#define LED_AZUL     4 // BRANCO
#define LED_VERDE    5 // VERDE
#define BUZZER       15

#define DHT_PIN 18
#define DHT_TYPE DHT11
#define RST_PIN 13
#define SS_PIN  23  // SDA RFID

DHT dht(DHT_PIN, DHT_TYPE);
MFRC522 rfid(SS_PIN, RST_PIN);
WebServer server(80);

// ------------------- CONFIGURAÇÃO Wi-Fi -------------------
const char* ssid = "LoRa32-AP";
const char* password = "12345678";

// ------------------- VARIÁVEIS GLOBAIS -------------------
float temperatura = 0.0;
float umidade = 0.0;
String ultimoRFID = "";
unsigned long ultimoTempoLeitura = 0;

// UID autorizado (exemplo)
byte uidAutorizado[] = {0xE6, 0xB2, 0x8B, 0xF9};

// ------------------- FUNÇÕES AUXILIARES -------------------
void logLine(String msg) {
  Serial.println("------------------------------------------------");
  Serial.println(msg);
  Serial.println("------------------------------------------------");
}

void logEvent(String tipo, String msg) {
  Serial.printf("[%s] %s\n", tipo.c_str(), msg.c_str());
}

void acenderLED(int pin, bool estado) {
  digitalWrite(pin, estado ? HIGH : LOW);
}

// ------------------- TESTE INICIAL -------------------
void testeInicial() {
  logLine("INICIANDO TESTE DE LEDS E BUZZER");

  int leds[] = {LED_AZUL, LED_VERDE, LED_BRANCO, LED_VERMELHO};
  const char* nomes[] = {"AZUL", "VERDE", "BRANCO", "VERMELHO"};

  for (int i = 0; i < 4; i++) {
    logEvent("LED", String("Ligando LED_") + nomes[i]);
    acenderLED(leds[i], true);
    delay(300);
    acenderLED(leds[i], false);
    delay(100);
  }

  logEvent("TESTE", "Acendendo todos os LEDs");
  for (int i = 0; i < 4; i++) acenderLED(leds[i], true);
  delay(500);

  logEvent("BUZZER", "Beep curto");
  digitalWrite(BUZZER, HIGH); delay(150); digitalWrite(BUZZER, LOW); delay(200);

  logEvent("BUZZER", "Beep longo");
  digitalWrite(BUZZER, HIGH); delay(800); digitalWrite(BUZZER, LOW); delay(300);

  logEvent("TESTE", "Piscar rápido final");
  for (int j = 0; j < 3; j++) {
    for (int i = 0; i < 4; i++) acenderLED(leds[i], LOW);
    delay(100);
    for (int i = 0; i < 4; i++) acenderLED(leds[i], HIGH);
    delay(100);
  }

  for (int i = 0; i < 4; i++) acenderLED(leds[i], LOW);
  digitalWrite(BUZZER, LOW);
  logLine("TESTE DE LEDS E BUZZER CONCLUIDO ✅");
}

// ------------------- ENDPOINTS -------------------
void sendCORS() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void handleOptions() {
  sendCORS();
  server.send(204);
}

void handleStatus() {
  sendCORS();
  String json = "{\"temperatura\":" + String(temperatura, 1) +
                ",\"umidade\":" + String(umidade, 1) +
                ",\"ultimo_rfid\":\"" + ultimoRFID + "\"}";
  server.send(200, "application/json", json);
}

void handleStatusRFID() {
  sendCORS();
  server.send(200, "application/json", "{\"ultimo_rfid\":\"" + ultimoRFID + "\"}");
}

void handleLedBranco() {
  sendCORS();
  String status = server.arg("status");
  if (status == "on") {
    acenderLED(LED_BRANCO, true);
    logEvent("LED", "LED BRANCO LIGADO (pessoa detectada)");
    server.send(200, "text/plain", "LED branco ligado");
  } else {
    acenderLED(LED_BRANCO, false);
    logEvent("LED", "LED BRANCO DESLIGADO");
    server.send(200, "text/plain", "LED branco desligado");
  }
}

void handleLedAzul() {
  sendCORS();
  String status = server.arg("status");
  if (status == "on") {
    acenderLED(LED_AZUL, true);
    logEvent("LED", "LED AZUL LIGADO via API");
    server.send(200, "text/plain", "LED azul ligado");
  } else {
    acenderLED(LED_AZUL, false);
    logEvent("LED", "LED AZUL DESLIGADO via API");
    server.send(200, "text/plain", "LED azul desligado");
  }
}

void handleRfidResult() {
  sendCORS();
  String resultado = server.arg("resultado");

  if (resultado == "permitido") {
    acenderLED(LED_VERDE, true);
    acenderLED(LED_VERMELHO, false);
    logEvent("RFID", "Acesso PERMITIDO");
    digitalWrite(BUZZER, HIGH); delay(150); digitalWrite(BUZZER, LOW);
  } else if (resultado == "negado") {
    acenderLED(LED_VERDE, false);
    acenderLED(LED_VERMELHO, true);
    logEvent("RFID", "Acesso NEGADO");
    digitalWrite(BUZZER, HIGH); delay(800); digitalWrite(BUZZER, LOW);
  } else {
    server.send(400, "text/plain", "Parametro 'resultado' invalido (use 'permitido' ou 'negado')");
    return;
  }

  server.send(200, "text/plain", "Resultado recebido: " + resultado);
}

// ------------------- SETUP -------------------
void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(LED_VERMELHO, OUTPUT);
  pinMode(LED_BRANCO, OUTPUT);
  pinMode(LED_AZUL, OUTPUT);
  pinMode(LED_VERDE, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  testeInicial();

  dht.begin();
  SPI.begin(19, 12, 22, 23);
  rfid.PCD_Init();

  WiFi.softAP(ssid, password);
  IPAddress IP = WiFi.softAPIP();
  logEvent("WIFI", "Access Point ativo: SSID=" + String(ssid) + " | IP=" + IP.toString());

  // Endpoints
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/status_rfid", HTTP_GET, handleStatusRFID);
  server.on("/led_branco", HTTP_ANY, handleLedBranco);
  server.on("/led_azul", HTTP_ANY, handleLedAzul);
  server.on("/rfid_result", HTTP_ANY, handleRfidResult);
  server.onNotFound([]() {
    if (server.method() == HTTP_OPTIONS) handleOptions();
    else {
      sendCORS();
      server.send(404, "text/plain", "Endpoint nao encontrado");
    }
  });
  server.begin();

  logEvent("HTTP", "Servidor Web ativo na porta 80");
}

// ------------------- LOOP PRINCIPAL -------------------
void loop() {
  server.handleClient();

  // Leitura de sensores
  unsigned long agora = millis();
  if (agora - ultimoTempoLeitura > 5000) {
    temperatura = dht.readTemperature();
    umidade = dht.readHumidity();
    if (!isnan(temperatura) && !isnan(umidade)) {
      logEvent("DHT", "Temp=" + String(temperatura) + "C  Umid=" + String(umidade) + "%");
    }
    ultimoTempoLeitura = agora;
  }

  // Leitura RFID
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    ultimoRFID = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) ultimoRFID += "0";
      ultimoRFID += String(rfid.uid.uidByte[i], HEX);
    }
    ultimoRFID.toUpperCase();
    logEvent("RFID", "Cartao detectado: " + ultimoRFID);
    rfid.PICC_HaltA();
  }
}


# Plataform.ini

monitor_speed = 115200
upload_port = COM6
monitor_port = COM6

lib_deps =
    adafruit/DHT sensor library@^1.4.4
    adafruit/Adafruit Unified Sensor@^1.1.6
    miguelbalboa/MFRC522@^1.4.10
