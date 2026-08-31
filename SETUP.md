# Vidyarthi-IoT — Exact Installation, Workspace and Operating Guide

This is the **authoritative installation and setup document**. Follow it in order on Windows.

---

## 1. What you need before starting

Install these applications:

1. **Git for Windows**
2. **Python 3.13.x**
3. **Visual Studio Code**
4. **PlatformIO IDE** extension for VS Code
5. The USB/serial driver required by your ESP32 board, if Windows does not install it automatically
6. A **PostgreSQL database** or **Supabase PostgreSQL project**

### Node.js is not required

The supplied frontend is plain HTML/JavaScript. There is no React/Vite/npm build step in this repository.

---

## 2. Final project structure

After extracting the repaired archive, the directory should be:

```text
vidyarthi-iot/
├── README.md
├── SETUP.md
├── .gitignore
├── vidyarthi-iot.code-workspace
├── backend/
├── frontend/
└── firmware/
    └── RFID_Attendance/
```

There should be **only these two Markdown documentation files** at repository level:

```text
README.md
SETUP.md
```

The project intentionally removes duplicated/scattered documentation so there is one project explanation and one setup guide.

---

## 3. Open the correct folder in VS Code

Do not open only `backend/` or only `firmware/RFID_Attendance/`.

Open the workspace file:

```text
vidyarthi-iot.code-workspace
```

### GUI method

In VS Code:

```text
File
  → Open Workspace from File...
  → vidyarthi-iot.code-workspace
```

The workspace contains four logical folders:

```text
Vidyarthi-IoT Root
Backend
Firmware (PlatformIO)
Frontend
```

This is what allows the backend, simulator, frontend and PlatformIO project to be worked on in **one VS Code window**.

---

## 4. VS Code extensions

VS Code should recommend these extensions automatically:

```text
PlatformIO IDE
Python
Pylance
```

Extension IDs:

```text
platformio.platformio-ide
ms-python.python
ms-python.vscode-pylance
```

### Install from the GUI

Open:

```text
Ctrl+Shift+X
```

Search for each extension and install it.

After installing PlatformIO, allow VS Code to reload if it asks.

---

## 5. Set PowerShell as the integrated terminal

The workspace is configured for PowerShell.

Open:

```text
Terminal → New Terminal
```

The shell should normally show something like:

```text
PS C:\...\vidyarthi-iot>
```

The workspace has:

```json
"terminal.integrated.defaultProfile.windows": "PowerShell"
```

so you do not need to configure this manually in a new installation.

---

## 6. Create the backend Python virtual environment

Open a VS Code PowerShell terminal.

From the repository root:

```powershell
cd backend
```

Create the environment:

```powershell
py -3.13 -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Upgrade pip:

```powershell
python -m pip install --upgrade pip
```

Install every backend dependency:

```powershell
pip install -r requirements.txt
```

Verify:

```powershell
python --version
pip --version
python -c "import fastapi, pydantic, psycopg, psycopg_pool, apscheduler, httpx; print('Backend dependencies OK')"
```

Expected final line:

```text
Backend dependencies OK
```

### If PowerShell blocks activation

Run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Close/reopen the terminal, then run:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
```

---

## 7. Backend dependencies

`backend/requirements.txt` is the complete runtime dependency list:

```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
websockets==13.1
apscheduler==3.10.4
httpx==0.27.2
python-dotenv==1.0.1
pydantic-settings==2.5.2
pydantic==2.9.2
psycopg[binary,pool]==3.2.3
```

Do not manually install random packages one by one unless you are troubleshooting an environment.

The normal install command is:

```powershell
pip install -r requirements.txt
```

---

## 8. Configure the backend environment

Stay in:

```text
backend/
```

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Open it:

```powershell
notepad .env
```

At minimum configure:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/postgres

ADMIN_API_KEY=replace_with_a_long_random_admin_key
TERMINAL_API_KEY=replace_with_a_long_random_terminal_key
```

The example file also contains configuration for:

```text
database pool
attendance AM/PM cutoff
PM-POSHAN allocation
ration starting stock
dropout thresholds
Rabi/Kharif month rules
Telegram bot
SMS compatibility values
security keys
CORS
notification schedule
```

Do not commit the resulting `.env`.

The root `.gitignore` already ignores:

```text
**/.env
**/.env.*
```

while allowing:

```text
**/.env.example
```

---

## 9. PostgreSQL / Supabase setup

The backend expects a normal PostgreSQL connection string.

Example form:

```text
postgresql://USER:PASSWORD@HOST:5432/postgres
```

Put the real connection string into:

```text
backend/.env
```

### What happens after you start FastAPI

The backend automatically creates its application tables:

```text
students
taps
feedback_sessions
feedback_responses
ration_stock
ration_claims
risk_flags
interventions
hardware_status
sms_log
telegram_chat_map
```

You do **not** need to manually paste the schema into a SQL console for a fresh installation.

### Initial roster

A fresh database can be seeded from:

```text
backend/data/initial_roster.json
```

Only when the `students` table is empty.

If an older installation has:

```text
backend/data/roster.csv
```

the backend can import it once and rename it to:

```text
roster.csv.migrated
```

after a successful import.

After that PostgreSQL is the runtime source of truth.

---

## 10. Start the FastAPI backend manually

Make sure the virtual environment is active:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
```

Start FastAPI:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Important:

```text
0.0.0.0
```

is used so the ESP32 can reach the machine over the LAN.

The backend should be available at:

```text
http://localhost:8000
```

Health check:

```text
http://localhost:8000/health
```

Interactive API docs:

```text
http://localhost:8000/docs
```

Dashboard:

```text
http://localhost:8000/
```

---

## 11. How to run everything in one VS Code window

The workspace is designed so every component can run in its own terminal.

### Terminal 1 — Backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2 — Simulator

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts/simulate_terminal.py
```

### Terminal 3 — PlatformIO build

From the firmware folder:

```powershell
cd firmware\RFID_Attendance
pio run
```

### Terminal 4 — PlatformIO upload

After the ESP32 is connected:

```powershell
cd firmware\RFID_Attendance
pio run --target upload
```

### Terminal 5 — ESP32 serial monitor

```powershell
cd firmware\RFID_Attendance
pio device monitor --baud 115200
```

You can switch between these terminals with the VS Code terminal selector.

---

## 12. Use the built-in VS Code tasks

The repository also contains:

```text
.vscode/tasks.json
```

Run a task with:

```text
Terminal → Run Task...
```

Available tasks:

```text
Backend: Run FastAPI
Backend: Run Simulator
Firmware: Build
Firmware: Upload
Firmware: Serial Monitor
```

This is the preferred one-window workflow once the environment has been installed.

---

## 13. Install PlatformIO

### Option A — PlatformIO extension only

Install:

```text
platformio.platformio-ide
```

Then open:

```text
firmware/RFID_Attendance/platformio.ini
```

PlatformIO will manage the framework and listed libraries.

### Option B — PlatformIO Core in PowerShell

For a command-line `pio` command outside the PlatformIO UI:

```powershell
py -3.13 -m pip install --user platformio
```

Verify:

```powershell
py -3.13 -m platformio --version
```

Then:

```powershell
cd firmware\RFID_Attendance
pio run
```

If Windows says `pio` is not recognized, use:

```powershell
py -3.13 -m platformio run
```

or use the PlatformIO terminal inside VS Code.

---

## 14. PlatformIO libraries

`firmware/RFID_Attendance/platformio.ini` declares:

```text
miguelbalboa/MFRC522
adafruit/Adafruit SSD1306
adafruit/Adafruit GFX Library
links2004/WebSockets @ ^2.4.1
bblanchon/ArduinoJson @ ^7.0.4
```

PlatformIO normally downloads these automatically the first time you build:

```powershell
cd firmware\RFID_Attendance
pio run
```

The selected framework is Arduino and the board is the ESP32 Dev Module.

---

## 15. Create ESP32 secrets

Do not put Wi-Fi or API credentials directly into `main.cpp`.

From:

```text
firmware/RFID_Attendance/
```

run:

```powershell
Copy-Item src\secrets.example.h src\secrets.h
```

Open:

```powershell
notepad src\secrets.h
```

Fill in:

```cpp
#pragma once

#define WIFI_SSID "YOUR_WIFI_NAME"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

#define BACKEND_HOST "192.168.1.100"
#define BACKEND_PORT 8000

#define DEVICE_ID "gate-1"
#define TERMINAL_API_KEY "YOUR_TERMINAL_API_KEY"
```

### Critical rule for `BACKEND_HOST`

Do **not** write:

```text
localhost
```

or:

```text
127.0.0.1
```

in the ESP32 firmware.

Those addresses refer to the ESP32 itself.

Use the LAN IP address of the computer running FastAPI, for example:

```text
192.168.1.100
```

The PC and ESP32 must be able to reach each other over the network.

The key must match:

```text
backend/.env
TERMINAL_API_KEY=...
```

---

## 16. Find the backend PC IP address

On Windows PowerShell:

```powershell
ipconfig
```

Look for the active adapter and its IPv4 address, for example:

```text
IPv4 Address. . . . . . : 192.168.1.100
```

Put that value into:

```cpp
#define BACKEND_HOST "192.168.1.100"
```

---

## 17. Windows firewall check

If the ESP32 cannot connect to FastAPI but:

```text
http://localhost:8000
```

works on the PC, Windows Firewall may be blocking inbound TCP port `8000`.

Allow Python/your FastAPI process through the firewall on the trusted/private network, or create an appropriate inbound firewall rule for TCP 8000.

Do not expose port 8000 publicly to the internet.

---

## 18. Build the firmware

Connect the ESP32 with USB.

From:

```powershell
cd firmware\RFID_Attendance
```

Run:

```powershell
pio run
```

A successful build generates PlatformIO output under:

```text
.pio/
```

That directory is ignored by Git and should not be committed.

---

## 19. Upload the firmware

With the ESP32 connected:

```powershell
pio run --target upload
```

If there are multiple serial devices, PlatformIO may need an explicit port.

List devices:

```powershell
pio device list
```

Then use the appropriate PlatformIO upload configuration or port selection supported by your board/installation.

---

## 20. Open the serial monitor

Run:

```powershell
pio device monitor --baud 115200
```

The firmware prints useful information such as:

```text
Connecting to ...
Connected, IP address: ...
WebSocket connected to backend
Button ... pressed ...
```

The serial monitor is often the fastest way to determine whether a failure is:

```text
RFID → button → Wi-Fi → WebSocket → backend
```

---

## 21. Hardware wiring

The firmware currently uses:

| Hardware | GPIO |
|---|---:|
| RC522 SS | 21 |
| RC522 RST | 22 |
| OLED SDA | 5 |
| OLED SCL | 4 |
| Button 1 | 25 |
| Button 2 | 26 |
| Button 3 | 27 |
| Button 4 | 32 |

Buttons use:

```text
INPUT_PULLUP
```

Therefore each momentary button should connect:

```text
GPIO pin ↔ push button ↔ GND
```

A pressed button reads `LOW`.

---

## 22. First end-to-end test without hardware

The project includes:

```text
backend/scripts/simulate_terminal.py
```

This lets you test WebSocket message flow without the ESP32.

First start the backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open a second terminal:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts/simulate_terminal.py
```

The simulator expects environment variables:

```text
TERMINAL_WS
TEACHER_UID
STUDENT_UID
TEACHER_ROLL
```

Example PowerShell session:

```powershell
$env:TERMINAL_WS="ws://localhost:8000/ws/terminal/gate-1"
$env:TEACHER_UID="YOUR_TEACHER_RFID_UID"
$env:STUDENT_UID="YOUR_STUDENT_RFID_UID"
$env:TEACHER_ROLL="T01"
python scripts/simulate_terminal.py
```

The simulator tests:

```text
heartbeat
teacher card scan
feedback mode
student card
rating 4
teacher card again
ration mode
student card
ration claim
```

---

## 23. Testing the dashboard

Start FastAPI:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

```text
http://localhost:8000/
```

The dashboard is served by FastAPI.

### Dashboard source rule

Edit:

```text
frontend/vidyarthi-iot-dashboard.html
```

Then synchronize the resulting file to:

```text
backend/app/static/index.html
```

The two are intentionally kept aligned so the server does not serve an old dashboard.

---

## 24. Roster search

The roster is stored in PostgreSQL.

The search endpoint is:

```text
GET /search
```

Search is performed against roster information such as:

```text
roll
name
class
RFID UID
```

This means the search result comes from the database, not from an old CSV file.

---

## 25. Attendance verification rules

Attendance requires:

1. a teacher RFID identity;
2. a teacher-started attendance mode;
3. a recognized student card;
4. backend processing.

The backend then:

- determines AM/PM using the configured cutoff;
- records the school date;
- checks for duplicates;
- handles verification/proxy heuristics;
- writes the final record.

The ESP32 is not allowed to bypass these rules.

---

## 26. Feedback testing

Use this exact flow:

```text
1. Scan teacher RFID
2. Press Button 1
3. Wait for Feedback mode
4. Scan student RFID
5. Press Button 1, 2, 3 or 4
6. Observe backend response
7. Scan another student
8. Repeat
9. Press Button 4 to exit
```

Button meaning during feedback mode:

```text
Button 1 → rating 1
Button 2 → rating 2
Button 3 → rating 3
Button 4 → rating 4
```

### Important

Because Button 4 is a rating while a student is waiting for a rating, the firmware only treats Button 4 as **Exit** when no student is currently waiting.

---

## 27. Ration testing

Use:

```text
1. Scan teacher RFID
2. Press Button 2
3. Wait for Ration mode
4. Scan a student
5. Backend checks today's claim
6. Backend checks stock
7. Backend records claim/deducts stock
8. Result appears on terminal/dashboard
```

Default allocation:

```text
100 g grain
20 g pulses
```

The dashboard/admin path can set daily initial stock.

---

## 28. Dropout-risk testing

Risk analysis can be triggered through:

```text
POST /scan
```

Flags can be viewed through:

```text
GET /flags
```

Staff follow-up is recorded through:

```text
POST /interventions
```

and viewed with:

```text
GET /interventions
```

A risk flag should always be reviewed by a responsible staff member before taking action.

---

## 29. Telegram notification setup

Development defaults are intentionally safe:

```dotenv
TELEGRAM_DRY_RUN=true
```

Do not turn on live delivery until the bot and webhook have been tested.

Relevant configuration:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_DRY_RUN=true
TELEGRAM_WEBHOOK_SECRET=
```

Webhook endpoint:

```text
POST /webhook
```

Notification logs:

```text
GET /log
```

Status:

```text
GET /status
```

Batch trigger:

```text
POST /trigger-batch
```

---

## 30. CORS

For a backend-served dashboard, CORS does not need to be opened broadly.

For local development, the example is:

```dotenv
CORS_ORIGINS=*
```

For a real deployment, use explicit trusted origins instead of `*`.

Example form:

```dotenv
CORS_ORIGINS=http://192.168.1.100:8000
```

---

## 31. Security checklist before deployment

Never deploy with:

```text
live secrets in Git
weak admin keys
weak terminal keys
public PostgreSQL
unrestricted CORS
publicly exposed FastAPI port
```

Use:

```text
strong ADMIN_API_KEY
strong TERMINAL_API_KEY
private database connectivity
restricted CORS
private/trusted LAN or secure gateway
regular database backups
```

The `.gitignore` already excludes:

```text
.env
.venv
.pio
secrets.h
```

---

## 32. Verify what Git will ignore

From repository root:

```powershell
git status --short --ignored
```

You should see local secrets/build/runtime folders ignored when they exist, including:

```text
backend/.env
backend/.venv/
firmware/RFID_Attendance/.pio/
firmware/RFID_Attendance/src/secrets.h
```

Do not force-add them with:

```text
git add -f
```

---

## 33. Clean rebuild procedures

### Python environment reset

From repository root:

```powershell
Remove-Item -Recurse -Force backend\.venv
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### PlatformIO clean rebuild

From firmware directory:

```powershell
pio run --target clean
pio run
```

If dependency installation is corrupted, deleting the local `.pio` directory and rebuilding is acceptable:

```powershell
Remove-Item -Recurse -Force .pio
pio run
```

---

## 34. Common problems and exact fixes

### Problem: `python` is not recognized

Try:

```powershell
py -3.13 --version
```

If that works, use:

```powershell
py -3.13 -m venv .venv
```

and:

```powershell
py -3.13 -m pip install -r requirements.txt
```

### Problem: PowerShell activation is blocked

Run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Problem: `No module named app`

You are probably not inside `backend/`.

Correct:

```powershell
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Problem: `DATABASE_URL is not configured`

Check:

```text
backend/.env
```

and make sure it contains:

```dotenv
DATABASE_URL=...
```

Then restart FastAPI.

### Problem: database connection fails

Check:

1. host is correct;
2. username/password are correct;
3. PostgreSQL/Supabase is reachable;
4. the connection string includes the correct port;
5. the machine has internet/LAN connectivity as required.

### Problem: ESP32 cannot reach backend

Check:

```text
1. FastAPI is running
2. FastAPI is bound to 0.0.0.0
3. BACKEND_HOST is the PC LAN IP
4. port is 8000
5. PC firewall permits the connection
6. ESP32 and PC can reach each other
7. TERMINAL_API_KEY matches
```

Do not use:

```text
localhost
127.0.0.1
```

as the ESP32 backend host.

### Problem: PlatformIO command not found

Use:

```powershell
py -3.13 -m platformio --version
```

or install:

```powershell
py -3.13 -m pip install --user platformio
```

### Problem: no ESP32 upload port

Run:

```powershell
pio device list
```

Then check:

- USB cable supports data;
- correct board is connected;
- driver is installed;
- no other serial monitor has the port open.

### Problem: dashboard opens but is stale

Make sure the source:

```text
frontend/vidyarthi-iot-dashboard.html
```

and server copy:

```text
backend/app/static/index.html
```

are synchronized.

### Problem: same student gets ration twice

This should be blocked by:

```text
UNIQUE(school_date, roll)
```

in `ration_claims`.

Check the backend logs and database if you see an unexpected duplicate.

### Problem: same student can submit repeated feedback

This should be blocked by:

```text
UNIQUE(session_id, roll)
```

in `feedback_responses`.

---

## 35. Recommended order for first successful run

Perform the first setup in this exact sequence:

```text
1. Install Git
2. Install Python 3.13
3. Install VS Code
4. Install PlatformIO + Python/Pylance extensions
5. Open vidyarthi-iot.code-workspace
6. Open PowerShell terminal
7. Create backend/.venv
8. Activate backend/.venv
9. pip install -r backend/requirements.txt
10. Copy backend/.env.example → backend/.env
11. Configure DATABASE_URL
12. Configure ADMIN_API_KEY
13. Configure TERMINAL_API_KEY
14. Start FastAPI
15. Open /health
16. Open /docs
17. Open /
18. Run terminal simulator
19. Confirm WebSocket workflow
20. Copy firmware secrets.example.h → secrets.h
21. Configure Wi-Fi
22. Configure BACKEND_HOST
23. Configure TERMINAL_API_KEY
24. Connect ESP32
25. pio run
26. pio run --target upload
27. pio device monitor --baud 115200
28. Test teacher card
29. Test attendance
30. Test feedback
31. Test ration
32. Test dashboard updates
```

---

## 36. One-command reference sheet

### Start backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run simulator

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python scripts/simulate_terminal.py
```

### Install backend dependencies

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Create backend environment

```powershell
cd backend
Copy-Item .env.example .env
```

### Create firmware secrets

```powershell
cd firmware\RFID_Attendance
Copy-Item src\secrets.example.h src\secrets.h
```

### PlatformIO build

```powershell
cd firmware\RFID_Attendance
pio run
```

### PlatformIO upload

```powershell
cd firmware\RFID_Attendance
pio run --target upload
```

### Serial monitor

```powershell
cd firmware\RFID_Attendance
pio device monitor --baud 115200
```

### List serial devices

```powershell
pio device list
```

### PlatformIO version

```powershell
py -3.13 -m platformio --version
```

### Check FastAPI

```text
http://localhost:8000/health
```

### API docs

```text
http://localhost:8000/docs
```

### Dashboard

```text
http://localhost:8000/
```

---

## 37. Final deployment checklist

Before calling the system ready:

```text
[ ] PostgreSQL/Supabase connection tested
[ ] backend/.env created
[ ] ADMIN_API_KEY set
[ ] TERMINAL_API_KEY set
[ ] CORS reviewed
[ ] FastAPI starts without errors
[ ] /health returns {"status":"ok"}
[ ] /docs opens
[ ] dashboard opens
[ ] roster is present in students
[ ] roster search works
[ ] simulator completes its workflow
[ ] firmware secrets.h created
[ ] Wi-Fi works on ESP32
[ ] BACKEND_HOST points to the server PC
[ ] PlatformIO build succeeds
[ ] firmware uploads
[ ] serial monitor shows connection
[ ] teacher RFID is recognized
[ ] attendance works
[ ] feedback works
[ ] ration works
[ ] duplicate ration is blocked
[ ] duplicate feedback is blocked
[ ] hardware status updates
[ ] dropout/risk scan tested
[ ] intervention recording tested
[ ] notifications kept in dry-run until verified
[ ] no secret files are tracked by Git
[ ] database backups/retention policy established
```

---

## 38. Important source-of-truth reminders

### Backend configuration

Edit:

```text
backend/.env
```

not `config.py`.

### Firmware configuration

Edit:

```text
firmware/RFID_Attendance/src/secrets.h
```

not `main.cpp` for Wi-Fi/API secrets.

### Frontend

Edit:

```text
frontend/vidyarthi-iot-dashboard.html
```

and keep:

```text
backend/app/static/index.html
```

synchronized.

### Roster

Runtime authority:

```text
PostgreSQL → students
```

Seed input:

```text
backend/data/initial_roster.json
```

Legacy migration input:

```text
backend/data/roster.csv
```

only when the runtime roster is empty.

---

## 39. When the system is running

You should have this overall flow:

```text
VS Code
│
├── Terminal 1 → FastAPI backend
│                  │
│                  ├── PostgreSQL
│                  ├── REST API
│                  ├── WebSocket
│                  ├── Scheduler
│                  └── Dashboard
│
├── Terminal 2 → Terminal simulator
│
├── Terminal 3 → PlatformIO build/upload
│
└── Terminal 4 → ESP32 serial monitor

ESP32
│
├── RC522
├── OLED
├── Buttons
└── Wi-Fi
      │
      ▼
FastAPI
      │
      ▼
PostgreSQL
      │
      ├── Attendance
      ├── Feedback
      ├── PM-POSHAN
      ├── Risk flags
      ├── Interventions
      ├── Hardware status
      └── Notification logs
```

That is the intended complete local-development setup.
