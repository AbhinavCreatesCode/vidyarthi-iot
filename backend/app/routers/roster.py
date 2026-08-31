from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import roster_store
from app.security import require_admin

router = APIRouter(prefix="/roster", tags=["roster"])


class StudentIn(BaseModel):
    roll: str
    name: str
    cls: str
    rfid_uid: str
    guardian_phone: str = ""
    role: str = "student"


@router.get("")
def get_roster():
    return roster_store.list_students()


@router.get("/search")
def search_roster(q: str = "", limit: int = 50):
    return roster_store.search_students(q, limit=limit)


@router.post("", dependencies=[Depends(require_admin)])
def add_or_update_student(student: StudentIn):
    try:
        return roster_store.upsert_student(
            student.roll,
            student.name,
            student.cls,
            student.rfid_uid,
            student.guardian_phone,
            student.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{roll}", dependencies=[Depends(require_admin)])
def delete_student(roll: str):
    ok = roster_store.remove_student(roll)
    if not ok:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"removed": roll}
