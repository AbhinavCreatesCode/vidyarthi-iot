"""PM-POSHAN ration distribution and stock tracking.

Each successful student RFID claim deducts the configured per-child ration
from the day's remaining stock. The dashboard can therefore show both the
remaining stock and exactly which roster students have not claimed their
ration yet.
"""

from datetime import date, datetime

from app.config import settings
from app.database import get_db
from app.roster_store import get_by_uid, get_by_roll, list_students


def today_str() -> str:
    return date.today().isoformat()


def _ensure_stock(conn, school_date: str) -> dict:
    row = conn.execute(
        "SELECT * FROM ration_stock WHERE school_date = %s", (school_date,)
    ).fetchone()
    if row:
        return dict(row)

    # A useful default for a new day: enough stock for every student in the
    # roster, using the same per-child quantities already configured.
    student_count = sum(
        1 for s in list_students() if s.get("role", "student") == "student"
    )
    grain = (
        settings.ration_initial_grain_kg
        if settings.ration_initial_grain_kg > 0
        else student_count * settings.grain_g_per_child / 1000
    )

    pulses = (
        settings.ration_initial_pulses_kg
        if settings.ration_initial_pulses_kg > 0
        else student_count * settings.pulses_g_per_child / 1000
    )

    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO ration_stock
           (school_date, initial_grain_kg, initial_pulses_kg, updated_at)
           VALUES (%s,%s,%s,%s)""",
        (school_date, grain, pulses, now),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM ration_stock WHERE school_date = %s", (school_date,)
    ).fetchone()
    return dict(row)


def set_stock(
    initial_grain_kg: float,
    initial_pulses_kg: float,
    school_date: str | None = None,
) -> dict:
    school_date = school_date or today_str()

    if initial_grain_kg < 0 or initial_pulses_kg < 0:
        raise ValueError("ration stock cannot be negative")

    now = datetime.now().isoformat()

    with get_db() as conn:
        claims = conn.execute(
            "SELECT COALESCE(SUM(grain_kg),0) AS grain, "
            "COALESCE(SUM(pulses_kg),0) AS pulses "
            "FROM ration_claims WHERE school_date = %s",
            (school_date,),
        ).fetchone()

        if initial_grain_kg + 1e-9 < float(
            claims["grain"]
        ) or initial_pulses_kg + 1e-9 < float(claims["pulses"]):
            raise ValueError(
                "initial stock cannot be lower than ration already distributed"
            )

        conn.execute(
            """INSERT INTO ration_stock
               (school_date, initial_grain_kg, initial_pulses_kg, updated_at)
               VALUES (%s,%s,%s,%s)
               ON CONFLICT(school_date) DO UPDATE SET
                 initial_grain_kg=excluded.initial_grain_kg,
                 initial_pulses_kg=excluded.initial_pulses_kg,
                 updated_at=excluded.updated_at""",
            (school_date, initial_grain_kg, initial_pulses_kg, now),
        )
        conn.commit()

    return status(school_date)


def claim_ration(
    uid: str | None,
    roll: str | None,
    teacher_roll: str,
    school_date: str | None = None,
) -> dict:
    school_date = school_date or today_str()

    student = get_by_uid(uid) if uid else (get_by_roll(roll) if roll else None)

    if not student:
        raise ValueError("student card not found")

    if student.get("role", "student") != "student":
        raise ValueError("teacher cards cannot claim student ration")

    grain = settings.grain_g_per_child / 1000
    pulses = settings.pulses_g_per_child / 1000
    now = datetime.now().isoformat()

    with get_db() as conn:
        stock = _ensure_stock(conn, school_date)

        claimed = conn.execute(
            "SELECT id FROM ration_claims " "WHERE school_date = %s AND roll = %s",
            (school_date, student["roll"]),
        ).fetchone()

        if claimed:
            raise ValueError("ration already collected today")

        used = conn.execute(
            """SELECT COALESCE(SUM(grain_kg),0) AS grain,
                      COALESCE(SUM(pulses_kg),0) AS pulses
               FROM ration_claims WHERE school_date = %s""",
            (school_date,),
        ).fetchone()

        remaining_grain = float(stock["initial_grain_kg"]) - float(used["grain"])
        remaining_pulses = float(stock["initial_pulses_kg"]) - float(used["pulses"])

        if remaining_grain + 1e-9 < grain or remaining_pulses + 1e-9 < pulses:
            raise ValueError("insufficient ration stock")

        conn.execute(
            """INSERT INTO ration_claims
               (school_date, roll, name, teacher_roll, grain_kg, pulses_kg, ts, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                school_date,
                student["roll"],
                student["name"],
                teacher_roll,
                grain,
                pulses,
                now,
                "terminal",
            ),
        )

        conn.execute(
            "UPDATE ration_stock SET updated_at = %s WHERE school_date = %s",
            (now, school_date),
        )
        conn.commit()

    return {
        "school_date": school_date,
        "roll": student["roll"],
        "name": student["name"],
        "grain_kg": grain,
        "pulses_kg": pulses,
        "remaining_grain_kg": remaining_grain - grain,
        "remaining_pulses_kg": remaining_pulses - pulses,
    }


def status(school_date: str | None = None) -> dict:
    school_date = school_date or today_str()

    with get_db() as conn:
        stock = _ensure_stock(conn, school_date)

        rows = conn.execute(
            "SELECT roll, name, ts FROM ration_claims "
            "WHERE school_date = %s ORDER BY ts",
            (school_date,),
        ).fetchall()

    claims_by_roll = {r["roll"]: dict(r) for r in rows}

    students = [s for s in list_students() if s.get("role", "student") == "student"]

    claimed = len(claims_by_roll)

    grain_issued = round(sum(settings.grain_g_per_child / 1000 for _ in rows), 3)

    pulses_issued = round(sum(settings.pulses_g_per_child / 1000 for _ in rows), 3)

    remaining_grain = round(float(stock["initial_grain_kg"]) - grain_issued, 3)

    remaining_pulses = round(float(stock["initial_pulses_kg"]) - pulses_issued, 3)

    not_claimed = [
        {
            "roll": s["roll"],
            "name": s["name"],
            "class": s.get("class", ""),
        }
        for s in students
        if s["roll"] not in claims_by_roll
    ]

    return {
        "school_date": school_date,
        "initial_grain_kg": round(float(stock["initial_grain_kg"]), 3),
        "initial_pulses_kg": round(float(stock["initial_pulses_kg"]), 3),
        "grain_issued_kg": grain_issued,
        "pulses_issued_kg": pulses_issued,
        "remaining_grain_kg": max(0, remaining_grain),
        "remaining_pulses_kg": max(0, remaining_pulses),
        "student_count": len(students),
        "claimed_count": claimed,
        "not_claimed_count": len(not_claimed),
        "not_claimed": not_claimed,
        "per_student_grain_kg": settings.grain_g_per_child / 1000,
        "per_student_pulses_kg": settings.pulses_g_per_child / 1000,
    }


# Backward-compatible shape used by older dashboard code.
def compute_ration(school_date: str | None = None) -> dict:
    s = status(school_date)
    return {
        "school_date": s["school_date"],
        "headcount": s["claimed_count"],
        "roster_size": s["student_count"],
        "grain_kg": s["grain_issued_kg"],
        "pulses_kg": s["pulses_issued_kg"],
        "ghost_flags": 0,
    }
