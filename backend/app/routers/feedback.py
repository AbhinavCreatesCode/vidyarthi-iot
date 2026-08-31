from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import feedback
from app.ws_manager import manager

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackSessionStart(BaseModel):
    teacher_roll: str
    terminal_id: str = "dashboard"


@router.get("/summary")
def get_feedback_summary():
    return feedback.summary()
