"""Hand transactional email off to the worker once the request has committed.

The API tier has no mail egress path and delivery must not decide whether a
registration succeeds, so these helpers are the only way request handlers ask
for an email. Payloads carry a user ID only; the task mints the raw token.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.common.after_commit import run_after_commit


def enqueue_email_verification(user_id: uuid.UUID) -> None:
    from app.notifications.tasks import send_email_verification

    send_email_verification.delay(str(user_id))


def enqueue_password_reset(user_id: uuid.UUID) -> None:
    from app.notifications.tasks import send_password_reset

    send_password_reset.delay(str(user_id))


def enqueue_email_verification_after_commit(db: Session, user_id: uuid.UUID) -> None:
    run_after_commit(db, lambda: enqueue_email_verification(user_id))


def enqueue_password_reset_after_commit(db: Session, user_id: uuid.UUID) -> None:
    run_after_commit(db, lambda: enqueue_password_reset(user_id))
