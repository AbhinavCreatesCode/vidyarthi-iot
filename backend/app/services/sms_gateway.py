"""
Telegram gateway (drop-in replacement for the old generic SMS REST gateway).

Telegram has no concept of "send to a phone number" -- a household must
first start a chat with your bot and share their phone number once, which
we store in the `telegram_chat_map` table (phone -> chat_id). After that,
send_sms(phone, message) looks up the chat_id and calls Telegram's
sendMessage API.

TELEGRAM_DRY_RUN=true (the default) logs the message and records it in
sms_log with status 'dry_run' instead of calling the real Telegram API, so
the 7:30 PM batch job is safe to test before a bot token is configured.

Setup: see SETUP_TELEGRAM.md at the repo root.
"""

import logging
from datetime import datetime

import httpx

from app.config import settings
from app.database import get_db

logger = logging.getLogger("vidyarthi.sms")

TELEGRAM_API_BASE = "https://api.telegram.org"


def _log(phone: str, message: str, status: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sms_log (phone, message, status, ts) VALUES (%s,%s,%s,%s)",
            (phone, message, status, datetime.now().isoformat()),
        )
        conn.commit()


def _lookup_chat_id(phone: str) -> int | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT chat_id FROM telegram_chat_map WHERE phone = %s", (phone,)
        ).fetchone()
    return row["chat_id"] if row else None


async def send_sms(phone: str, message: str) -> str:
    """Returns the final status string: 'sent' | 'failed' | 'dry_run' | 'unregistered'.

    Kept the name send_sms (and same (phone, message) -> str signature) so
    routers/sms.py, services/scheduler.py, and services/daily_summary.py
    don't need to change at all.
    """
    if not phone:
        return "failed"

    if settings.telegram_dry_run or not settings.telegram_bot_token:
        logger.info("[DRY RUN] Telegram message to %s: %s", phone, message)
        _log(phone, message, "dry_run")
        return "dry_run"

    chat_id = _lookup_chat_id(phone)
    if chat_id is None:
        logger.warning(
            "No Telegram chat_id registered for %s (household hasn't messaged "
            "the bot / shared contact yet)",
            phone,
        )
        _log(phone, message, "unregistered")
        return "unregistered"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("description", "unknown Telegram error"))
        _log(phone, message, "sent")
        return "sent"
    except Exception as exc:
        logger.warning("Telegram message to %s failed: %s", phone, exc)
        _log(phone, message, "failed")
        return "failed"
