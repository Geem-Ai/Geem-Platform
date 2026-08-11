from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """Mixin for tenant-owned rows that soft-delete instead of hard-delete.

    Concrete models adopt this in later phases; included now for package hygiene.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, when: datetime | None = None) -> None:
        self.deleted_at = when or datetime.now(timezone.utc)
