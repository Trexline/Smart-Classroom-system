#include <WiFi.h>
#include <HTTPClient.h>

// ===========================
// WiFi credentials
// ===========================
const char* ssid     = "low_2.4G.the101_QWWN";
const char* password = "DAYZZLNG";

// ===========================
// Flask server
// ===========================
const char* flaskServer = "http://192.168.0.245:5000/api/ultrasonic";

// ===========================
// Ultrasonic sensor pins
// ESP32 DevKit V1
// ===========================
const int trigPin = 5;
const int echoPin = 18;

void setup() {
  Serial.begin(115200);
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.println(WiFi.localIP());
}

float getDistance() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 30000);

  if (duration == 0) return -1;  // timeout

  return (duration * 0.0343) / 2;
}

void sendToFlask(float distance) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(flaskServer);
  http.addHeader("Content-Type", "application/json");

  String body = "{\"distance_cm\": " + String(distance, 2) + "}";
  int responseCode = http.POST(body);

  if (responseCode > 0) {
    Serial.printf("Response: %d\n", responseCode);
  } else {
    Serial.printf("Error: %s\n", http.errorToString(responseCode).c_str());
  }
  http.end();
}

void loop() {
  float distance = getDistance();

  if (distance < 0 || distance > 400) {
    Serial.println("Out of range or timeout");
    delay(1000);
    return;
  }

  Serial.printf("Distance: %.2f cm\n", distance);
  sendToFlask(distance);

  delay(2000);
}