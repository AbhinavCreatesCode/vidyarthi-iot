from collections import deque
from datetime import date, datetime

from app.config import settings
from app.roster_store import get_by_roll, get_by_uid
from app.database import get_db


class UnknownCardError(Exception):
    pass


# Two different student IDs this close together are considered suspicious.
# Change this value to 2, 3, etc. to tune the suspicion window.
PROXY_WINDOW_SECONDS = 3

# Physical scan events are kept separately from attendance rows so duplicate
# scans can participate in proxy detection without creating duplicate
# attendance records. Only distinct student rolls count toward suspicion.
_recent_scans = deque()


def _session_for_time(ts: datetime) -> str:
    return "AM" if ts.hour < settings.am_pm_cutoff_hour else "PM"


def _parse_ts(value) -> datetime:
    """Convert a database timestamp string back into a datetime."""
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))

    # Keep comparisons safe if one timestamp happens to contain timezone info.
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)

    return parsed


def record_tap(
    uid: str | None = None,
    roll: str | None = None,
    session: str | None = None,
    ts: datetime | None = None,
    source: str = "terminal",
) -> dict:
    """
    Record one student's attendance.

    Rules:
      1. Only one attendance record per student/session/day.
      2. A student's repeat scan does not by itself trigger proxy suspicion.
      3. Two or more *different students* physically scanning within
         PROXY_WINDOW_SECONDS causes all students in that scan window to be
         marked as proxy-suspected.

    Physical scan events are tracked separately in memory so duplicate scans
    can be visible to the proxy detector without creating duplicate
    attendance rows.
    """

    student = get_by_uid(uid) if uid else (get_by_roll(roll) if roll else None)

    if not student or student.get("role", "student") != "student":
        raise UnknownCardError(uid or roll or "")

    ts = ts or datetime.now()

    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)

    session = session or _session_for_time(ts)
    school_date = ts.date().isoformat()

    # Track every physical scan, including duplicates. The proxy detector
    # counts distinct student rolls, so A+A does not flag anyone, while
    # A+B (or A+A+B) does.
    window_start = ts.timestamp() - PROXY_WINDOW_SECONDS
    _recent_scans.append((ts, student["roll"], student["name"], session, school_date))
    while _recent_scans and _recent_scans[0][0].timestamp() < window_start:
        _recent_scans.popleft()

    window_students = {}
    for scan_ts, scan_roll, scan_name, scan_session, scan_date in _recent_scans:
        if scan_session == session and scan_date == school_date:
            window_students[scan_roll] = {
                "roll": scan_roll,
                "name": scan_name,
                "ts": scan_ts,
            }

    proxy_suspected = len(window_students) >= 2
    proxy_students = list(window_students.values()) if proxy_suspected else []

    with get_db() as conn:
        existing = conn.execute(
            """
            SELECT verified, ts
            FROM taps
            WHERE roll = %s
              AND session = %s
              AND school_date = %s
            ORDER BY ts ASC
            LIMIT 1
            """,
            (student["roll"], session, school_date),
        ).fetchone()

        if existing:
            # A repeat scan by the same student alone is never a proxy event.
            # Preserve the prior behavior that a flagged student can clear
            # their timing-proxy flag by scanning their own card again, but
            # only when this scan is NOT part of a multi-student window.
            if int(existing["verified"]) == 0 and not proxy_suspected:
                conn.execute(
                    """
                    UPDATE taps
                    SET verified = 1
                    WHERE roll = %s
                      AND session = %s
                      AND school_date = %s
                    """,
                    (student["roll"], session, school_date),
                )
                conn.commit()

                return {
                    "name": student["name"],
                    "roll": student["roll"],
                    "session": session,
                    "verified": True,
                    "already_marked": True,
                    "proxy_cleared": True,
                    "proxy_suspected": False,
                    "ts": ts.isoformat(),
                    "attendance_ts": existing["ts"],
                }

            # If this duplicate scan participates in a multi-student window,
            # keep the student flagged instead of clearing the proxy state.
            if proxy_suspected:
                conn.execute(
                    """
                    UPDATE taps
                    SET verified = 0
                    WHERE roll = ANY(%s)
                      AND session = %s
                      AND school_date = %s
                    """,
                    (list(window_students.keys()), session, school_date),
                )
                conn.commit()

            return {
                "name": student["name"],
                "roll": student["roll"],
                "session": session,
                "verified": not proxy_suspected,
                "already_marked": True,
                "proxy_cleared": False,
                "proxy_suspected": proxy_suspected,
                "ts": ts.isoformat(),
                "attendance_ts": existing["ts"],
                "proxy_partners": [
                    {"roll": x["roll"], "name": x["name"]}
                    for x in proxy_students
                    if x["roll"] != student["roll"]
                ],
            }

        # New attendance record.
        conn.execute(
            """
            INSERT INTO taps
            (roll, name, session, ts, school_date, verified, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                student["roll"],
                student["name"],
                session,
                ts.isoformat(),
                school_date,
                0 if proxy_suspected else 1,
                source,
            ),
        )

        # If this scan completes a multi-student proxy window, mark ALL
        # students in that window, not just the immediately previous one.
        if proxy_suspected:
            conn.execute(
                """
                UPDATE taps
                SET verified = 0
                WHERE roll = ANY(%s)
                  AND session = %s
                  AND school_date = %s
                """,
                (list(window_students.keys()), session, school_date),
            )

        conn.commit()

    result = {
        "name": student["name"],
        "roll": student["roll"],
        "session": session,
        "verified": not proxy_suspected,
        "already_marked": False,
        "proxy_suspected": proxy_suspected,
        "ts": ts.isoformat(),
    }

    if proxy_suspected:
        result["proxy_partners"] = [
            {"roll": x["roll"], "name": x["name"]}
            for x in proxy_students
            if x["roll"] != student["roll"]
        ]

    return result


def recent_taps(limit: int = 40, school_date: str | None = None) -> list[dict]:
    """Most recent taps for the dashboard live feed."""

    school_date = school_date or date.today().isoformat()

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT roll, name, session, ts, verified
            FROM taps
            WHERE school_date = %s
            ORDER BY ts DESC
            LIMIT %s
            """,
            (school_date, limit),
        ).fetchall()

    return [
        {
            "name": r["name"],
            "roll": r["roll"],
            "session": r["session"],
            "verified": bool(r["verified"]),
            "ts": r["ts"],
        }
        for r in rows
    ]


def verification_matrix(
    school_date: str | None = None,
) -> list[dict]:
    """
    AM vs PM tap status per student.

    `proxy` is true when a stored attendance record was explicitly
    timing-proxy-flagged, or when the historical AM/PM rule identifies
    a PM-only student as suspicious.
    """

    from app.roster_store import list_students

    school_date = school_date or date.today().isoformat()

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                roll,
                session,
                MIN(ts) AS first_ts,
                MIN(verified) AS verified_state
            FROM taps
            WHERE school_date = %s
            GROUP BY roll, session
            """,
            (school_date,),
        ).fetchall()

    taps_by_roll: dict[str, dict] = {}

    for r in rows:
        taps_by_roll.setdefault(r["roll"], {})[r["session"]] = {
            "ts": r["first_ts"],
            "verified": bool(r["verified_state"]),
        }

    out = []

    for s in list_students():
        if s.get("role", "student") != "student":
            continue

        student_taps = taps_by_roll.get(s["roll"], {})
        am_data = student_taps.get("AM")
        pm_data = student_taps.get("PM")

        am = am_data["ts"] if am_data else None
        pm = pm_data["ts"] if pm_data else None

        timing_proxy = (am_data is not None and not am_data["verified"]) or (
            pm_data is not None and not pm_data["verified"]
        )

        if timing_proxy:
            status = "proxy_suspected"
        elif am and pm:
            status = "matched"
        elif am and not pm:
            status = "pending_pm"
        elif pm and not am:
            status = "proxy_suspected"
        else:
            status = "no_taps"

        out.append(
            {
                "roll": s["roll"],
                "name": s["name"],
                "am": am,
                "pm": pm,
                "status": status,
                "proxy": timing_proxy or (pm is not None and am is None),
            }
        )

    return out
