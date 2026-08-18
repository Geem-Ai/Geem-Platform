from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.soft_delete import SoftDeleteMixin
from app.db.session import Base
from app.workspaces.permissions import SystemRoleKey

if TYPE_CHECKING:
    from app.identity.models import User


class WorkspaceStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class WorkspaceKind(str, enum.Enum):
    """Workspace ownership class.

    - ``tenant`` — normal customer Workspace (selectable, membership-based).
    - ``system`` — internal platform scope (e.g. Platform Knowledge). Never a
      tenant current Workspace; no ordinary memberships; privileged services only.
    """

    TENANT = "tenant"
    SYSTEM = "system"


# Pre-10C static role enum (system_key values). Prefer SystemRoleKey in new code.
# Kept so existing tests can still import WorkspaceRole.OWNER / ADMIN / MEMBER.
class WorkspaceRole(str, enum.Enum):
    OWNER = SystemRoleKey.OWNER.value
    ADMIN = SystemRoleKey.ADMIN.value
    MEMBER = SystemRoleKey.MEMBER.value


class Permission(Base):
    """Global Geem-defined permission catalog. Tenants cannot invent keys."""

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name_key: Mapped[str] = mapped_column(String(200), nullable=False)
    description_key: Mapped[str] = mapped_column(String(200), nullable=False)
    group_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    role_links: Mapped[list[WorkspaceRolePermission]] = relationship(
        back_populates="permission"
    )


class WorkspaceRoleDef(Base):
    """Workspace-scoped role. Owner is a protected system role (is_owner_role)."""

    __tablename__ = "workspace_roles"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "name_normalized",
            name="uq_workspace_roles_workspace_name",
        ),
        Index(
            "uq_workspace_roles_workspace_system_key",
            "workspace_id",
            "system_key",
            unique=True,
            postgresql_where=text("system_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_owner_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship(back_populates="roles")
    permission_links: Mapped[list[WorkspaceRolePermission]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
    memberships: Mapped[list[WorkspaceMembership]] = relationship(back_populates="workspace_role")
    invitations: Mapped[list[WorkspaceInvitation]] = relationship(back_populates="workspace_role")

    @property
    def permissions(self) -> list[Permission]:
        return [link.permission for link in self.permission_links]


class WorkspaceRolePermission(Base):
    __tablename__ = "workspace_role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_workspace_role_permission"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )

    role: Mapped[WorkspaceRoleDef] = relationship(back_populates="permission_links")
    permission: Mapped[Permission] = relationship(back_populates="role_links")


class Workspace(Base, SoftDeleteMixin):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default=WorkspaceKind.TENANT.value, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=WorkspaceStatus.ACTIVE.value, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped[User | None] = relationship(back_populates="created_workspaces")
    memberships: Mapped[list[WorkspaceMembership]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    invitations: Mapped[list[WorkspaceInvitation]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    roles: Mapped[list[WorkspaceRoleDef]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )

    @property
    def is_system(self) -> bool:
        return self.kind == WorkspaceKind.SYSTEM.value

    @property
    def is_tenant(self) -> bool:
        return self.kind == WorkspaceKind.TENANT.value


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_membership"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
    workspace_role: Mapped[WorkspaceRoleDef] = relationship(
        back_populates="memberships", foreign_keys=[role_id]
    )

    @property
    def role(self) -> str:
        """Legacy string for logs: system_key when present, else role display name."""
        row = self.workspace_role
        if row is None:
            return WorkspaceRole.MEMBER.value
        if row.system_key:
            return row.system_key
        return row.name

    @property
    def is_owner(self) -> bool:
        row = self.workspace_role
        return bool(row is not None and row.is_owner_role)


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class WorkspaceInvitation(Base):
    """Tokenized email invitation. Raw tokens are never persisted."""

    __tablename__ = "workspace_invitations"
    __table_args__ = (
        Index(
            "uq_workspace_invitations_pending_email",
            "workspace_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
        Index(
            "ix_workspace_invitations_workspace_pending",
            "workspace_id",
            "created_at",
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
        UniqueConstraint("token_hash", name="uq_workspace_invitations_token_hash"),
        CheckConstraint(
            "NOT (accepted_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name="ck_workspace_invitations_terminal_state",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship(back_populates="invitations")
    inviter: Mapped[User] = relationship(foreign_keys=[invited_by])
    workspace_role: Mapped[WorkspaceRoleDef] = relationship(
        back_populates="invitations", foreign_keys=[role_id]
    )

    @property
    def role(self) -> str:
        row = self.workspace_role
        if row is None:
            return WorkspaceRole.MEMBER.value
        if row.system_key:
            return row.system_key
        return row.name

    def derived_status(self, *, now: datetime | None = None) -> InvitationStatus:
        if self.accepted_at is not None:
            return InvitationStatus.ACCEPTED
        if self.revoked_at is not None:
            return InvitationStatus.REVOKED
        when = now or datetime.now(timezone.utc)
        expiry = self.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= when:
            return InvitationStatus.EXPIRED
        return InvitationStatus.PENDING
