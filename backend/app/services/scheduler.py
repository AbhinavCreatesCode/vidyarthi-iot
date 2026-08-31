"""
Two recurring jobs, both driven by AsyncIOScheduler so they share the
FastAPI event loop:

  * dropout scan   -- daily, early evening, well before the SMS batch so a
    same-day risk flag can be folded into that evening's message.
  * SMS batch       -- one consolidated dispatch per household at the
    configured time (default 7:30 PM), when parents are most likely to have
    the household's primary phone in hand.

Both are also exposed as on-demand REST triggers (see routers/) for testing
without waiting for the clock.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services import dropout_risk
from app.services.daily_summary import build_household_messages
from app.services.sms_gateway import send_sms
from app.ws_manager import manager

logger = logging.getLogger("vidyarthi.scheduler")

scheduler = AsyncIOScheduler()


async def run_dropout_scan_job() -> list[dict]:
    flags = dropout_risk.run_scan()
    for flag in flags:
        await manager.broadcast("risk_alert", flag)
    if flags:
        logger.info("dropout scan raised %d new flag(s)", len(flags))
    return flags


async def run_sms_batch_job() -> dict:
    messages = build_household_messages()
    results = {"sent": 0, "dry_run": 0, "failed": 0}
    for phone, text in messages.items():
        status = await send_sms(phone, text)
        results[status] = results.get(status, 0) + 1
    logger.info("SMS batch complete: %s", results)
    return results


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        run_dropout_scan_job,
        CronTrigger(hour=18, minute=0),
        id="dropout_scan",
        replace_existing=True,
    )
    scheduler.add_job(
        run_sms_batch_job,
        CronTrigger(hour=settings.sms_batch_hour, minute=settings.sms_batch_minute),
        id="sms_batch",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "scheduler started: dropout scan @18:00, SMS batch @%02d:%02d",
        settings.sms_batch_hour,
        settings.sms_batch_minute,
    )
