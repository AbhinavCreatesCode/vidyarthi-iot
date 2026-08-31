"""Raw WebSocket endpoints for dashboard and ESP32 terminal."""

import traceback
import json
import logging
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.roster_store import get_by_uid, get_by_roll
from app.services import feedback as feedback_service
from app.services import hardware
from app.services import poshan
from app.services.attendance import UnknownCardError, record_tap
from app.ws_manager import manager

logger = logging.getLogger("vidyarthi.ws.router")
router = APIRouter(tags=["websocket"])
terminal_modes: Dict[str, dict] = {}


async def _terminal_reply(device_id: str, message_type: str, data: dict) -> None:
    await manager.send_to_terminal(device_id, {"type": message_type, "data": data})


@router.websocket("/ws/dashboard")
async def dashboard_socket(ws: WebSocket):
    # Reuse the admin key as the dashboard WebSocket token. The dashboard
    # already stores this key for authenticated REST requests.
    token = ws.query_params.get("token")
    if settings.admin_api_key and token != settings.admin_api_key:
        await ws.close(code=1008, reason="Invalid or missing dashboard token")
        return
    await manager.connect_dashboard(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_dashboard(ws)


async def _handle_tap(
    device_id: str,
    data: dict,
    source: str = "terminal",
) -> None:

    # ------------------------------------------------------------
    # Make sure Attendance mode is actually active
    # ------------------------------------------------------------
    active = terminal_modes.get(device_id)

    if not active or active.get("mode") != "attendance":

        logger.warning(
            "Blocked attendance tap: device=%s mode=%s source=%s",
            device_id,
            active.get("mode") if active else None,
            source,
        )

        await _terminal_reply(
            device_id,
            "attendance_result",
            {
                "ok": False,
                "message": (
                    "Attendance requires a teacher to start " "Attendance mode first"
                ),
            },
        )

        return

    # ------------------------------------------------------------
    # Read tap data
    # ------------------------------------------------------------
    uid = data.get("uid")
    roll = data.get("roll")
    session = data.get("session")

    ts = None

    if data.get("ts"):
        try:
            ts = datetime.fromisoformat(data["ts"])
        except (ValueError, TypeError):
            ts = None

    # ------------------------------------------------------------
    # Record attendance
    # ------------------------------------------------------------
    try:

        event = record_tap(
            uid=uid,
            roll=roll,
            session=session,
            ts=ts,
            source=source,
        )

    # ------------------------------------------------------------
    # Unknown RFID
    # ------------------------------------------------------------
    except UnknownCardError:

        logger.warning(
            "Unrecognised card: uid=%s roll=%s",
            uid,
            roll,
        )

        await _terminal_reply(
            device_id,
            "attendance_result",
            {
                "ok": False,
                "uid": uid,
                "message": "Student card not recognised",
            },
        )

        # Keep unknown-card visibility in the dashboard.
        await manager.broadcast(
            "tap_event",
            {
                "name": "Unrecognised card",
                "roll": roll or "?",
                "uid": uid or "",
                "session": "SCAN",
                "verified": False,
            },
        )

        return

    # ------------------------------------------------------------
    # Any unexpected attendance/database error
    # ------------------------------------------------------------
    except Exception as exc:

        logger.exception(
            "Attendance error: device=%s uid=%s roll=%s",
            device_id,
            uid,
            roll,
        )

        await _terminal_reply(
            device_id,
            "attendance_result",
            {
                "ok": False,
                "message": f"Attendance save failed: {str(exc)}",
            },
        )

        return

    # ============================================================
    # SUCCESSFUL record_tap()
    # ============================================================

    # ------------------------------------------------------------
    # Duplicate tap
    #
    # If the student was already marked normally, don't create
    # another dashboard tap event.
    #
    # If the student was previously proxy-flagged and their own
    # card was scanned, record_tap() returns proxy_cleared=True.
    # ------------------------------------------------------------
    if event.get("already_marked"):

        await _terminal_reply(
            device_id,
            "attendance_result",
            {
                "ok": True,
                **event,
                "message": (
                    "Proxy cleared"
                    if event.get("proxy_cleared")
                    else (
                        "Proxy suspected"
                        if event.get("proxy_suspected")
                        else "Already marked for this session"
                    )
                ),
            },
        )

        # Every physical scan should reach the live feed, even when it did
        # not create a new attendance row. The event keeps `already_marked`
        # true so the dashboard can label it accordingly.
        await manager.broadcast(
            "tap_event",
            {
                **event,
                "already_marked": True,
            },
        )

        # A duplicate scan can itself complete a multi-student proxy window.
        # Do not return before notifying the dashboard about every partner.
        if event.get("proxy_suspected"):
            partners = event.get("proxy_partners") or []
            for partner in partners:
                await manager.broadcast(
                    "proxy_event",
                    {
                        "action": "flag",
                        "roll": partner["roll"],
                        "partner_roll": event["roll"],
                        "partner_name": event.get("name"),
                        "session": event.get("session"),
                    },
                )

            logger.warning(
                "Possible proxy group detected on duplicate scan: current=%s (%s), partners=%s, session=%s",
                event.get("roll"),
                event.get("name"),
                [p.get("roll") for p in partners],
                event.get("session"),
            )

        return

    # ------------------------------------------------------------
    # Send successful attendance result to ESP
    # ------------------------------------------------------------
    await _terminal_reply(
        device_id,
        "attendance_result",
        {
            "ok": True,
            **event,
        },
    )

    # ------------------------------------------------------------
    # Broadcast the current student's tap
    #
    # This works for:
    #   - normal attendance
    #   - newly detected proxy
    # ------------------------------------------------------------
    await manager.broadcast(
        "tap_event",
        event,
    )

    # ------------------------------------------------------------
    # Proxy detected
    #
    # record_tap() has already:
    #   1. marked the current student verified=0
    #   2. marked the previous student's record verified=0
    #
    # We now notify the dashboard that the PREVIOUS student's
    # existing feed entry must also become "UNKNOWN/Proxy".
    # ------------------------------------------------------------
    if event.get("proxy_suspected"):
        partners = event.get("proxy_partners") or []

        # Tell the dashboard about every other student in the 3-second
        # multi-student scan window, not only the immediately previous scan.
        for partner in partners:
            await manager.broadcast(
                "proxy_event",
                {
                    "action": "flag",
                    "roll": partner["roll"],
                    "partner_roll": event["roll"],
                    "partner_name": event.get("name"),
                    "session": event.get("session"),
                },
            )

        logger.warning(
            "Possible proxy group detected: current=%s (%s), partners=%s, session=%s",
            event.get("roll"),
            event.get("name"),
            [p.get("roll") for p in partners],
            event.get("session"),
        )


async def _handle_card_scan(device_id: str, data: dict) -> None:
    uid = str(data.get("uid") or "").upper()
    if not uid:
        await _terminal_reply(
            device_id, "card_result", {"ok": False, "message": "No card UID received"}
        )
        return

    person = get_by_uid(uid)
    if not person:
        await _terminal_reply(
            device_id,
            "card_result",
            {
                "ok": False,
                "uid": uid,
                "role": "unknown",
                "message": "Card not in roster",
            },
        )
        # Unknown scans are useful telemetry. Do not record them as attendance,
        # but show the raw UID in the dashboard live feed.
        await manager.broadcast(
            "tap_event",
            {
                "name": "Unrecognised card",
                "roll": "Unknown",
                "uid": uid,
                "session": "SCAN",
                "verified": False,
                "device_id": device_id,
            },
        )
        await manager.broadcast(
            "terminal_event",
            {"device_id": device_id, "event": "unknown_card", "uid": uid},
        )
        return

    role = person.get("role", "student")
    payload = {
        "ok": True,
        "uid": uid,
        "roll": person["roll"],
        "name": person["name"],
        "role": role,
    }

    if role == "teacher":
        terminal_modes.pop(device_id, None)
        await _terminal_reply(device_id, "card_result", payload)
        await manager.broadcast(
            "mode_event",
            {
                "device_id": device_id,
                "mode": "select",
                "teacher_roll": person["roll"],
                "teacher_name": person["name"],
            },
        )
        return
    active = terminal_modes.get(device_id)

    # Card classification is complete. The ESP is responsible for the
    # next mode-specific action. In Attendance mode the ESP will receive
    # card_result and then send a separate "tap" message.
    await _terminal_reply(device_id, "card_result", payload)

    if not active:
        return

    # Feedback/Ration need the dashboard event as before. Attendance must
    # NOT call _handle_tap() here, otherwise one physical scan would be
    # processed twice (card_scan + the ESP's subsequent tap message).
    if active.get("mode") != "attendance":
        await manager.broadcast(
            "terminal_event",
            {
                "device_id": device_id,
                "event": "student_card_ready",
                "mode": active["mode"],
                "roll": person["roll"],
                "name": person["name"],
            },
        )


async def _handle_start_mode(device_id: str, data: dict) -> None:
    mode = str(data.get("mode") or "").lower()
    teacher_roll = data.get("teacher_roll")
    teacher = get_by_roll(teacher_roll) if teacher_roll else None
    if not teacher or teacher.get("role") != "teacher":
        await _terminal_reply(
            device_id,
            "mode_started",
            {"ok": False, "message": "Teacher authentication required"},
        )
        return
    if mode not in ("attendance", "feedback", "ration"):
        await _terminal_reply(
            device_id,
            "mode_started",
            {"ok": False, "message": "Invalid mode"},
        )
        return

    terminal_modes[device_id] = {
        "mode": mode,
        "teacher_roll": teacher["roll"],
        "teacher_name": teacher["name"],
    }
    session_id = None
    if mode == "feedback":
        session = feedback_service.start_session(
            teacher["roll"], teacher["name"], device_id
        )
        session_id = session["session_id"]
        terminal_modes[device_id]["session_id"] = session_id

    await _terminal_reply(
        device_id,
        "mode_started",
        {
            "ok": True,
            "mode": mode,
            "teacher_roll": teacher["roll"],
            "teacher_name": teacher["name"],
            "session_id": session_id,
        },
    )
    await manager.broadcast(
        "mode_event",
        {
            "device_id": device_id,
            "mode": mode,
            "teacher_roll": teacher["roll"],
            "teacher_name": teacher["name"],
            "session_id": session_id,
        },
    )


async def _handle_stop_mode(device_id: str, data: dict) -> None:
    active = terminal_modes.pop(device_id, None)

    # Close any feedback session associated with this terminal.
    if active and active.get("mode") == "feedback":
        feedback_service.close_terminal_sessions(device_id)

    previous_mode = active.get("mode") if active else None

    await _terminal_reply(
        device_id,
        "mode_stopped",
        {
            "ok": True,
            "previous_mode": previous_mode,
        },
    )

    await manager.broadcast(
        "mode_event",
        {
            "device_id": device_id,
            "mode": "idle",
            "previous_mode": previous_mode,
        },
    )


async def _handle_feedback(device_id: str, data: dict) -> None:
    active = terminal_modes.get(device_id)
    if not active or active.get("mode") != "feedback":
        await _terminal_reply(
            device_id,
            "feedback_result",
            {"ok": False, "message": "Feedback mode is not active"},
        )
        return
    try:
        event = feedback_service.record_feedback(
            session_id=int(active["session_id"]),
            uid=data.get("uid"),
            roll=data.get("roll"),
            rating=int(data.get("rating")),
        )
    except (ValueError, TypeError, feedback_service.FeedbackError) as exc:
        await _terminal_reply(
            device_id, "feedback_result", {"ok": False, "message": str(exc)}
        )
        return
    await _terminal_reply(device_id, "feedback_result", {"ok": True, **event})
    await manager.broadcast("feedback_update", feedback_service.summary())


async def _handle_ration_claim(device_id: str, data: dict) -> None:
    active = terminal_modes.get(device_id)
    if not active or active.get("mode") != "ration":
        await _terminal_reply(
            device_id,
            "ration_result",
            {"ok": False, "message": "Ration mode is not active"},
        )
        return
    try:
        event = poshan.claim_ration(
            uid=data.get("uid"),
            roll=data.get("roll"),
            teacher_roll=active["teacher_roll"],
        )
    except (ValueError, TypeError) as exc:
        await _terminal_reply(
            device_id, "ration_result", {"ok": False, "message": str(exc)}
        )
        return
    await _terminal_reply(device_id, "ration_result", {"ok": True, **event})
    await manager.broadcast("ration_update", poshan.status())


async def _handle_heartbeat(device_id: str, data: dict) -> None:
    status = hardware.update_status(
        device_id=device_id,
        rssi=int(data.get("rssi", -100)),
        queue=int(data.get("queue", 0)),
        online=True,
    )
    await manager.broadcast(
        "hardware_status",
        {"rssi": status["rssi"], "online": status["online"], "queue": status["queue"]},
    )


async def _handle_offline_sync(device_id: str, data: dict) -> None:
    """
    Offline attendance sync is intentionally disabled.

    Attendance now requires an active teacher-started Attendance mode, so
    previously buffered taps must never be replayed automatically.
    """
    events = data.get("events", [])
    tap_count = sum(1 for ev in events if ev.get("type") == "tap")

    if tap_count:
        logger.warning(
            "Rejected %d offline attendance tap(s): teacher authorization required",
            tap_count,
        )
        await _terminal_reply(
            device_id,
            "attendance_result",
            {
                "ok": False,
                "message": "Offline attendance sync is disabled; scan teacher and use Attendance mode",
            },
        )

    await manager.broadcast(
        "hardware_status", {"rssi": None, "online": True, "queue": 0}
    )


@router.websocket("/ws/terminal/{device_id}")
async def terminal_socket(ws: WebSocket, device_id: str):
    # Terminal auth is separate from admin auth so the ESP32 does not need
    # dashboard permissions. Leave TERMINAL_API_KEY blank only for local LAN development.
    token = ws.query_params.get("token")
    if settings.terminal_api_key and token != settings.terminal_api_key:
        await ws.close(code=1008, reason="Invalid or missing terminal token")
        return

    await manager.connect_terminal(device_id, ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            msg_type = msg.get("type")
            data = msg.get("data", {})
            if msg_type == "card_scan":
                await _handle_card_scan(device_id, data)

            elif msg_type == "tap":
                await _handle_tap(device_id, data)

            elif msg_type == "start_mode":
                await _handle_start_mode(device_id, data)

            elif msg_type == "stop_mode":
                await _handle_stop_mode(device_id, data)

            elif msg_type == "feedback":
                await _handle_feedback(device_id, data)

            elif msg_type == "ration_claim":
                await _handle_ration_claim(device_id, data)

            elif msg_type == "heartbeat":
                await _handle_heartbeat(device_id, data)

            elif msg_type == "offline_sync":
                await _handle_offline_sync(device_id, data)

            else:
                logger.debug("unknown terminal message type: %s", msg_type)
    except WebSocketDisconnect:
        pass
    finally:
        terminal_modes.pop(device_id, None)
        feedback_service.close_terminal_sessions(device_id)
        await manager.disconnect_terminal(device_id)
        hardware.mark_offline(device_id)
        await manager.broadcast(
            "hardware_status", {"rssi": None, "online": False, "queue": 0}
        )
