"""Stable audit action names for security-sensitive mutations."""

from __future__ import annotations

from enum import StrEnum


class AuditAction(StrEnum):
    AUTH_PASSWORD_CHANGED = "auth.password_changed"
    AUTH_PASSWORD_RESET = "auth.password_reset"

    USER_DISABLED = "user.disabled"
    USER_ENABLED = "user.enabled"

    WORKSPACE_CREATED = "workspace.created"
    WORKSPACE_UPDATED = "workspace.updated"
    WORKSPACE_SOFT_DELETED = "workspace.soft_deleted"
    WORKSPACE_PURGED = "workspace.purged"
    WORKSPACE_DISABLED = "workspace.disabled"
    WORKSPACE_ENABLED = "workspace.enabled"

    MEMBER_ROLE_CHANGED = "workspace.member_role_changed"
    MEMBER_REMOVED = "workspace.member_removed"

    INVITE_CREATED = "workspace.invite_created"
    INVITE_RESENT = "workspace.invite_resent"
    INVITE_REVOKED = "workspace.invite_revoked"
    INVITE_ACCEPTED = "workspace.invite_accepted"

    ROLE_CREATED = "workspace.role_created"
    ROLE_UPDATED = "workspace.role_updated"
    ROLE_PERMISSIONS_CHANGED = "workspace.role_permissions_changed"
    ROLE_DELETED = "workspace.role_deleted"

    EXPERT_CREATED = "expert.created"
    EXPERT_UPDATED = "expert.updated"
    EXPERT_SOFT_DELETED = "expert.soft_deleted"
    EXPERT_PURGED = "expert.purged"

    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"

    BILLING_PURCHASE_PAID = "billing.purchase_paid"
    BILLING_PURCHASE_FAILED = "billing.purchase_failed"

    PLAN_CREATED = "plan.create"
    PLAN_UPDATED = "plan.update"
    PLAN_ACTIVATED = "plan.activate"
    PLAN_DEACTIVATED = "plan.deactivate"
    PLAN_ENTITLEMENTS_UPDATED = "plan.entitlements_update"

    WORKSPACE_SUBSCRIPTION_ASSIGNED = "workspace.subscription_assign"
    WORKSPACE_SUBSCRIPTION_CHANGED = "workspace.subscription_change"
    WORKSPACE_CREDIT_GRANTED = "workspace.credit_grant"

    APP_INSTALLED = "app.installed"
    APP_UNINSTALLED = "app.uninstalled"
    APP_PURCHASED = "app.purchased"
    APP_RENEWED = "app.renewed"
    APP_CONNECTION_CREATED = "app.connection.created"
    APP_CONNECTION_DISCONNECTED = "app.connection.disconnected"
    APP_CONNECTION_UPDATED = "app.connection.updated"
    APP_WIDGET_UPDATED = "app.widget.updated"

    CONVERSATION_SOFT_DELETED = "conversation.soft_deleted"
    CONVERSATION_PURGED = "conversation.purged"


class AuditEntityType(StrEnum):
    USER = "user"
    WORKSPACE = "workspace"
    MEMBERSHIP = "membership"
    INVITATION = "invitation"
    ROLE = "role"
    EXPERT = "expert"
    API_KEY = "api_key"
    PURCHASE = "purchase"
    PLAN = "plan"
    SUBSCRIPTION = "subscription"
    CREDIT_LEDGER_ENTRY = "credit_ledger_entry"
    APP_INSTALLATION = "app_installation"
    APP_CONNECTION = "app_connection"
    CONVERSATION = "conversation"
