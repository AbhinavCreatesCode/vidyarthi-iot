from fastapi import APIRouter

from app.services import hardware

router = APIRouter(prefix="/hardware", tags=["hardware"])


@router.get("/status")
def get_hardware_status():
    """
    Latest known terminal heartbeat, dashboard-shaped. Backed by the same
    hardware_status table the WebSocket heartbeat handler writes to, so a
    freshly-loaded dashboard can show real link status immediately instead
    of waiting for the next heartbeat broadcast.
    """
    status = hardware.latest_status()
    if not status:
        return {"rssi": None, "online": False, "queue": 0}
    return {"rssi": status["rssi"], "online": bool(status["online"]), "queue": status["queue"]}
