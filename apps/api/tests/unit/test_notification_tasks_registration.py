"""The email tasks must be discoverable by the worker and retry only transport faults."""

from __future__ import annotations

import pytest


TASK_NAMES = ("send_email_verification", "send_password_reset")


@pytest.fixture(scope="module")
def celery_app():
    from app.worker.celery_app import celery_app as configured

    return configured


def test_worker_includes_the_notification_task_module(celery_app) -> None:
    assert "app.notifications.tasks" in celery_app.conf.include


@pytest.mark.parametrize("name", TASK_NAMES)
def test_task_is_registered(celery_app, name: str) -> None:
    import app.notifications.tasks  # noqa: F401

    assert name in celery_app.tasks


@pytest.mark.parametrize("name", TASK_NAMES)
def test_task_retries_transport_faults(celery_app, name: str) -> None:
    import app.notifications.tasks  # noqa: F401

    task = celery_app.tasks[name]
    assert task.autoretry_for == (Exception,)
    assert task.max_retries == 5
    assert task.retry_backoff is True


@pytest.mark.parametrize("name", TASK_NAMES)
def test_task_does_not_retry_a_payload_that_can_never_become_valid(
    celery_app, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    # Asserting the option name alone would not catch a misspelling, because
    # Celery accepts an unknown key as a plain task attribute and then retries
    # the bad payload anyway. Drive the autoretry wrapper instead: calling run()
    # directly avoids eager mode, where retry() collapses into a re-raise.
    import app.notifications.tasks  # noqa: F401

    task = celery_app.tasks[name]
    retries: list[BaseException | None] = []

    def record_retry(*_args, exc: BaseException | None = None, **_kwargs):
        retries.append(exc)
        raise AssertionError("a malformed payload must not be retried")

    monkeypatch.setattr(task, "retry", record_retry)
    with pytest.raises(ValueError):
        task.run("not-a-uuid")

    assert retries == []
