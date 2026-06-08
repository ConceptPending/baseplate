import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import async_session
from app.services.submissions import SubmissionService

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()


async def _expire_stale_submissions() -> None:
    """Scheduled job: fire the submission lifecycle's system-only `expire`
    transition on every stale open submission. Idempotent — a second run (e.g.
    on another instance during a rolling deploy) finds them already expired and
    out of the open states, so it's safe to fire on every instance."""
    async with async_session() as db:
        count = await SubmissionService.expire_stale(db)
    if count:
        logger.info("submissions_expired", count=count)


def register_jobs() -> None:
    """Register the app's scheduled jobs. Separated from `start_scheduler` so it
    can be asserted in tests without spinning up the event-loop scheduler. Add
    new jobs here."""
    scheduler.add_job(
        _expire_stale_submissions,
        IntervalTrigger(hours=24),
        id="expire_stale_submissions",
        replace_existing=True,
    )


def start_scheduler():
    """Register jobs and start the scheduler.

    Note: jobs run in-process, so on a multi-instance / rolling deploy they fire
    on each instance. Keep jobs idempotent (as `_expire_stale_submissions` is)
    or add a distributed lock.
    """
    register_jobs()
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
