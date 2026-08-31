from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.security import require_admin
from app.services import poshan
from app.ws_manager import manager

router = APIRouter(prefix="/ration", tags=["ration"])


class StockIn(BaseModel):
    initial_grain_kg: float
    initial_pulses_kg: float
    school_date: str | None = None


@router.get("/today")
def get_ration_today():
    return poshan.status()


@router.post("/stock", dependencies=[Depends(require_admin)])
async def set_ration_stock(body: StockIn):
    try:
        result = poshan.set_stock(body.initial_grain_kg, body.initial_pulses_kg, body.school_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await manager.broadcast("ration_update", result)
    return result
