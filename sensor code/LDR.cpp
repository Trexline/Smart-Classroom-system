#include <WiFi.h>
#include <HTTPClient.h>

// --- Configuration ---
const char* ssid = "Trex";
const char* password = "TrexlineSpk24";
const char* serverUrl = "http://10.221.58.86:5000/api/ldr";

// Unique ID for this specific light sensor
const char* deviceId = "LIGHT_MONITOR_01"; 

const int ldrPin = 36; // GPIO 34 (Analog input)

void setup() {
  Serial.begin(115200);
  
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nLDR Sensor Connected!");
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    int ldrValue = analogRead(ldrPin);
    
    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");

    // --- Prepare JSON payload ---
    // Use "ldrvalue" to match what your Flask/Dashboard expects
    String jsonPayload = "{\"deviceId\":\"" + String(deviceId) + 
                         "\",\"ldrvalue\":" + String(ldrValue) + "}";
    
    int httpResponseCode = http.POST(jsonPayload);

    if (httpResponseCode > 0) {
      Serial.printf("[%s] LDR: %d | Server Response: %d\n", deviceId, ldrValue, httpResponseCode);
    } else {
      Serial.printf("Error sending LDR data: %d\n", httpResponseCode);
    }

    http.end();
  }
  
  // Send data every 5 seconds
  delay(5000); 
}