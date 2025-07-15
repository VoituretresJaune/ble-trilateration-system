#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <map>
#include <vector>
#include <algorithm>

// === CONFIGURATION ===
const int RSSI_WINDOW_SIZE = 7;
const unsigned long SEND_INTERVAL = 5000; // Envoi toutes les 5 secondes
const unsigned long MAX_DATA_AGE = 30000; // 30 secondes max pour les données
const char* WIFI_SSID = "IT_Staff";
const char* WIFI_PASS = "8APKXXE3Y6FKD9QNHSCY";
const char* SERVER_URL = "http://10.12.3.19:5001/collect_gateway_info";

// === BEACON CONFIGURATION ===
const int NUM_BEACONS = 4;
const char* BEACON_MACS[NUM_BEACONS] = {
  "c3:00:00:37:31:fd",
  "c3:00:00:37:31:04", 
  "c3:00:00:37:31:f8",
  "c3:00:00:37:31:dd"
};

const char* BEACON_NAMES[NUM_BEACONS] = {
  "balise_1",
  "balise_2",
  "balise_4", 
  "balise_5 "
};

// === VARIABLES GLOBALES ===
BLEScan* pBLEScan;
unsigned long lastSendTime = 0;

// Structure pour stocker RSSI avec timestamp
struct RSSIData {
  int rssi;
  unsigned long timestamp;
};

std::map<String, std::vector<RSSIData>> rssiHistory;

// === FONCTIONS ===

// Fonction pour obtenir le nom de la balise à partir de son MAC
String getBeaconName(String mac) {
  mac.toLowerCase();
  for (int i = 0; i < NUM_BEACONS; i++) {
    if (mac.equalsIgnoreCase(BEACON_MACS[i])) {
      return String(BEACON_NAMES[i]);
    }
  }
  return mac; // Retourne le MAC si pas trouvé
}

// === Wi-Fi ===
void connectToWiFi() {
  Serial.print("Connexion Wi-Fi...");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(" Connecté !");
}

// === RSSI Historique avec nettoyage temporel ===
void updateRSSI(String mac, int rssi) {
  unsigned long now = millis();
  std::vector<RSSIData>& history = rssiHistory[mac];
  
  // Ajouter la nouvelle mesure
  history.push_back({rssi, now});
  
  // Nettoyer les données trop anciennes
  history.erase(
    std::remove_if(history.begin(), history.end(),
      [now](const RSSIData& data) {
        return (now - data.timestamp) > MAX_DATA_AGE;
      }),
    history.end()
  );
  
  // Limiter la taille de la fenêtre
  if (history.size() > RSSI_WINDOW_SIZE) {
    history.erase(history.begin(), history.end() - RSSI_WINDOW_SIZE);
  }
}

// === Médiane améliorée ===
int computeMedian(const std::vector<RSSIData>& values) {
  if (values.empty()) return -100;
  
  std::vector<int> rssi_values;
  for (const auto& data : values) {
    rssi_values.push_back(data.rssi);
  }
  
  std::sort(rssi_values.begin(), rssi_values.end());
  int n = rssi_values.size();
  return (n % 2 == 0) ? (rssi_values[n/2 - 1] + rssi_values[n/2]) / 2 : rssi_values[n/2];
}

// === Envoi au serveur modifié ===
void sendToServer(String mac, int rssi, int median) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  doc["gateway_id"] = "esp32_1";
  doc["beacon_name"] = getBeaconName(mac);
  doc["rssi"] = rssi;
  doc["median"] = median;
  doc["timestamp"] = millis();

  String payload;
  serializeJson(doc, payload);

  int code = http.POST(payload);
  Serial.printf("POST → %s | RSSI: %d | Médiane: %d | Historique: %d | Code: %d\n", 
                getBeaconName(mac).c_str(), rssi, median, rssiHistory[mac].size(), code);
  http.end();
}

// === Callback BLE ===
class MyAdvertisedDeviceCallbacks : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice advertisedDevice) {
    String mac = advertisedDevice.getAddress().toString().c_str();
    for (int i = 0; i < NUM_BEACONS; i++) {
      if (mac.equalsIgnoreCase(BEACON_MACS[i])) {
        int rssi = advertisedDevice.getRSSI();
        updateRSSI(mac, rssi);
        break;  // Stop dès qu'on trouve une balise reconnue
      }
    }
  }
};

// === SETUP ===
void setup() {
  Serial.begin(115200);
  connectToWiFi();

  BLEDevice::init("ESP32_Scanner");
  pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new MyAdvertisedDeviceCallbacks(), true);
  pBLEScan->setActiveScan(true);
  pBLEScan->start(0, nullptr, false);  // Scan BLE infini
}

// === LOOP modifiée ===
void loop() {
  unsigned long now = millis();
  if (now - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = now;

    for (auto const& entry : rssiHistory) {
      String mac = entry.first;
      const std::vector<RSSIData>& history = entry.second;
      
      if (!history.empty()) {
        int median = computeMedian(history);
        int latestRssi = history.back().rssi;  // Dernier RSSI connu
        sendToServer(mac, latestRssi, median);
      }
    }
  }

  delay(100);
}
