"""Teacher-session feedback service (1-4 rating)."""

from datetime import datetime
from app.database import get_db
from app.roster_store import get_by_uid, get_by_roll


class FeedbackError(Exception):
    pass


def start_session(teacher_roll: str, teacher_name: str, terminal_id: str) -> dict:
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE feedback_sessions SET active = 0 WHERE terminal_id = %s",
            (terminal_id,),
        )
        cur = conn.execute(
            """INSERT INTO feedback_sessions
               (teacher_roll, teacher_name, terminal_id, started_at, active)
               VALUES (%s,%s,%s,%s,1)
               RETURNING id""",
            (teacher_roll, teacher_name, terminal_id, now),
        )
        conn.commit()
        session_id = cur.fetchone()["id"]
    return {
        "session_id": session_id,
        "teacher_roll": teacher_roll,
        "teacher_name": teacher_name,
    }


def close_terminal_sessions(terminal_id: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE feedback_sessions SET active = 0 WHERE terminal_id = %s",
            (terminal_id,),
        )
        conn.commit()


def record_feedback(
    session_id: int, uid: str | None, roll: str | None, rating: int
) -> dict:
    if rating not in (1, 2, 3, 4):
        raise FeedbackError("rating must be between 1 and 4")
    student = get_by_uid(uid) if uid else (get_by_roll(roll) if roll else None)
    if not student:
        raise FeedbackError("student card not found")
    if student.get("role", "student") != "student":
        raise FeedbackError("teacher cards cannot submit student feedback")

    now = datetime.now().isoformat()
    with get_db() as conn:
        session = conn.execute(
            "SELECT * FROM feedback_sessions WHERE id = %s AND active = 1",
            (session_id,),
        ).fetchone()
        if not session:
            raise FeedbackError("feedback session is no longer active")
        try:
            conn.execute(
                """INSERT INTO feedback_responses
                   (session_id, roll, name, rating, ts)
                   VALUES (%s,%s,%s,%s,%s)""",
                (session_id, student["roll"], student["name"], rating, now),
            )
        except Exception as exc:
            # PostgreSQL UNIQUE violation.
            if getattr(exc, "sqlstate", None) == "23505":
                raise FeedbackError("student already submitted feedback") from exc
            raise
        conn.commit()

    return {
        "session_id": session_id,
        "roll": student["roll"],
        "name": student["name"],
        "rating": rating,
    }


def summary() -> dict:
    with get_db() as conn:
        row = conn.execute(
            """SELECT fs.id, fs.teacher_roll, fs.teacher_name, fs.started_at, fs.active,
                      COUNT(fr.id) AS total
               FROM feedback_sessions fs
               LEFT JOIN feedback_responses fr ON fr.session_id = fs.id
               GROUP BY fs.id
               ORDER BY fs.id DESC LIMIT 1"""
        ).fetchone()
        if not row:
            return {
                "active": False,
                "teacher_roll": None,
                "teacher_name": None,
                "session_id": None,
                "total": 0,
                "average": 0,
                "ratings": {"1": 0, "2": 0, "3": 0, "4": 0},
            }

        ratings = {"1": 0, "2": 0, "3": 0, "4": 0}
        responses = conn.execute(
            "SELECT rating FROM feedback_responses WHERE session_id = %s",
            (row["id"],),
        ).fetchall()
        for r in responses:
            ratings[str(r["rating"])] += 1

    total = sum(ratings.values())
    average = sum(int(k) * v for k, v in ratings.items()) / total if total else 0
    return {
        "active": bool(row["active"]),
        "teacher_roll": row["teacher_roll"],
        "teacher_name": row["teacher_name"],
        "session_id": row["id"],
        "started_at": row["started_at"],
        "total": total,
        "average": round(average, 2),
        "ratings": ratings,
    }
