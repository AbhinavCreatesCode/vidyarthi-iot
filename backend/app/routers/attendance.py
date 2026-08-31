from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services import poshan
from app.security import require_admin
from app.services.attendance import UnknownCardError, record_tap, recent_taps, verification_matrix
from app.ws_manager import manager

router = APIRouter(tags=["attendance"])


class TapIn(BaseModel):
    uid: str | None = None
    roll: str | None = None
    session: str | None = None  # "AM" | "PM", auto-detected from time if omitted


@router.post("/attendance/tap", dependencies=[Depends(require_admin)])
async def http_tap(tap: TapIn):
    """
    HTTP fallback for ingesting a tap -- useful for testing without an ESP32
    on hand (curl/Postman), or for a second entry channel. The primary path
    for the real terminal is the WebSocket at /ws/terminal/{device_id}.
    """
    try:
        event = record_tap(uid=tap.uid, roll=tap.roll, session=tap.session, source="manual")
    except UnknownCardError:
        raise HTTPException(status_code=404, detail="Card UID / roll not found in roster")
    await manager.broadcast("tap_event", event)
    return event


@router.get("/attendance/verification")
def get_verification_matrix(school_date: str | None = None):
    return verification_matrix(school_date)


@router.get("/attendance/recent")
def get_recent_taps(limit: int = 40, school_date: str | None = None):
    """Powers the dashboard's live tap feed on first load / reload, before
    any new WebSocket tap_event has arrived."""
    return recent_taps(limit=limit, school_date=school_date)


@router.get("/poshan/today")
def get_poshan_today():
    return poshan.compute_ration()
