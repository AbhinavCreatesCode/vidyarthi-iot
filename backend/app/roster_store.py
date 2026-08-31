"""
PostgreSQL-backed student roster.

The roster is stored in the same PostgreSQL database as attendance and the
other application data. No CSV file is used at runtime.
"""
from typing import List, Optional

from app.database import get_db


def list_students() -> List[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT roll,
                   name,
                   class_name AS class,
                   rfid_uid,
                   guardian_phone,
                   role
            FROM students
            ORDER BY roll
            """
        ).fetchall()
    return list(rows)


def search_students(query: str, limit: int = 50) -> List[dict]:
    """Search the PostgreSQL roster by roll, name, class, or RFID UID."""
    query = (query or "").strip()
    limit = max(1, min(int(limit), 100))

    with get_db() as conn:
        if not query:
            rows = conn.execute(
                """
                SELECT roll,
                       name,
                       class_name AS class,
                       rfid_uid,
                       guardian_phone,
                       role
                FROM students
                ORDER BY roll
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        else:
            pattern = f"%{query}%"
            rows = conn.execute(
                """
                SELECT roll,
                       name,
                       class_name AS class,
                       rfid_uid,
                       guardian_phone,
                       role
                FROM students
                WHERE roll ILIKE %s
                   OR name ILIKE %s
                   OR class_name ILIKE %s
                   OR rfid_uid ILIKE %s
                ORDER BY
                    CASE WHEN roll ILIKE %s THEN 0 ELSE 1 END,
                    name,
                    roll
                LIMIT %s
                """,
                (pattern, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
    return list(rows)



def get_by_roll(roll: str) -> Optional[dict]:
    with get_db() as conn:
        return conn.execute(
            """
            SELECT roll,
                   name,
                   class_name AS class,
                   rfid_uid,
                   guardian_phone,
                   role
            FROM students
            WHERE roll = %s
            """,
            (roll,),
        ).fetchone()


def get_by_uid(uid: str) -> Optional[dict]:
    with get_db() as conn:
        return conn.execute(
            """
            SELECT roll,
                   name,
                   class_name AS class,
                   rfid_uid,
                   guardian_phone,
                   role
            FROM students
            WHERE UPPER(rfid_uid) = UPPER(%s)
            """,
            (uid,),
        ).fetchone()


def upsert_student(
    roll: str,
    name: str,
    cls: str,
    rfid_uid: str,
    guardian_phone: str = "",
    role: str = "student",
) -> dict:
    role = role.lower().strip()
    if role not in ("student", "teacher"):
        raise ValueError("role must be student or teacher")

    row = {
        "roll": roll.strip(),
        "name": name.strip(),
        "class": cls.strip(),
        "rfid_uid": rfid_uid.strip().upper(),
        "guardian_phone": guardian_phone.strip(),
        "role": role,
    }

    if not row["roll"] or not row["name"] or not row["class"] or not row["rfid_uid"]:
        raise ValueError("roll, name, class and RFID UID are required")

    with get_db() as conn:
        try:
            result = conn.execute(
                """
                INSERT INTO students
                    (roll, name, class_name, rfid_uid, guardian_phone, role)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (roll) DO UPDATE SET
                    name = EXCLUDED.name,
                    class_name = EXCLUDED.class_name,
                    rfid_uid = EXCLUDED.rfid_uid,
                    guardian_phone = EXCLUDED.guardian_phone,
                    role = EXCLUDED.role
                RETURNING roll,
                          name,
                          class_name AS class,
                          rfid_uid,
                          guardian_phone,
                          role
                """,
                (
                    row["roll"],
                    row["name"],
                    row["class"],
                    row["rfid_uid"],
                    row["guardian_phone"],
                    row["role"],
                ),
            ).fetchone()
        except Exception as exc:
            # Keep the dashboard's existing validation error UX for a UID
            # already assigned to another student.
            if "students_rfid_uid_key" in str(exc) or "duplicate key" in str(exc):
                raise ValueError("RFID UID is already assigned to another student") from exc
            raise

    return dict(result)


def remove_student(roll: str) -> bool:
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM students WHERE roll = %s",
            (roll,),
        )
        return result.rowcount > 0
