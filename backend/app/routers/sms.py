from fastapi import APIRouter, Depends

from app.database import get_db
from app.security import require_admin
from app.services.daily_summary import households_pending_count
from app.services.scheduler import run_sms_batch_job

router = APIRouter(prefix="/sms", tags=["sms"])


@router.get("/status")
def sms_status():
    return {"households_pending": households_pending_count()}


@router.post("/trigger-batch", dependencies=[Depends(require_admin)])
async def trigger_batch():
    """Manually fire the evening consolidated batch, without waiting for the clock."""
    return await run_sms_batch_job()


@router.get("/log")
def sms_log(limit: int = 50):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT phone, message, status, ts FROM sms_log ORDER BY ts DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
