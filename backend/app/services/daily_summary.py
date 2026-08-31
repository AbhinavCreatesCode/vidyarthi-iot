from collections import defaultdict
from datetime import date

from app.roster_store import list_students
from app.database import get_db


def _today_attendance() -> dict:
    """roll -> {'am': bool, 'pm': bool}"""
    today = date.today().isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT roll, session FROM taps WHERE school_date = %s AND verified = 1",
            (today,),
        ).fetchall()
    out: dict[str, dict] = defaultdict(lambda: {"am": False, "pm": False})
    for r in rows:
        out[r["roll"]][r["session"].lower()] = True
    return out


def _today_meal_claims() -> set[str]:
    today = date.today().isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT roll FROM ration_claims WHERE school_date = %s",
            (today,),
        ).fetchall()
    return {r["roll"] for r in rows}


def _today_risk_flags() -> set[str]:
    today = date.today().isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT roll FROM risk_flags WHERE created_at::date = %s", (today,)
        ).fetchall()
    return {r["roll"] for r in rows}


def build_household_messages() -> dict[str, str]:
    """Returns {phone: message_text} for every household with a phone on file."""
    attendance = _today_attendance()
    meal_claims = _today_meal_claims()
    flagged = _today_risk_flags()
    today_label = date.today().strftime("%d %b")

    by_phone: dict[str, list[dict]] = defaultdict(list)
    for s in list_students():
        if s.get("role", "student") != "student":
            continue
        phone = (s.get("guardian_phone") or "").strip()
        if not phone:
            continue
        by_phone[phone].append(s)

    messages: dict[str, str] = {}
    for phone, students in by_phone.items():
        lines = [f"School update {today_label}:"]
        for s in students:
            att = attendance.get(s["roll"], {"am": False, "pm": False})
            if att["am"] and att["pm"]:
                status = "present, full day"
            elif att["am"]:
                status = (
                    "present morning, meal served"
                    if s["roll"] in meal_claims
                    else "present morning, meal not served"
                )
            else:
                status = "ABSENT today"
            line = f"{s['name']} (Roll {s['roll']}): {status}."
            if s["roll"] in flagged:
                line += " Teacher would like to speak with you about attendance."
            lines.append(line)
        messages[phone] = " ".join(lines)
    return messages


def households_pending_count() -> int:
    return len(build_household_messages())
