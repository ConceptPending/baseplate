from apscheduler.schedulers.asyncio import AsyncIOScheduler

import structlog

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()


def start_scheduler():
    """Start the scheduler. It ships with NO jobs — register your own here
    (e.g. `scheduler.add_job(my_job, IntervalTrigger(minutes=60))`) rather than
    shipping a placeholder that runs in every deployment.

    Note: jobs run in-process, so on a multi-instance / rolling deploy they fire
    on each instance. Add a distributed lock for anything non-idempotent.
    """
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
