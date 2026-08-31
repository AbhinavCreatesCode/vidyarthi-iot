import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import attendance, dropout, feedback, hardware, ration, roster, sms, ws
from app.routers import telegram_webhook
from app.services.scheduler import scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("vidyarthi.main")

STATIC_DIR = Path(__file__).resolve().parent / "static"
DASHBOARD_FILE = STATIC_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    logger.info("Vidyarthi-IoT backend ready.")
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("scheduler stopped")


app = FastAPI(
    title="Vidyarthi-IoT Backend",
    description="ESP32/RC522 school attendance, teacher-authenticated feedback, ration distribution, dropout early-warning, and Telegram notifications.",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(roster.router)
app.include_router(attendance.router)
app.include_router(feedback.router)
app.include_router(ration.router)
app.include_router(dropout.router)
app.include_router(sms.router)
app.include_router(telegram_webhook.router)
app.include_router(hardware.router)
app.include_router(ws.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if DASHBOARD_FILE.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def serve_dashboard():
        return FileResponse(DASHBOARD_FILE)
