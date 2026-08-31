from datetime import datetime

from app.database import get_db

# A terminal that hasn't sent a heartbeat within this many seconds is
# considered offline even if its WebSocket hasn't formally closed yet.
STALE_AFTER_SECONDS = 90


def update_status(device_id: str, rssi: int, queue: int, online: bool = True) -> dict:
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO hardware_status (device_id, rssi, online, queue, updated_at) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT(device_id) DO UPDATE SET rssi=excluded.rssi, online=excluded.online, "
            "queue=excluded.queue, updated_at=excluded.updated_at",
            (device_id, rssi, 1 if online else 0, queue, now),
        )
        conn.commit()
    return {"device_id": device_id, "rssi": rssi, "online": online, "queue": queue}


def mark_offline(device_id: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE hardware_status SET online = 0, updated_at = %s WHERE device_id = %s",
            (datetime.now().isoformat(), device_id),
        )
        conn.commit()


def latest_status() -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM hardware_status ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None
