"""
PostgreSQL database layer for the Vidyarthi-IoT backend.

The application uses Supabase PostgreSQL through DATABASE_URL.
The public API intentionally stays close to the old SQLite layer:
    - init_db()
    - get_db()

All application tables, including sms_log and telegram_chat_map,
are created automatically on startup.
"""

from contextlib import contextmanager
import csv
import json
import logging
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

logger = logging.getLogger("vidyarthi.database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    roll TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    class_name TEXT NOT NULL,
    rfid_uid TEXT NOT NULL UNIQUE,
    guardian_phone TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'teacher'))
);
CREATE INDEX IF NOT EXISTS idx_students_name
    ON students(name);
CREATE INDEX IF NOT EXISTS idx_students_role
    ON students(role);


CREATE TABLE IF NOT EXISTS taps (
    id BIGSERIAL PRIMARY KEY,
    roll TEXT NOT NULL,
    name TEXT NOT NULL,
    session TEXT NOT NULL CHECK (session IN ('AM', 'PM')),
    ts TEXT NOT NULL,
    school_date TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'terminal'
);
CREATE INDEX IF NOT EXISTS idx_taps_roll_date
    ON taps(roll, school_date);
CREATE INDEX IF NOT EXISTS idx_taps_date
    ON taps(school_date);


CREATE TABLE IF NOT EXISTS feedback_sessions (
    id BIGSERIAL PRIMARY KEY,
    teacher_roll TEXT NOT NULL,
    teacher_name TEXT NOT NULL,
    terminal_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_feedback_sessions_date
    ON feedback_sessions(started_at);


CREATE TABLE IF NOT EXISTS feedback_responses (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES feedback_sessions(id),
    roll TEXT NOT NULL,
    name TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 4),
    ts TEXT NOT NULL,
    UNIQUE(session_id, roll)
);
CREATE INDEX IF NOT EXISTS idx_feedback_responses_session
    ON feedback_responses(session_id);


CREATE TABLE IF NOT EXISTS ration_stock (
    school_date TEXT PRIMARY KEY,
    initial_grain_kg DOUBLE PRECISION NOT NULL,
    initial_pulses_kg DOUBLE PRECISION NOT NULL,
    updated_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS ration_claims (
    id BIGSERIAL PRIMARY KEY,
    school_date TEXT NOT NULL,
    roll TEXT NOT NULL,
    name TEXT NOT NULL,
    teacher_roll TEXT NOT NULL,
    grain_kg DOUBLE PRECISION NOT NULL,
    pulses_kg DOUBLE PRECISION NOT NULL,
    ts TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'terminal',
    UNIQUE(school_date, roll)
);
CREATE INDEX IF NOT EXISTS idx_ration_claims_date
    ON ration_claims(school_date);


CREATE TABLE IF NOT EXISTS risk_flags (
    id BIGSERIAL PRIMARY KEY,
    roll TEXT NOT NULL,
    name TEXT NOT NULL,
    pattern TEXT NOT NULL,
    missed INTEGER NOT NULL,
    risk TEXT NOT NULL CHECK (risk IN ('low', 'med', 'high')),
    created_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS interventions (
    id BIGSERIAL PRIMARY KEY,
    roll TEXT,
    student TEXT NOT NULL,
    note TEXT NOT NULL,
    ts TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS hardware_status (
    device_id TEXT PRIMARY KEY,
    rssi INTEGER,
    online INTEGER NOT NULL DEFAULT 1,
    queue INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS sms_log (
    id BIGSERIAL PRIMARY KEY,
    phone TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL,
    ts TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS telegram_chat_map (
    phone TEXT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    ts TEXT NOT NULL
);
"""


_db_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _db_pool

    if _db_pool is None:
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is not configured. "
                "Add your Supabase PostgreSQL connection string to .env."
            )

        _db_pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=getattr(settings, "db_pool_min_size", 1),
            max_size=getattr(settings, "db_pool_max_size", 8),
            kwargs={"row_factory": dict_row},
            open=True,
        )

    return _db_pool


def _migrate_legacy_roster(conn) -> None:
    """
    One-time migration for projects that still have data/roster.csv.

    PostgreSQL remains the runtime source of truth. The legacy CSV is only
    read when the students table is empty, then renamed after a successful
    import so it cannot silently become a second source of truth.
    """
    count = conn.execute("SELECT COUNT(*) AS count FROM students").fetchone()["count"]
    if count:
        return

    data_dir = Path(settings.data_dir)
    legacy_path = data_dir / "roster.csv"
    seed_path = data_dir / "initial_roster.json"

    if legacy_path.exists():
        source_rows = []
        with legacy_path.open(newline="", encoding="utf-8") as f:
            source_rows = list(csv.DictReader(f))
        source_kind = "legacy CSV"
    elif seed_path.exists():
        with seed_path.open(encoding="utf-8") as f:
            source_rows = json.load(f)
        source_kind = "initial roster seed"
    else:
        return

    imported = 0
    for row in source_rows:
            roll = (row.get("roll") or "").strip()
            name = (row.get("name") or "").strip()
            class_name = (row.get("class") or "").strip()
            rfid_uid = (row.get("rfid_uid") or "").strip().upper()
            guardian_phone = (row.get("guardian_phone") or "").strip()
            role = (row.get("role") or "student").strip().lower()

            if not roll or not name or not class_name or not rfid_uid:
                continue
            if role not in ("student", "teacher"):
                role = "student"

            conn.execute(
                """
                INSERT INTO students
                    (roll, name, class_name, rfid_uid, guardian_phone, role)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (roll) DO NOTHING
                """,
                (roll, name, class_name, rfid_uid, guardian_phone, role),
            )
            imported += 1

    if imported:
        if legacy_path.exists():
            archived_path = legacy_path.with_name("roster.csv.migrated")
            try:
                legacy_path.replace(archived_path)
                logger.info(
                    "Migrated %d roster records from legacy CSV to PostgreSQL; archived %s",
                    imported,
                    archived_path,
                )
            except OSError:
                logger.warning(
                    "Migrated %d roster records from legacy CSV to PostgreSQL, but could not archive %s",
                    imported,
                    legacy_path,
                )
        else:
            logger.info(
                "Seeded %d initial roster records into PostgreSQL from %s",
                imported,
                seed_path,
            )


def init_db() -> None:
    """
    Create all application tables in Supabase PostgreSQL and migrate the
    legacy CSV roster once, when present.
    """
    pool = _get_pool()

    with pool.connection() as conn:
        conn.execute(SCHEMA)
        _migrate_legacy_roster(conn)
        conn.commit()


@contextmanager
def get_db():
    """
    Yield a PostgreSQL connection.

    Existing application code can continue using:
        with get_db() as db:
            row = db.execute(...).fetchone()
    """
    pool = _get_pool()

    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def close_db_pool() -> None:
    """
    Close the PostgreSQL connection pool during application shutdown.
    """
    global _db_pool

    if _db_pool is not None:
        _db_pool.close()
        _db_pool = None
