#pragma once

// Copy this file to src/secrets.h and replace every placeholder.
// src/secrets.h is ignored by Git and must never be committed.

#define WIFI_SSID "YOUR_WIFI_NAME"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// FastAPI host must be reachable from the ESP32 over the same LAN/VPN.
#define BACKEND_HOST "192.168.1.100"
#define BACKEND_PORT 8000

#define DEVICE_ID "gate-1"
#define TERMINAL_API_KEY "YOUR_TERMINAL_API_KEY"
