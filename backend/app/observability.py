"""Error-reporting seam.

This is the single, documented place to plug in an error-monitoring service
(Sentry, GlitchTip, Honeybadger, …). The base ships with **no** such
dependency — `report_exception` just emits a structured log. To wire a real
reporter, install its SDK and call it from inside `report_exception`, e.g.:

    import sentry_sdk
    sentry_sdk.init(dsn=settings.sentry_dsn)  # in app startup

    def report_exception(exc, **context):
        sentry_sdk.capture_exception(exc)
        logger.error("unhandled_exception", error=str(exc), **context)

Keeping every reporting call behind this one function means the rest of the
app never imports a vendor SDK directly, and swapping providers is a one-file
change.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


def report_exception(exc: BaseException, **context: object) -> None:
    """Record an unhandled exception. Default: structured log only.

    `context` is arbitrary key/values (request path, user id, …) that get
    attached to the log event and would map to tags/extra on a real reporter.
    The active request_id is already bound via structlog contextvars, so it
    appears automatically.
    """
    logger.error("unhandled_exception", error=str(exc), error_type=type(exc).__name__, **context)
