#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>

// ===========================
// WiFi credentials
// ===========================
const char* ssid     = "low_2.4G.the101_QWWN";
const char* password = "DAYZZLNG";

// ===========================
// Flask server
// ===========================
const char* flaskServer = "http://192.168.0.245:5000/api/dht22";

#define DHTPIN  4      // DHT22 data pin
#define DHTTYPE DHT22

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);
  dht.begin();

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.println(WiFi.localIP());
}

void sendToFlask(float temperature, float humidity) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(flaskServer);
  http.addHeader("Content-Type", "application/json");

  String body = "{\"temperature\": " + String(temperature, 2) +
                ", \"humidity\": "   + String(humidity, 2)    + "}";

  int responseCode = http.POST(body);

  if (responseCode > 0) {
    Serial.printf("Response: %d\n", responseCode);
  } else {
    Serial.printf("Error: %s\n", http.errorToString(responseCode).c_str());
  }
  http.end();
}

void loop() {
  float temperature = dht.readTemperature();
  float humidity    = dht.readHumidity();

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("Failed to read from DHT22!");
    delay(2000);
    return;
  }

  Serial.printf("Temp: %.1f°C  Humidity: %.1f%%\n", temperature, humidity);
  sendToFlask(temperature, humidity);

  delay(5000);  // send every 5 seconds
}