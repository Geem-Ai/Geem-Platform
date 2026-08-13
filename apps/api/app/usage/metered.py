"""Reserve / settle / release around a Workspace LLM request (Chat or /api/query)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.usage.ai_usage import AiUsageService
from app.usage.attribution import GenerationUsageContext
from app.usage.weights import settled_tokens_from_payload

logger = logging.getLogger(__name__)


class MeteredWorkspaceGeneration:
    """One billable request_id with explicit reserve → settle or release."""

    def __init__(
        self,
        db: Session,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        expert_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        api_key_id: uuid.UUID | None = None,
        request_id: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.expert_id = expert_id
        self.conversation_id = conversation_id
        self.message_id = message_id
        self.api_key_id = api_key_id
        self.request_id = (request_id or str(uuid.uuid4())).strip()
        self._closed = False
        self._context = GenerationUsageContext(
            workspace_id=workspace_id,
            user_id=user_id,
            expert_id=expert_id,
            conversation_id=conversation_id,
            message_id=message_id,
            api_key_id=api_key_id,
            request_id=self.request_id,
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def context(self) -> GenerationUsageContext:
        return self._context

    def reserve(self) -> GenerationUsageContext:
        AiUsageService(self.db, self.settings).reserve_ai_usage(
            self.workspace_id,
            self.request_id,
            self.settings.effective_ai_usage_reservation_tokens,
            conversation_id=self.conversation_id,
            message_id=self.message_id,
            user_id=self.user_id,
            expert_id=self.expert_id,
        )
        self.db.commit()
        return self._context

    def settle(self, payload: dict[str, Any] | None) -> None:
        if self._closed:
            return
        actual = settled_tokens_from_payload(
            self.settings,
            payload,
            extra_billed=self._context.extra_billed_tokens,
        )
        AiUsageService(self.db, self.settings).settle_ai_usage(
            self.workspace_id, self.request_id, actual
        )
        self.db.commit()
        self._closed = True

    def release(self) -> None:
        if self._closed:
            return
        extra = self._context.extra_billed_tokens
        if extra > 0:
            try:
                AiUsageService(self.db, self.settings).settle_ai_usage(
                    self.workspace_id, self.request_id, extra
                )
                self.db.commit()
                self._closed = True
                return
            except Exception:  # noqa: BLE001
                logger.exception("metered_generation_extra_settle_failed")
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
        try:
            self.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        try:
            AiUsageService(self.db, self.settings).release_ai_usage(
                self.workspace_id, self.request_id
            )
            self.db.commit()
        except AppError as exc:
            if exc.category != ErrorCategory.NOT_FOUND:
                self.db.rollback()
                logger.exception("metered_generation_release_failed")
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.exception("metered_generation_release_failed")
        self._closed = True
