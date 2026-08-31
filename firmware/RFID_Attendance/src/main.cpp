/*
  Vidyarthi-IoT ESP32 terminal

  Workflow:
    1. Teacher scans RFID card.
    2. Backend classifies the card from the role-aware roster.
    3. Teacher presses:
         Button 1 -> Feedback mode
         Button 2 -> Ration mode
    4. Feedback mode: each student scans -> Button 1..4 records rating.
    5. Ration mode: each student scans -> one ration is deducted from today's stock.

  IMPORTANT:
    - Button pins below are configurable. Wire four momentary push-buttons
      from the selected GPIO to GND; INPUT_PULLUP is used, so a pressed button
      reads LOW.
    - Feedback/ration mode requires the WebSocket backend because teacher
      authentication and ration stock deduction must be authoritative.
*/

#include <SPI.h>
#include <MFRC522.h>

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <time.h>

#include <Wire.h>
#include <Adafruit_SSD1306.h>

#include "secrets.h"

// ---------------------------------------------------------------- network
const long GMT_OFFSET_SEC = 5 * 3600 + 30 * 60;
const int DAYLIGHT_OFFSET_SEC = 0;

// ---------------------------------------------------------------- RFID
#define SS_PIN 21
#define RST_PIN 22
MFRC522 mfrc522(SS_PIN, RST_PIN);

// ---------------------------------------------------------------- OLED
#define OLED_ADDR 0x3C
#define SDA_PIN 5
#define SCK_PIN 4
Adafruit_SSD1306 display(128, 64, &Wire, -1);

// ---------------------------------------------------------------- buttons
// Four physical buttons. Pressed = LOW because of INPUT_PULLUP.
const uint8_t BUTTON1_PIN = 25;
const uint8_t BUTTON2_PIN = 26;
const uint8_t BUTTON3_PIN = 27;
const uint8_t BUTTON4_PIN = 32;
const uint8_t BUTTON_COUNT = 4;
const uint8_t BUTTON_PINS[BUTTON_COUNT] = {
    BUTTON1_PIN, BUTTON2_PIN, BUTTON3_PIN, BUTTON4_PIN};

bool lastButtonState[BUTTON_COUNT] = {HIGH, HIGH, HIGH, HIGH};
unsigned long lastButtonEventMs = 0;
const unsigned long BUTTON_DEBOUNCE_MS = 180;

// ---------------------------------------------------------------- websocket
WebSocketsClient webSocket;
bool wsConnected = false;

// ---------------------------------------------------------------- terminal state
enum TerminalMode
{
  MODE_IDLE,
  MODE_SELECT,
  MODE_ATTENDANCE,
  MODE_FEEDBACK,
  MODE_RATION
};

TerminalMode terminalMode = MODE_IDLE;

String teacherRoll = "";
String teacherName = "";
String feedbackSessionId = "";

String pendingStudentUid = "";
String pendingStudentName = "";
String pendingStudentRoll = "";

// RFID debounce: prevents repeated reads of the same card.
const unsigned long CARD_DEBOUNCE_MS = 2000;
String lastCardId = "";
unsigned long lastCardMillis = 0;

// Heartbeat
const unsigned long HEARTBEAT_INTERVAL_MS = 20000;
unsigned long lastHeartbeatMillis = 0;

bool waitingForModeStart = false;
unsigned long modeStartRequestedMs = 0;
const unsigned long MODE_START_TIMEOUT_MS = 5000;

bool waitingForModeStop = false;
unsigned long modeStopRequestedMs = 0;
const unsigned long MODE_STOP_TIMEOUT_MS = 5000;

bool waitingForCardResponse = false;
unsigned long cardScanRequestedMs = 0;
const unsigned long CARD_RESPONSE_TIMEOUT_MS = 5000;

bool waitingForAttendanceResult = false;
unsigned long attendanceRequestedMs = 0;
const unsigned long ATTENDANCE_RESULT_TIMEOUT_MS = 5000;
// Offline attendance replay is intentionally disabled because attendance
// requires an active teacher-started mode on the authoritative backend.

// ---------------------------------------------------------------- helpers
void showMessage(const String &line1, const String &line2 = "", const String &line3 = "")
{
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(WHITE);
  display.setCursor(0, 0);
  display.println(line1);
  if (line2.length())
    display.println(line2);
  if (line3.length())
    display.println(line3);
  display.display();
}

String modeLabel()
{
  switch (terminalMode)
  {
  case MODE_SELECT:
    return "Select mode";
  case MODE_ATTENDANCE:
    return "Attendance";
  case MODE_FEEDBACK:
    return "Feedback";
  case MODE_RATION:
    return "Ration";
  default:
    return "Idle";
  }
}

void showModeReady()
{
  if (terminalMode == MODE_FEEDBACK)
  {
    if (pendingStudentUid.length())
    {
      showMessage(
          "Feedback mode",
          pendingStudentName,
          "Buttons 1-4 = rating");
    }
    else
    {
      showMessage(
          "Feedback mode",
          "Scan student card",
          "Btn 4: Exit");
    }
  }
  else if (terminalMode == MODE_RATION)
  {
    showMessage(
        "Ration mode",
        "Scan student card",
        "Btn 4: Exit");
  }
  else if (terminalMode == MODE_ATTENDANCE)
  {
    showMessage(
        "Attendance mode",
        "Scan student card",
        "Btn 4: Exit");
  }
  else if (terminalMode == MODE_SELECT)
  {
    showMessage(
        "Teacher verified",
        teacherName,
        "1:Fdbk 2:Ration 3:Attend");
  }
  else
  {
    showMessage(
        "Vidyarthi-IoT",
        wsConnected ? "Ready - scan card" : "Offline - attendance only",
        String("Device: ") + DEVICE_ID);
  }
}

void connectToWiFi()
{
  WiFi.mode(WIFI_OFF);
  delay(200);
  WiFi.mode(WIFI_STA);

  Serial.print("Connecting to ");
  Serial.println(WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000)
  {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.print("Connected, IP address: ");
    Serial.println(WiFi.localIP());

    configTime(
        GMT_OFFSET_SEC,
        DAYLIGHT_OFFSET_SEC,
        "pool.ntp.org",
        "time.google.com");
  }
  else
  {
    Serial.println("Wi-Fi connect timed out; retrying in loop().");
  }
}

String getIsoTimestamp()
{
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 200))
    return "";

  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &timeinfo);
  return String(buf);
}

String formatUid(MFRC522::Uid *uid)
{
  String out = "";

  for (byte i = 0; i < uid->size; i++)
  {
    if (uid->uidByte[i] < 0x10)
      out += "0";
    out += String(uid->uidByte[i], HEX);
    if (i < uid->size - 1)
      out += ":";
  }

  out.toUpperCase();
  return out;
}

// ---------------------------------------------------------------- sending
void sendHeartbeat()
{
  JsonDocument doc;
  doc["type"] = "heartbeat";
  JsonObject data = doc["data"].to<JsonObject>();
  data["rssi"] = WiFi.RSSI();
  data["queue"] = 0;

  String out;
  serializeJson(doc, out);
  webSocket.sendTXT(out);
}

void sendCardScan(const String &uid)
{
  if (!wsConnected)
    return;

  JsonDocument doc;
  doc["type"] = "card_scan";

  JsonObject data = doc["data"].to<JsonObject>();
  data["uid"] = uid;

  String ts = getIsoTimestamp();
  if (ts.length())
    data["ts"] = ts;

  String out;
  serializeJson(doc, out);
  webSocket.sendTXT(out);

  waitingForCardResponse = true;
  cardScanRequestedMs = millis();
}

void sendStartMode(const String &mode)
{
  if (!wsConnected)
  {
    showMessage("No backend", "Mode needs network", "Reconnect Wi-Fi");
    return;
  }

  JsonDocument doc;
  doc["type"] = "start_mode";

  JsonObject data = doc["data"].to<JsonObject>();
  data["mode"] = mode;
  data["teacher_roll"] = teacherRoll;

  String out;
  serializeJson(doc, out);
  webSocket.sendTXT(out);

  waitingForModeStart = true;
  modeStartRequestedMs = millis();

  String modeName = "Ration";
  if (mode == "feedback")
  {
    modeName = "Feedback";
  }
  else if (mode == "attendance")
  {
    modeName = "Attendance";
  }

  showMessage("Starting...", modeName, "Please wait");
}
void resetToIdle()
{
  terminalMode = MODE_IDLE;
  teacherRoll = "";
  teacherName = "";
  feedbackSessionId = "";

  pendingStudentUid = "";
  pendingStudentName = "";
  pendingStudentRoll = "";

  waitingForModeStart = false;
  waitingForModeStop = false;
  waitingForCardResponse = false;
  waitingForAttendanceResult = false;

  showModeReady();
}
void sendStopMode()
{
  if (!wsConnected)
  {
    resetToIdle();
    return;
  }

  JsonDocument doc;
  doc["type"] = "stop_mode";

  JsonObject data = doc["data"].to<JsonObject>();

  // Keep teacher information for backend validation/logging
  data["teacher_roll"] = teacherRoll;

  String out;
  serializeJson(doc, out);
  webSocket.sendTXT(out);

  waitingForModeStop = true;
  modeStopRequestedMs = millis();

  showMessage("Ending mode...", "Please wait");
}

void sendFeedbackRating(uint8_t rating)
{
  if (!wsConnected || pendingStudentUid.isEmpty())
  {
    showModeReady();
    return;
  }

  JsonDocument doc;
  doc["type"] = "feedback";

  JsonObject data = doc["data"].to<JsonObject>();
  data["uid"] = pendingStudentUid;
  data["rating"] = rating;

  String out;
  serializeJson(doc, out);
  webSocket.sendTXT(out);
}

void sendRationClaim(
    const String &uid,
    const String &roll)
{
  if (!wsConnected)
  {
    showMessage(
        "No backend",
        "Ration needs network",
        "Card not processed");

    return;
  }

  JsonDocument doc;
  doc["type"] = "ration_claim";

  JsonObject data = doc["data"].to<JsonObject>();

  data["uid"] = uid;
  data["roll"] = roll;

  String out;
  serializeJson(doc, out);

  webSocket.sendTXT(out);
}

void sendOrBufferAttendance(const String &uid)
{
  // Attendance requires a live backend connection and an active
  // teacher-started Attendance mode. Do not buffer offline taps.
  if (!wsConnected)
  {
    showMessage(
        "No backend",
        "Attendance locked",
        "Teacher + network required");
    return;
  }

  if (terminalMode != MODE_ATTENDANCE || teacherRoll.length() == 0)
  {
    showMessage(
        "Attendance locked",
        "Scan teacher first",
        "Then press 3");
    return;
  }

  JsonDocument doc;
  doc["type"] = "tap";

  JsonObject data = doc["data"].to<JsonObject>();
  data["uid"] = uid;

  String ts = getIsoTimestamp();
  if (ts.length())
    data["ts"] = ts;

  String out;
  serializeJson(doc, out);
  webSocket.sendTXT(out);

  waitingForAttendanceResult = true;
  attendanceRequestedMs = millis();
}

// ---------------------------------------------------------------- UI state

// Called when a button edge is detected.
void handleButtonPress(uint8_t buttonNumber)
{
  Serial.printf(
      "Button %d pressed in mode %s\n",
      buttonNumber,
      modeLabel().c_str());

  // ------------------------------------------------ SELECT MODE
  if (terminalMode == MODE_SELECT)
  {
    if (buttonNumber == 1)
    {
      pendingStudentUid = "";
      pendingStudentName = "";
      pendingStudentRoll = "";

      sendStartMode("feedback");
      return;
    }

    if (buttonNumber == 2)
    {
      pendingStudentUid = "";
      pendingStudentName = "";
      pendingStudentRoll = "";

      sendStartMode("ration");
      return;
    }

    if (buttonNumber == 3)
    {
      pendingStudentUid = "";
      pendingStudentName = "";
      pendingStudentRoll = "";

      sendStartMode("attendance");
      return;
    }

    if (buttonNumber == 4)
    {
      resetToIdle();
      return;
    }

    return;
  }

  // ------------------------------------------------ FEEDBACK MODE
  if (terminalMode == MODE_FEEDBACK)
  {
    // A student is waiting for a rating.
    // Buttons 1-4 are ratings.
    if (pendingStudentUid.length())
    {
      if (buttonNumber >= 1 && buttonNumber <= 4)
      {
        sendFeedbackRating(buttonNumber);
      }

      return;
    }

    // No student is selected.
    // Button 4 exits feedback mode.
    if (buttonNumber == 4)
    {
      sendStopMode();
      return;
    }

    return;
  }
  // ------------------------------------------------ ATTENDANCE MODE
  if (terminalMode == MODE_ATTENDANCE)
  {
    // Button 4 exits attendance mode.
    if (buttonNumber == 4)
    {
      sendStopMode();
      return;
    }

    return;
  }

  // ------------------------------------------------ RATION MODE
  if (terminalMode == MODE_RATION)
  {
    // Button 4 exits ration mode.
    if (buttonNumber == 4)
    {
      sendStopMode();
      return;
    }

    return;
  }

  // ------------------------------------------------ IDLE MODE
}

void pollButtons()
{
  unsigned long now = millis();

  for (uint8_t i = 0; i < BUTTON_COUNT; i++)
  {
    bool current = digitalRead(BUTTON_PINS[i]);

    if (current == LOW && lastButtonState[i] == HIGH)
    {
      if (now - lastButtonEventMs >= BUTTON_DEBOUNCE_MS)
      {
        lastButtonEventMs = now;
        handleButtonPress(i + 1);
      }
    }

    lastButtonState[i] = current;
  }
}

// ---------------------------------------------------------------- websocket
void webSocketEvent(WStype_t type, uint8_t *payload, size_t length)
{
  switch (type)
  {
  case WStype_CONNECTED:
    wsConnected = true;
    Serial.println("WebSocket connected to backend");
    showModeReady();
    break;

  case WStype_DISCONNECTED:
    wsConnected = false;
    waitingForModeStart = false;
    waitingForModeStop = false;
    waitingForCardResponse = false;
    waitingForAttendanceResult = false;
    Serial.println("WebSocket disconnected");

    // Mode cannot continue without authoritative backend access.
    if (terminalMode != MODE_IDLE)
    {
      terminalMode = MODE_IDLE;
      teacherRoll = "";
      teacherName = "";
      feedbackSessionId = "";
      pendingStudentUid = "";
      pendingStudentName = "";
      pendingStudentRoll = "";
    }

    showModeReady();
    break;

  case WStype_TEXT:
  {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, payload, length);

    if (err)
    {
      Serial.printf("Invalid backend JSON: %s\n", err.c_str());
      return;
    }

    const char *msgType = doc["type"] | "";
    JsonObject data = doc["data"].as<JsonObject>();

    // ------------------------------------------- teacher/student classifier
    if (strcmp(msgType, "card_result") == 0)
    {
      waitingForCardResponse = false;
      bool ok = data["ok"] | false;
      String role = String((const char *)(data["role"] | ""));
      String name = String((const char *)(data["name"] | ""));
      String roll = String((const char *)(data["roll"] | ""));
      String message = String((const char *)(data["message"] | ""));

      if (!ok)
      {
        String rejectedUid = String((const char *)(data["uid"] | ""));
        showMessage(
            "Unknown card",
            rejectedUid.length() ? rejectedUid : message,
            "Not in roster");
        delay(900);
        showModeReady();
        break;
      }

      if (role == "teacher")
      {
        terminalMode = MODE_SELECT;
        teacherRoll = roll;
        teacherName = name;
        feedbackSessionId = "";
        pendingStudentUid = "";
        pendingStudentName = "";
        pendingStudentRoll = "";

        showMessage(
            "Teacher verified",
            teacherName,
            "1:Fdbk 2:Ration 3:Attend");
        break;
      }

      if (role == "student")
      {
        if (terminalMode == MODE_ATTENDANCE)
        {
          pendingStudentUid =
              String((const char *)(data["uid"] | ""));

          pendingStudentName = name;
          pendingStudentRoll = roll;

          showMessage(
              "Student",
              pendingStudentName,
              "Recording attendance...");

          // The backend checks that Attendance mode was started by a
          // verified teacher before recording this tap.
          sendOrBufferAttendance(pendingStudentUid);
        }
        else if (terminalMode == MODE_FEEDBACK)
        {
          pendingStudentUid =
              String((const char *)(data["uid"] | ""));

          pendingStudentName = name;

          pendingStudentRoll = roll;

          showMessage(
              "Student",
              pendingStudentName,
              "Press 1-4 to rate");
        }
        else if (terminalMode == MODE_RATION)
        {
          pendingStudentUid =
              String((const char *)(data["uid"] | ""));

          pendingStudentName = name;
          pendingStudentRoll = roll;

          showMessage(
              "Student",
              pendingStudentName,
              "Issuing ration...");

          sendRationClaim(
              pendingStudentUid,
              pendingStudentRoll);
        }
        else
        {
          showMessage(
              "Attendance locked",
              "Teacher must scan",
              "first");
          delay(900);
          showModeReady();
        }

        break;
      }

      break;
    }

    // --------------------------------------------------------- mode start
    // --------------------------------------------------------- mode started
    if (strcmp(msgType, "mode_started") == 0)
    {
      waitingForModeStart = false;
      bool ok = data["ok"] | false;

      if (!ok)
      {
        showMessage(
            "Mode failed",
            String((const char *)(data["message"] | "")),
            "Try again");

        terminalMode = MODE_SELECT;
        pendingStudentUid = "";
        pendingStudentName = "";
        pendingStudentRoll = "";

        delay(1000);
        showModeReady();
        break;
      }

      String mode =
          String((const char *)(data["mode"] | ""));

      if (mode == "attendance")
      {
        terminalMode = MODE_ATTENDANCE;
      }
      else if (mode == "feedback")
      {
        terminalMode = MODE_FEEDBACK;
      }
      else if (mode == "ration")
      {
        terminalMode = MODE_RATION;
      }

      pendingStudentUid = "";
      pendingStudentName = "";
      pendingStudentRoll = "";

      showModeReady();
      break;
    }
    // ---------------------------------------------------------- mode stopped
    if (strcmp(msgType, "mode_stopped") == 0)
    {
      waitingForModeStop = false;
      bool ok = data["ok"] | false;

      if (ok)
      {
        String previousMode =
            String((const char *)(data["previous_mode"] | ""));

        showMessage(
            "Mode ended",
            previousMode,
            "Returning to idle");

        delay(700);
        resetToIdle();
      }
      else
      {
        showMessage(
            "Stop failed",
            String((const char *)(data["message"] | "")),
            "Try again");

        delay(800);
        showModeReady();
      }

      break;
    }

    // ------------------------------------------------------ attendance result
    if (strcmp(msgType, "attendance_result") == 0)
    {
      waitingForAttendanceResult = false;
      bool ok = data["ok"] | false;
      bool alreadyMarked = data["already_marked"] | false;
      bool proxyCleared = data["proxy_cleared"] | false;

      if (!ok)
      {
        showMessage(
            "Attendance failed",
            String((const char *)(data["message"] | "")),
            "Scan again");

        pendingStudentUid = "";
        pendingStudentName = "";
        pendingStudentRoll = "";

        delay(800);
        showModeReady();
        break;
      }

      String name =
          String((const char *)(data["name"] | ""));

      if (proxyCleared)
      {
        showMessage(
            "Proxy cleared",
            name,
            "Verified");
      }
      else if (data["proxy_suspected"] | false)
      {
        showMessage(
            "Proxy suspected",
            name,
            alreadyMarked ? "Already marked" : "Do not count");
      }
      else if (alreadyMarked)
      {
        showMessage(
            "Already marked",
            name,
            "No duplicate saved");
      }
      else
      {
        showMessage(
            "Attendance saved",
            name,
            data["proxy_suspected"] | false ? "Proxy suspected" : "Present");
      }

      pendingStudentUid = "";
      pendingStudentName = "";
      pendingStudentRoll = "";

      delay(800);
      showModeReady();
      break;
    }

    // ------------------------------------------------------ feedback result
    if (strcmp(msgType, "feedback_result") == 0)
    {
      bool ok = data["ok"] | false;

      if (!ok)
      {
        showMessage(
            "Feedback failed",
            String((const char *)(data["message"] | "")),
            "Scan student again");
        delay(800);
        pendingStudentUid = "";
        pendingStudentName = "";
        pendingStudentRoll = "";
        showModeReady();
        break;
      }

      uint8_t rating = data["rating"] | 0;
      String name = String((const char *)(data["name"] | ""));

      showMessage(
          "Feedback saved",
          name,
          String("Rating: ") + rating + "/4");

      pendingStudentUid = "";
      pendingStudentName = "";
      pendingStudentRoll = "";
      delay(800);
      showModeReady();
      break;
    }

    // --------------------------------------------------------- ration result
    if (strcmp(msgType, "ration_result") == 0)
    {
      bool ok = data["ok"] | false;

      if (!ok)
      {
        showMessage(
            "Ration not issued",
            String((const char *)(data["message"] | "")),
            "Scan another card");
        pendingStudentUid = "";
        pendingStudentName = "";
        pendingStudentRoll = "";
        delay(900);
        showModeReady();
        break;
      }

      String name = String((const char *)(data["name"] | ""));
      float remainingGrain = data["remaining_grain_kg"] | 0.0;
      float remainingPulse = data["remaining_pulses_kg"] | 0.0;

      showMessage(
          "Ration issued",
          name,
          String("G:") + String(remainingGrain, 3) +
              "kg P:" + String(remainingPulse, 3));

      pendingStudentUid = "";
      pendingStudentName = "";
      pendingStudentRoll = "";
      delay(900);
      showModeReady();
      break;
    }

    break;
  }

  case WStype_ERROR:
    Serial.println("WebSocket error");
    break;

  default:
    break;
  }
}

// ---------------------------------------------------------------- setup
void setup()
{
  Serial.begin(115200);

  // Buttons
  for (uint8_t i = 0; i < BUTTON_COUNT; i++)
  {
    pinMode(BUTTON_PINS[i], INPUT_PULLUP);
    lastButtonState[i] = digitalRead(BUTTON_PINS[i]);
  }

  // RFID
  SPI.begin();
  mfrc522.PCD_Init();

  // OLED
  Wire.begin(SDA_PIN, SCK_PIN);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR))
  {
    Serial.println(F("SSD1306 allocation failed"));
    for (;;)
    {
      delay(1000);
    }
  }

  display.clearDisplay();
  display.display();

  showMessage("Starting...", "Connecting Wi-Fi...");
  connectToWiFi();

  showMessage("Wi-Fi connected", "Connecting backend...");
  String wsPath =
      String("/ws/terminal/gate-1?token=") +
      TERMINAL_API_KEY;

  webSocket.begin(
      BACKEND_HOST,
      BACKEND_PORT,
      wsPath);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);

  showModeReady();

  mfrc522.PCD_DumpVersionToSerial();
}

// ---------------------------------------------------------------- loop
void loop()
{
  if (!WiFi.isConnected())
  {
    connectToWiFi();
    showModeReady();
  }

  webSocket.loop();

  if (waitingForModeStart &&
      millis() - modeStartRequestedMs >= MODE_START_TIMEOUT_MS)
  {
    waitingForModeStart = false;
    Serial.println("Mode start timeout - no backend response");

    showMessage(
        "Mode failed",
        "Backend did not reply",
        "Press 3 again");

    if (wsConnected)
    {
      terminalMode = MODE_SELECT;
      pendingStudentUid = "";
      pendingStudentName = "";
      pendingStudentRoll = "";
      delay(800);
      showModeReady();
    }
  }

  if (waitingForModeStop &&
      millis() - modeStopRequestedMs >= MODE_STOP_TIMEOUT_MS)
  {
    waitingForModeStop = false;
    Serial.println("Mode stop timeout - no backend response");

    showMessage(
        "Stop timed out",
        "Backend did not reply",
        "Returning to idle");

    delay(800);
    resetToIdle();
  }

  if (waitingForCardResponse &&
      millis() - cardScanRequestedMs >= CARD_RESPONSE_TIMEOUT_MS)
  {
    waitingForCardResponse = false;
    Serial.println("Card response timeout - no backend response");

    pendingStudentUid = "";
    pendingStudentName = "";
    pendingStudentRoll = "";

    showMessage(
        "Card check failed",
        "Backend did not reply",
        "Try again");

    delay(900);
    showModeReady();
  }

  if (waitingForAttendanceResult &&
      millis() - attendanceRequestedMs >= ATTENDANCE_RESULT_TIMEOUT_MS)
  {
    waitingForAttendanceResult = false;
    Serial.println("Attendance response timeout - no backend response");

    pendingStudentUid = "";
    pendingStudentName = "";
    pendingStudentRoll = "";

    showMessage(
        "Attendance failed",
        "Backend did not reply",
        "Scan again");

    delay(900);
    showModeReady();
  }

  if (wsConnected &&
      millis() - lastHeartbeatMillis >= HEARTBEAT_INTERVAL_MS)
  {
    lastHeartbeatMillis = millis();
    sendHeartbeat();
  }

  if (millis() - lastCardMillis >= CARD_DEBOUNCE_MS)
  {
    lastCardId = "";
  }

  // Buttons remain responsive even while waiting for RFID cards.
  pollButtons();

  // Process one authoritative request at a time. Timeout logic above
  // releases the lock if the backend never responds.
  if (waitingForModeStart ||
      waitingForModeStop ||
      waitingForCardResponse ||
      waitingForAttendanceResult)
    return;

  if (!mfrc522.PICC_IsNewCardPresent())
    return;
  if (!mfrc522.PICC_ReadCardSerial())
    return;

  String cardId = formatUid(&mfrc522.uid);

  if (cardId == lastCardId)
  {
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
    return;
  }

  lastCardId = cardId;
  lastCardMillis = millis();

  Serial.println("Card scanned: " + cardId);

  if (wsConnected)
  {
    showMessage("Card scanned", cardId, "Checking card...");
    sendCardScan(cardId);
  }
  else
  {
    showMessage(
        "Offline",
        "Attendance locked",
        "Teacher required");
    delay(800);
    showModeReady();
  }

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}