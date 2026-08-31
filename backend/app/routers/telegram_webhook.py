"""
Telegram webhook for household self-registration.

Flow:
    1. Household opens the bot and taps Start.
    2. Bot asks them to share their phone number.
    3. Telegram sends the contact payload to this webhook.
    4. The phone number is normalized and stored with the Telegram chat_id.
    5. Later, services/sms_gateway.py can look up the chat_id and send
       Telegram notifications for that phone number.
"""

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.database import get_db

logger = logging.getLogger("vidyarthi.telegram")

router = APIRouter(prefix="/telegram", tags=["telegram"])

TELEGRAM_API_BASE = "https://api.telegram.org"

CONTACT_KEYBOARD = {
    "keyboard": [
        [
            {
                "text": "Share phone number",
                "request_contact": True,
            }
        ]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}


def _normalize_phone(raw: str) -> str:
    """
    Normalize phone numbers so they match the format used in the roster.

    Example:
        +91 8853391938 -> 8853391938

    Adjust this if your roster stores phone numbers differently.
    """
    digits = "".join(ch for ch in raw if ch.isdigit())

    # Remove leading Indian country code when the number is 12 digits.
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]

    return digits


async def _send(
    chat_id: int,
    text: str,
    keyboard: dict | None = None,
) -> None:
    """Send a Telegram message to a chat."""
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    if keyboard:
        payload["reply_markup"] = keyboard

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage",
            json=payload,
        )

    # Raise on HTTP errors such as 401/403/404.
    response.raise_for_status()

    data = response.json()

    # Telegram can return HTTP 200 with {"ok": false}, so check this too.
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram sendMessage failed"))

    logger.info(
        "Telegram message sent successfully: chat_id=%s",
        chat_id,
    )


def _upsert_chat_map(phone: str, chat_id: int) -> None:
    """
    Store or update the phone -> Telegram chat_id mapping
    in PostgreSQL.
    """
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO telegram_chat_map (phone, chat_id, ts)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (phone)
            DO UPDATE SET
                chat_id = EXCLUDED.chat_id,
                ts = EXCLUDED.ts
            """,
            (phone, chat_id),
        )


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Public Telegram webhook endpoint.

    Telegram authenticates the webhook using the secret_token configured
    in setWebhook. We verify that header here.
    """
    if settings.telegram_webhook_secret:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

        if header != settings.telegram_webhook_secret:
            logger.warning("Rejected Telegram webhook: invalid secret token")
            raise HTTPException(
                status_code=403,
                detail="Invalid Telegram webhook secret",
            )

    update = await request.json()

    logger.info(
        "Telegram update received: update_id=%s",
        update.get("update_id"),
    )

    message = update.get("message")
    if not message:
        logger.info("Telegram update contains no message")
        return {"ok": True}

    chat_id = message["chat"]["id"]

    logger.info(
        "Telegram message received: chat_id=%s text=%r",
        chat_id,
        message.get("text"),
    )

    contact = message.get("contact")

    if contact:
        phone = _normalize_phone(contact.get("phone_number", ""))

        if phone:
            _upsert_chat_map(phone, int(chat_id))

            logger.info(
                "Telegram registration successful: phone=%s chat_id=%s",
                phone,
                chat_id,
            )

            await _send(
                int(chat_id),
                "Thanks! You're registered to receive school updates.",
            )
        else:
            await _send(
                int(chat_id),
                "Sorry, couldn't read that phone number, please try again.",
            )

        return {"ok": True}

    text = (message.get("text") or "").strip().lower()

    if text in ("/start", "/register"):
        logger.info(
            "Handling Telegram registration request: chat_id=%s",
            chat_id,
        )

        await _send(
            int(chat_id),
            "Welcome! Please share your phone number so we can send you "
            "your child's attendance/ration updates.",
            keyboard=CONTACT_KEYBOARD,
        )
    else:
        await _send(
            int(chat_id),
            "Send /start to register for school updates.",
        )

    return {"ok": True}
