#include <WiFi.h>
#include <HTTPClient.h>

// ===========================
// WiFi credentials
// ===========================
const char* ssid     = "Trex";
const char* password = "TrexlineSpk24";

// ===========================
// Flask server
// ===========================
const char* flaskServer = "http://10.221.58.86:5000:5000/api/pir";

const int pirPin = 14;

// ===========================
// Sensitivity settings
// ===========================
const unsigned long COOLDOWN        = 3000;   // min time between triggers
const unsigned long NO_MOTION_DELAY = 2000;   // time after LOW to clear motion
const unsigned long HEARTBEAT       = 2000;   // send every 2 seconds

unsigned long lastTriggerTime = 0;
unsigned long lastHeartbeat   = 0;
bool motionActive = false;
bool lastState    = LOW;

void setup() {
  Serial.begin(115200);
  pinMode(pirPin, INPUT_PULLDOWN);

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.println(WiFi.localIP());
}

void sendToFlask(int motionValue) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(flaskServer);
  http.addHeader("Content-Type", "application/json");

  String body = "{\"motion_detected\": " + String(motionValue) + "}";
  int responseCode = http.POST(body);

  if (responseCode > 0) {
    Serial.printf("Sent motion=%d  Response: %d\n", motionValue, responseCode);
  } else {
    Serial.printf("Error: %s\n", http.errorToString(responseCode).c_str());
  }
  http.end();
}

void loop() {
  int reading = digitalRead(pirPin);
  unsigned long now = millis();

  // ── Motion detected ────────────────────────────────────────
  if (reading == HIGH) {
    lastTriggerTime = now;

    if (!motionActive && (now - lastTriggerTime == 0 || now - lastTriggerTime < COOLDOWN)) {
      if (!motionActive) {
        Serial.println("✅ Motion detected!");
        motionActive = true;
        sendToFlask(1);
      }
    }
  }

  // ── Motion cleared ─────────────────────────────────────────
  if (motionActive && reading == LOW && (now - lastTriggerTime > NO_MOTION_DELAY)) {
    Serial.println("❌ Motion cleared.");
    motionActive = false;
    sendToFlask(0);
  }

  // ── Heartbeat ──────────────────────────────────────────────
  if (now - lastHeartbeat > HEARTBEAT) {
    lastHeartbeat = now;
    sendToFlask(motionActive ? 1 : 0);
    Serial.printf("Heartbeat: motion=%d\n", motionActive ? 1 : 0);
  }

  lastState = reading;
  delay(100);
}