"""The scheduler wires the submission expiry job. Behaviour of the job itself
is covered by test_submission_lifecycle_api.py::test_scheduled_expire_only_
touches_stale; here we just assert it's registered (without starting the
event-loop scheduler)."""

from app.tasks.scheduler import register_jobs, scheduler


def test_expire_job_is_registered():
    register_jobs()
    job = scheduler.get_job("expire_stale_submissions")
    assert job is not None
    # Daily cadence.
    assert int(job.trigger.interval.total_seconds()) == 24 * 3600
