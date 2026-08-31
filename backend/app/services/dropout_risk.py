"""Heuristic (not ML) dropout early-warning scan. Two pattern families:

  1. Weekday pattern   -- a student who is consistently absent on the same
     weekday (e.g. every Monday) often has a recurring household reason
     (market day, sibling care, a long commute after a weekend visit home).

  2. Seasonal pattern  -- absences that cluster inside the configured Rabi /
     Kharif harvest months suggest the family has pulled the child in for
     farm labour.

Anything at/above the missed-day threshold that doesn't fit either pattern
still gets flagged as a generic recurring-absence risk, so nothing silently
falls through.

This runs on a schedule (see services/scheduler.py) and is also exposed as
an on-demand REST trigger. Each new flag is stored and broadcast once;
re-running the scan on the same day does not duplicate a flag already
raised today for that student.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from app.config import settings
from app.roster_store import list_students
from app.database import get_db

WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
WINDOW_DAYS = 30


def _school_days(end: date, days: int) -> list[date]:
    """Weekdays (Mon-Fri) in the trailing `days` calendar days, ending `end`."""
    out = []
    for i in range(days):
        d = end - timedelta(days=i)
        if d.weekday() < 5:  # 0=Mon .. 4=Fri
            out.append(d)
    return out


def _present_dates(roll: str, since: date) -> set[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT school_date FROM taps WHERE roll = %s AND session = 'AM' AND school_date >= %s",
            (roll, since.isoformat()),
        ).fetchall()
    return {r["school_date"] for r in rows}


def _already_flagged_today(roll: str) -> bool:
    today = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM risk_flags WHERE roll = %s AND created_at::date = %s LIMIT 1",
            (roll, today),
        ).fetchone()
    return row is not None


def _store_flag(roll: str, name: str, pattern: str, missed: int, risk: str) -> dict:
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO risk_flags (roll, name, pattern, missed, risk, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
            (roll, name, pattern, missed, risk, now),
        )
        conn.commit()
    return {
        "roll": roll,
        "name": name,
        "pattern": pattern,
        "missed": missed,
        "risk": risk,
    }


def analyze_student(roll: str, name: str, today: date) -> dict | None:
    since = today - timedelta(days=WINDOW_DAYS)
    school_days = _school_days(today, WINDOW_DAYS)
    present = _present_dates(roll, since)
    missed_dates = [d for d in school_days if d.isoformat() not in present]
    missed = len(missed_dates)

    if missed < settings.dropout_missed_threshold:
        return None

    # -- weekday pattern --
    weekday_counts = Counter(d.weekday() for d in missed_dates)
    weekday_occurrences = Counter(d.weekday() for d in school_days)
    pattern = None
    for wd, count in weekday_counts.most_common(1):
        occurrences = weekday_occurrences[wd] or 1
        if count >= 3 and (count / occurrences) >= 0.5:
            pattern = f"Missing every {WEEKDAY_NAMES[wd]} — {count} of the last {occurrences} occurrences"
            break

    # -- seasonal pattern --
    if pattern is None:
        season_months = set(settings.rabi_months_list) | set(
            settings.kharif_months_list
        )
        in_season = [d for d in missed_dates if d.month in season_months]
        if season_months and missed and len(in_season) / missed >= 0.6:
            season_name = (
                "Rabi" if today.month in settings.rabi_months_list else "Kharif"
            )
            pattern = f"Absent during the {season_name} harvest window — {len(in_season)} of {missed} missed days"

    if pattern is None:
        pattern = f"Recurring absences — {missed} missed in the last {WINDOW_DAYS} days"

    risk = "high" if missed >= settings.dropout_missed_threshold * 1.5 else "med"
    return {
        "roll": roll,
        "name": name,
        "pattern": pattern,
        "missed": missed,
        "risk": risk,
    }


def run_scan() -> list[dict]:
    """Scan every enrolled student, store + return newly raised flags."""
    today = date.today()
    new_flags = []
    for student in list_students():
        if student.get("role", "student") != "student":
            continue
        roll, name = student["roll"], student["name"]
        if _already_flagged_today(roll):
            continue
        result = analyze_student(roll, name, today)
        if result:
            new_flags.append(_store_flag(**result))
    return new_flags


def list_recent_flags(limit: int = 20) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT roll, name, pattern, missed, risk, created_at FROM risk_flags "
            "ORDER BY created_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
