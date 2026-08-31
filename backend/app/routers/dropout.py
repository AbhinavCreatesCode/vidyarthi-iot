from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.database import get_db
from app.security import require_admin
from app.services import dropout_risk
from app.services.scheduler import run_dropout_scan_job

router = APIRouter(prefix="/dropout", tags=["dropout"])


class InterventionIn(BaseModel):
    roll: str | None = None
    student: str
    note: str


@router.get("/flags")
def get_flags(limit: int = 20):
    return dropout_risk.list_recent_flags(limit)


@router.post("/scan", dependencies=[Depends(require_admin)])
async def trigger_scan():
    """On-demand trigger, in addition to the nightly scheduled scan."""
    new_flags = await run_dropout_scan_job()
    return {"new_flags": new_flags}


@router.post("/interventions", dependencies=[Depends(require_admin)])
def log_intervention(body: InterventionIn):
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO interventions (roll, student, note, ts) VALUES (%s,%s,%s,%s)",
            (body.roll, body.student, body.note, now),
        )
        conn.commit()
    return {"student": body.student, "note": body.note, "ts": now}


@router.get("/interventions")
def list_interventions(limit: int = 50):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT roll, student, note, ts FROM interventions ORDER BY ts DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
