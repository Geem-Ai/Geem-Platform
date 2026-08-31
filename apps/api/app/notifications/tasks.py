"""Celery tasks for transactional email (verification, password reset).

Delivery runs on the worker so a slow or failing SMTP hop can never turn a
registration into a 5xx. Each task receives only a user ID and mints the raw
token itself, keeping secrets off the broker; a retry simply invalidates the
undelivered token and mints a new one.
"""

from __future__ import annotations

import logging
import uuid

from app.db.session import SessionLocal
from app.notifications.factory import build_email_provider
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_RETRY = {
    "bind": True,
    "max_retries": 5,
    "autoretry_for": (Exception,),
    # A malformed payload will never become valid; only transport faults retry.
    # Celery reads this exact name; "dont_retry_for" is silently ignored.
    "dont_autoretry_for": (ValueError,),
    "retry_backoff": True,
    "retry_jitter": True,
    "retry_backoff_max": 600,
}


def _auth_service(db):
    from app.identity.service import AuthService

    return AuthService(db, email=build_email_provider())


@celery_app.task(name="send_email_verification", **_RETRY)
def send_email_verification(self, user_id: str) -> dict:
    identity = uuid.UUID(user_id)
    db = SessionLocal()
    try:
        delivered = _auth_service(db).deliver_verification_email(identity)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    logger.info(
        "email.verification_task_done",
        extra={"user_id": user_id, "delivered": delivered},
    )
    return {"user_id": user_id, "delivered": delivered}


@celery_app.task(name="send_password_reset", **_RETRY)
def send_password_reset(self, user_id: str) -> dict:
    identity = uuid.UUID(user_id)
    db = SessionLocal()
    try:
        delivered = _auth_service(db).deliver_password_reset_email(identity)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    logger.info(
        "email.password_reset_task_done",
        extra={"user_id": user_id, "delivered": delivered},
    )
    return {"user_id": user_id, "delivered": delivered}
