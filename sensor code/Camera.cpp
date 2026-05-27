#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include "board_config.h"

// ===========================
// WiFi credentials
// ===========================
const char *ssid     = "low_2.4G.the101_QWWN";
const char *password = "DAYZZLNG";

// ===========================
// Flask server address
// ===========================
const char *flaskServer    = "http://192.168.0.245:5000/api/esp32cam";
const char *flaskSetCamIP  = "http://192.168.0.245:5000/api/set_cam_ip";

void startCameraServer();
void setupLedFlash();
void registerCaptureHandler();   // forward-declare — defined below

// ───────────────────────────────────────────────
// Register cam IP + stream URL with Flask
// ───────────────────────────────────────────────
void postIPToFlask() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(flaskServer);
  http.addHeader("Content-Type", "application/json");

  String ip   = WiFi.localIP().toString();
  String body = "{\"image_url\": \"http://" + ip + ":81/stream\", \"ip\": \"" + ip + "\"}";

  int responseCode = http.POST(body);
  if (responseCode > 0) {
    Serial.printf("Flask notified (stream). Response: %d\n", responseCode);
  } else {
    Serial.printf("Failed to notify Flask: %s\n", http.errorToString(responseCode).c_str());
  }
  http.end();
}

// ───────────────────────────────────────────────
// Register cam IP on the dedicated set_cam_ip endpoint
// Flask uses this IP to call /capture when PIR fires
// ───────────────────────────────────────────────
void registerCamIP() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(flaskSetCamIP);
  http.addHeader("Content-Type", "application/json");

  String ip   = WiFi.localIP().toString();
  String body = "{\"ip\": \"" + ip + "\"}";

  int responseCode = http.POST(body);
  if (responseCode > 0) {
    Serial.printf("CAM IP registered with Flask. Response: %d\n", responseCode);
  } else {
    Serial.printf("Failed to register CAM IP: %s\n", http.errorToString(responseCode).c_str());
  }
  http.end();
}

// ───────────────────────────────────────────────
// Capture a frame and POST the JPEG to Flask
// Flask calls GET http://<cam_ip>/capture
// which triggers this, saves the image URL
// ───────────────────────────────────────────────
void captureAndPost() {
  Serial.println("📷 Capturing snapshot...");

  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Camera capture failed");
    return;
  }

  HTTPClient http;
  String ip  = WiFi.localIP().toString();
  // POST the raw JPEG bytes to Flask's /api/esp32cam/snapshot
  String url = "http://192.168.0.245:5000/api/esp32cam/snapshot";
  http.begin(url);
  http.addHeader("Content-Type", "image/jpeg");

  int responseCode = http.POST(fb->buf, fb->len);
  if (responseCode > 0) {
    Serial.printf("✅ Snapshot posted. Response: %d\n", responseCode);
  } else {
    Serial.printf("❌ Snapshot POST failed: %s\n", http.errorToString(responseCode).c_str());
  }
  http.end();

  esp_camera_fb_return(fb);
}

// ───────────────────────────────────────────────
// Setup
// ───────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size   = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location  = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 10;
  config.fb_count     = 1;

  if (config.pixel_format == PIXFORMAT_JPEG) {
    if (psramFound()) {
      config.jpeg_quality = 20;
      config.fb_count     = 2;
      config.grab_mode    = CAMERA_GRAB_LATEST;
    } else {
      config.frame_size  = FRAMESIZE_SVGA;
      config.fb_location = CAMERA_FB_IN_DRAM;
    }
  } else {
    config.frame_size = FRAMESIZE_240X240;
#if CONFIG_IDF_TARGET_ESP32S3
    config.fb_count = 2;
#endif
  }

#if defined(CAMERA_MODEL_ESP_EYE)
  pinMode(13, INPUT_PULLUP);
  pinMode(14, INPUT_PULLUP);
#endif

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);
    s->set_brightness(s, 1);
    s->set_saturation(s, -2);
  }
  if (config.pixel_format == PIXFORMAT_JPEG) {
    s->set_framesize(s, FRAMESIZE_HQVGA);
  }

#if defined(CAMERA_MODEL_M5STACK_WIDE) || defined(CAMERA_MODEL_M5STACK_ESP32CAM)
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
#endif

#if defined(CAMERA_MODEL_ESP32S3_EYE)
  s->set_vflip(s, 1);
#endif

#if defined(LED_GPIO_NUM)
  setupLedFlash();
#endif

  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");

  startCameraServer();

  Serial.print("Camera stream: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/stream");

  // ── Register with Flask ──────────────────────
  postIPToFlask();   // stream URL
  registerCamIP();   // /capture trigger IP
}

// ───────────────────────────────────────────────
// Loop
// ───────────────────────────────────────────────
void loop() {
  static unsigned long lastPost = 0;
  if (millis() - lastPost > 30000) {
    postIPToFlask();
    registerCamIP();
    lastPost = millis();
  }
  delay(1000);
}