"""Celery application factory with graceful degradation.

When Redis is unavailable or Celery is not installed, ``celery_app`` is set
to ``None`` and all task submissions become safe no-ops.
"""

import logging
import os

logger = logging.getLogger(__name__)

celery_app = None

_TEST_MODE = os.environ.get("TIMMY_TEST_MODE") == "1"

if not _TEST_MODE:
    try:
        from celery import Celery
        from config import settings

        if not settings.celery_enabled:
            logger.info("Celery disabled via settings (celery_enabled=False)")
        else:
            celery_app = Celery("timmy")
            celery_app.conf.update(
                broker_url=settings.redis_url,
                result_backend=settings.redis_url,
                task_serializer="json",
                result_serializer="json",
                accept_content=["json"],
                result_expires=3600,
                task_track_started=True,
                worker_hijack_root_logger=False,
            )
            # Autodiscover tasks in the celery package
            celery_app.autodiscover_tasks(["infrastructure.celery"])
            logger.info("Celery app configured (broker=%s)", settings.redis_url)
    except ImportError:
        logger.info("Celery not installed — background tasks disabled")
    except Exception as exc:
        logger.warning("Celery setup failed (Redis down?): %s", exc)
        celery_app = None
else:
    logger.debug("Celery disabled in test mode")
