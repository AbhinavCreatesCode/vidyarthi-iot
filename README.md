# Vidyarthi-IoT

## 1. Project overview

**Vidyarthi-IoT** is a school attendance and welfare management system that connects an ESP32-based RFID terminal, a FastAPI backend, a PostgreSQL/Supabase database, and a browser dashboard.

The project was designed to move important school workflows from disconnected/manual processes into one controlled system:

- attendance capture using RFID cards;
- teacher-authenticated attendance sessions;
- feedback collection from students;
- PM-POSHAN/ration distribution tracking;
- duplicate/invalid attendance handling and proxy-pattern marking;
- student roster management and database search;
- dropout/equity early-warning signals;
- intervention recording for at-risk students;
- guardian notification support through Telegram;
- live terminal and backend status monitoring;
- a single dashboard for staff to view the resulting data.

The important design decision is that the **backend is authoritative**. The ESP32 is an interface device: it reads cards, detects button presses, displays status, and sends events. It does not decide whether a teacher is valid, whether attendance should be written, whether a ration claim is allowed, or how much stock remains.

---

## 2. Why this project was made

The project addresses several practical problems that occur when school records are handled separately.

### 2.1 Attendance is easy to record incorrectly

Paper registers and loosely controlled digital forms can lead to:

- repeated entries;
- unclear timestamps;
- manual transcription mistakes;
- attendance being marked without an authenticated teacher session;
- difficult verification after the event.

Vidyarthi-IoT ties attendance to an RFID identity and an active teacher-started session. The backend stores the final attendance record.

### 2.2 Proxy attendance should be detectable

A student terminal can observe a sequence of rapid scans that may deserve review. The backend contains verification logic so suspicious patterns can be marked rather than silently treated as fully verified attendance.

This is an **early verification signal**, not an accusation. Staff still have to review questionable records.

### 2.3 Feedback should be collected in the same place as attendance

Student feedback is often collected separately from daily school operations. The terminal reuses the teacher RFID authentication and physical buttons so a teacher can start feedback mode without another application.

### 2.4 Ration / PM-POSHAN distribution needs accountability

Ration distribution has two important requirements:

1. a student should not be issued the configured daily entitlement twice;
2. the system should show stock consumed and stock remaining.

The project therefore records a unique daily ration claim for each student and updates stock in the database.

### 2.5 Early warning should happen before a student disappears completely

The dropout-risk component looks at recent attendance patterns and configurable seasonal/month-based rules. The purpose is to surface students who may need attention early enough for a staff member to investigate.

The risk flag is a **decision-support signal**, not an automatic determination that a student will drop out.

### 2.6 Staff need one source of truth

The dashboard combines roster search, attendance information, feedback, ration data, risk flags, interventions, hardware status and notification information. PostgreSQL is the runtime source of truth rather than separate CSV/SQLite files.

### 2.7 Hardware should be observable

An RFID terminal can fail while the web application appears healthy. Heartbeat messages let the backend store terminal online status, Wi-Fi RSSI and queue information so staff can distinguish a hardware/network problem from a data problem.

### 2.8 The project should be usable as a real development workspace

The repository is arranged so the backend, firmware and frontend can be opened in one VS Code workspace. Integrated tasks provide separate terminals for:

- FastAPI;
- the terminal simulator;
- PlatformIO firmware build;
- PlatformIO upload;
- serial monitoring.

---

## 3. What the project solves

| Problem | Project solution |
|---|---|
| Manual RFID/attendance handling | ESP32 + RC522 + FastAPI |
| Uncontrolled attendance writes | Teacher-authenticated backend mode |
| Duplicate attendance | Database lookup/duplicate detection |
| Suspicious rapid scan patterns | Verification/proxy heuristics |
| Separate student feedback process | Feedback mode on same terminal |
| Double ration collection | Unique daily ration claim |
| Poor ration accountability | Persistent stock + claim records |
| Fragmented student roster | PostgreSQL roster |
| Difficult roster lookup | PostgreSQL search endpoint/dashboard search |
| Late identification of attendance problems | Dropout-risk heuristics |
| No record of follow-up | Intervention table |
| Hard-to-see hardware failures | Heartbeat + hardware status |
| Manual/fragmented notifications | Scheduled notification service + Telegram |
| Difficult local development | VS Code multi-root workspace + tasks |

---

## 4. Project goals

The implementation follows these goals:

1. **Centralize authoritative data.** PostgreSQL stores the runtime records.
2. **Keep decisions on the server.** Security-sensitive business rules stay in FastAPI services.
3. **Make hardware simple.** The ESP32 should be an input/output terminal, not a second database.
4. **Make important actions traceable.** Attendance, ration, feedback and interventions are persisted.
5. **Prevent accidental double actions.** Database uniqueness and business rules enforce one-time operations where required.
6. **Support real-world recovery.** The server can seed the initial roster and migrate a legacy CSV once.
7. **Keep secrets outside source control.** `.env` and firmware `secrets.h` are ignored.
8. **Make testing possible without the ESP32.** `backend/scripts/simulate_terminal.py` exercises the WebSocket workflow.
9. **Keep the user interface simple.** The frontend is plain HTML/JavaScript served by FastAPI.
10. **Make deployment understandable.** The project includes an exact Windows + VS Code + PlatformIO setup guide.

---

## 5. Guidelines and engineering principles followed

### 5.1 Backend-authoritative operation

The terminal sends events; the backend validates and commits them. This prevents a modified firmware client from becoming an uncontrolled source of attendance or ration records.

### 5.2 Least privilege and explicit authentication

There are two configurable application keys:

- `ADMIN_API_KEY` for administrative HTTP/dashboard actions;
- `TERMINAL_API_KEY` for ESP32 terminal WebSocket access.

Security-sensitive operations are protected on the server.

### 5.3 No secrets in the repository

Real database passwords, bot tokens, Wi-Fi passwords and API keys belong in:

- `backend/.env`
- `firmware/RFID_Attendance/src/secrets.h`

Only example files are distributed.

### 5.4 One runtime source of truth

The `students` table is the authoritative runtime roster. `data/initial_roster.json` is only a seed for a fresh deployment. An older `data/roster.csv` is a one-time migration input and is renamed after a successful migration.

### 5.5 Data integrity at the database layer

The schema uses primary keys, unique constraints, foreign keys and checks such as:

- unique RFID UID;
- valid `role` values;
- valid attendance session (`AM`/`PM`);
- feedback rating `1..4`;
- unique ration claim per student and school date.

The backend should still perform user-friendly validation before relying on the database constraints.

### 5.6 Fail closed for sensitive workflows

Attendance, feedback and ration modes require a live backend session. The terminal is not allowed to continue sensitive operations offline because the backend must remain the authority for identity and business rules.

### 5.7 Privacy and appropriate use

Student and guardian information should only be used for the school's legitimate workflows. Risk flags and suspicious attendance markers are intended for human review and support, not automatic punishment.

### 5.8 Auditability

Operational records contain timestamps, source/terminal information and the relevant student/teacher identifiers needed for later review.

### 5.9 Simple, maintainable UI

The frontend is intentionally a static HTML dashboard instead of a separate Node build system. This reduces installation steps and makes the application easier to deploy in a controlled school environment.

---

## 6. High-level architecture

```text
                    ┌─────────────────────────────┐
                    │ PostgreSQL / Supabase       │
                    │-----------------------------│
                    │ students                    │
                    │ taps                        │
                    │ feedback_*                  │
                    │ ration_*                    │
                    │ risk_flags / interventions  │
                    │ hardware_status              │
                    │ sms_log / telegram_chat_map │
                    └──────────────┬──────────────┘
                                   │
                              SQL / psycopg
                                   │
┌──────────────────┐     WebSocket / REST     ┌───────────────────────┐
│ ESP32 Terminal   │◄────────────────────────►│ FastAPI Backend       │
│------------------│                          │-----------------------│
│ RC522 RFID       │                          │ app/main.py           │
│ OLED             │                          │ routers/              │
│ 4 buttons        │                          │ services/             │
│ Wi-Fi            │                          │ database.py           │
└──────────────────┘                          │ security.py           │
                                              │ static/index.html     │
                                              └───────────┬───────────┘
                                                          │
                                               Browser REST/WebSocket
                                                          │
                                              ┌───────────▼───────────┐
                                              │ School Dashboard      │
                                              │ frontend/*.html       │
                                              └───────────────────────┘

Optional notification path:
Telegram user → Telegram webhook → telegram_chat_map
             → scheduled notification service → Telegram Bot API
```

---

## 7. Repository structure

```text
vidyarthi-iot/
│
├── README.md
├── SETUP.md
├── .gitignore
├── vidyarthi-iot.code-workspace
│
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── roster_store.py
│   │   ├── security.py
│   │   ├── ws_manager.py
│   │   │
│   │   ├── routers/
│   │   │   ├── attendance.py
│   │   │   ├── dropout.py
│   │   │   ├── feedback.py
│   │   │   ├── hardware.py
│   │   │   ├── ration.py
│   │   │   ├── roster.py
│   │   │   ├── sms.py
│   │   │   ├── telegram_webhook.py
│   │   │   └── ws.py
│   │   │
│   │   ├── services/
│   │   │   ├── attendance.py
│   │   │   ├── daily_summary.py
│   │   │   ├── dropout_risk.py
│   │   │   ├── feedback.py
│   │   │   ├── hardware.py
│   │   │   ├── poshan.py
│   │   │   ├── scheduler.py
│   │   │   └── sms_gateway.py
│   │   │
│   │   └── static/
│   │       └── index.html
│   │
│   ├── data/
│   │   └── initial_roster.json
│   │
│   └── scripts/
│       └── simulate_terminal.py
│
├── frontend/
│   └── vidyarthi-iot-dashboard.html
│
└── firmware/
    └── RFID_Attendance/
        ├── platformio.ini
        ├── include/
        ├── lib/
        ├── src/
        │   ├── main.cpp
        │   └── secrets.example.h
        └── test/
```

### What each area does

**`backend/app/main.py`**  
Builds the FastAPI application, configures CORS, initializes PostgreSQL, starts/stops the scheduler and serves the dashboard.

**`backend/app/config.py`**  
Loads `.env` settings so configuration is centralized.

**`backend/app/database.py`**  
Creates the PostgreSQL schema, opens the connection pool and handles initial roster migration/seeding.

**`backend/app/roster_store.py`**  
Provides PostgreSQL-backed roster search/list/get/update/delete operations.

**`backend/app/routers/`**  
HTTP and WebSocket entry points. Routers validate requests and delegate business logic.

**`backend/app/services/`**  
Contains the application behavior for attendance, feedback, ration, dropout analysis, notifications, hardware status and scheduled work.

**`backend/app/ws_manager.py`**  
Manages connected WebSocket clients and broadcasting.

**`backend/app/static/index.html`**  
The copy of the dashboard that FastAPI serves at `/`.

**`frontend/vidyarthi-iot-dashboard.html`**  
The editable/authoritative frontend source. Keep it synchronized with the backend-served copy.

**`backend/data/initial_roster.json`**  
Fresh-install roster seed. It is not the runtime database.

**`backend/scripts/simulate_terminal.py`**  
Sends the same style of WebSocket messages as the ESP32 for terminal-free testing.

**`firmware/RFID_Attendance/src/main.cpp`**  
ESP32 application: RFID reading, OLED UI, buttons, Wi-Fi, WebSocket messaging and terminal state.

**`firmware/RFID_Attendance/src/secrets.h`**  
Local-only hardware/network credentials created from `secrets.example.h`.

---

## 8. End-to-end working

### 8.1 Application startup

When FastAPI starts:

1. `.env` is loaded.
2. PostgreSQL connection settings are read.
3. The connection pool is created.
4. Database tables are created if absent.
5. Initial roster data is seeded if `students` is empty.
6. The scheduler starts.
7. REST and WebSocket routers become available.
8. The dashboard is served from `/`.

Health check:

```text
GET http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Interactive API documentation:

```text
http://localhost:8000/docs
```

### 8.2 ESP32 startup

The ESP32:

1. initializes RC522, OLED and buttons;
2. connects to Wi-Fi;
3. configures India Standard Time (`UTC+05:30`) for its local clock;
4. connects to `/ws/terminal/{device_id}`;
5. sends periodic heartbeat information;
6. waits for an RFID card.

### 8.3 Teacher authentication

```text
Teacher RFID
    ↓
ESP32 card_scan
    ↓
FastAPI looks up UID in students
    ↓
role == teacher ?
    ├── No → reject
    └── Yes
          ↓
       MODE_SELECT
```

The terminal then shows:

```text
1:Fdbk 2:Ration 3:Attend
```

### 8.4 Attendance flow

```text
Teacher scans
   ↓
Teacher verified
   ↓
Press Button 3
   ↓
start_mode(attendance)
   ↓
Backend opens authoritative attendance session
   ↓
Student scans
   ↓
card_result(student)
   ↓
tap event
   ↓
Backend:
  - verifies active teacher session
  - finds student
  - chooses AM/PM
  - checks duplicates
  - checks verification/proxy heuristics
  - stores tap
   ↓
Result sent to terminal
   ↓
Dashboard receives live event
```

Attendance mode ends with Button 4.

### 8.5 Feedback flow

```text
Teacher verified
   ↓
Button 1
   ↓
start_mode(feedback)
   ↓
Student RFID
   ↓
student shown on OLED
   ↓
Button 1..4
   ↓
rating 1..4
   ↓
Backend stores response
   ↓
Dashboard summary updates
```

One student can provide only one response in the same feedback session because of the database uniqueness rule.

### 8.6 Ration flow

```text
Teacher verified
   ↓
Button 2
   ↓
start_mode(ration)
   ↓
Student RFID
   ↓
ration_claim
   ↓
Backend:
  - validates student
  - checks today's claim uniqueness
  - checks stock
  - deducts grain/pulses
  - stores claim
   ↓
Terminal result + dashboard update
```

Default allocation is:

- **100 g food grains / student / day**
- **20 g pulses / student / day**

These values are configurable.

### 8.7 Dropout/equity workflow

The scheduler runs the configured background jobs. The dropout service examines recent attendance and configurable month-based patterns. It stores `risk_flags` for cases that cross the configured rules.

Staff can then record a follow-up in `interventions`.

This is deliberately a **human-in-the-loop** workflow:

```text
Attendance history
      ↓
Risk heuristic
      ↓
Risk flag
      ↓
Staff review
      ↓
Optional intervention
```

### 8.8 Notifications

The daily notification service can assemble guardian messages from the stored student/attendance context.

Telegram support uses:

```text
Telegram → webhook → telegram_chat_map
                     ↓
              notification service
                     ↓
             Telegram Bot API
```

Dry-run is enabled by default so notifications are not accidentally sent during development.

### 8.9 Hardware monitoring

The ESP32 sends a heartbeat approximately every 20 seconds:

```json
{
  "type": "heartbeat",
  "data": {
    "rssi": -54,
    "queue": 0
  }
}
```

The backend records the latest terminal state in `hardware_status` and publishes status to the dashboard.

---

## 9. Web/API surface

Current important endpoints are:

```text
GET  /health

GET  /search
DELETE /{roll}

POST /attendance/tap
GET  /attendance/verification
GET  /attendance/recent
GET  /poshan/today

GET  /summary

GET  /today
POST /stock

GET  /flags
POST /scan
POST /interventions
GET  /interventions

GET  /status
POST /trigger-batch
GET  /log

POST /webhook

GET  /hardware/status

WS   /ws/dashboard
WS   /ws/terminal/{device_id}
```

FastAPI exposes the full request/response schema automatically at:

```text
http://localhost:8000/docs
```

---

## 10. Database model

### `students`
School roster and RFID identity:

- `roll`
- `name`
- `class_name`
- `rfid_uid`
- `guardian_phone`
- `role`

### `taps`
Attendance events:

- student identity;
- AM/PM session;
- timestamp;
- school date;
- verification state;
- source.

### `feedback_sessions`
Teacher-started feedback sessions.

### `feedback_responses`
Student ratings for a feedback session.

### `ration_stock`
Daily available grain and pulses.

### `ration_claims`
One student ration claim per school date.

### `risk_flags`
Early-warning results.

### `interventions`
Staff follow-up notes.

### `hardware_status`
Latest terminal health.

### `sms_log`
Notification delivery history.

### `telegram_chat_map`
Telegram chat registration mapped to a guardian phone identifier.

---

## 11. Important operational rules

1. The backend, not the ESP32, decides whether a card is a teacher or student.
2. Sensitive modes require a live backend connection.
3. A student cannot claim the same day's ration twice.
4. A feedback session allows one rating per student.
5. Attendance records are stored in PostgreSQL, not a local CSV.
6. `initial_roster.json` seeds the database only when the roster table is empty.
7. The dashboard source is `frontend/vidyarthi-iot-dashboard.html`; its backend copy must remain synchronized.
8. `.env` and `src/secrets.h` must never be committed.
9. Risk flags and proxy indicators are for review, not automatic disciplinary decisions.
10. The supplied notification system defaults to dry-run for safe development.

---

## 12. Development and deployment boundary

### Development

Use:

- Windows;
- VS Code;
- PowerShell;
- Python virtual environment;
- local FastAPI server;
- Supabase/PostgreSQL;
- PlatformIO;
- terminal simulator.

### Hardware deployment

The ESP32 needs:

- Wi-Fi access;
- RC522 reader;
- SSD1306 OLED;
- four buttons;
- backend host reachable over the network;
- correct terminal API key.

### Production

Before deploying to an actual school network:

- use a strong admin key and terminal key;
- restrict CORS to the actual dashboard origin;
- protect the database connection string;
- avoid exposing PostgreSQL directly to the public internet;
- configure backups;
- configure real notification credentials only after testing;
- review privacy/retention requirements for student and guardian data;
- test the exact RFID and wiring setup;
- establish who is responsible for reviewing risk/proxy alerts.
