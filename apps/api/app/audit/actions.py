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

    PLATFORM_EXPERT_CREATED = "platform_expert.create"
    PLATFORM_EXPERT_UPDATED = "platform_expert.update"
    PLATFORM_EXPERT_PUBLISHED = "platform_expert.publish"
    PLATFORM_EXPERT_UNPUBLISHED = "platform_expert.unpublish"
    PLATFORM_EXPERT_ACCESS_ALL_ENABLE = "platform_expert.access_all_enable"
    PLATFORM_EXPERT_ACCESS_ALL_DISABLE = "platform_expert.access_all_disable"
    PLATFORM_EXPERT_WORKSPACE_GRANT = "platform_expert.workspace_grant"
    PLATFORM_EXPERT_WORKSPACE_REVOKE = "platform_expert.workspace_revoke"
    PLATFORM_EXPERT_KNOWLEDGE_UPLOAD = "platform_expert.knowledge_upload"
    PLATFORM_EXPERT_KNOWLEDGE_REPROCESS = "platform_expert.knowledge_reprocess"
    PLATFORM_EXPERT_KNOWLEDGE_REMOVE = "platform_expert.knowledge_remove"
    PLATFORM_EXPERT_SOFT_DELETED = "platform_expert.soft_deleted"

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

    APP_CREATED = "app.create"
    APP_UPDATED = "app.update"
    APP_PUBLISHED = "app.publish"
    APP_UNPUBLISHED = "app.unpublish"
    APP_COMING_SOON = "app.set_coming_soon"
    APP_DISABLED = "app.disable"
    APP_PLAN_CREATED = "app_plan.create"
    APP_PLAN_UPDATED = "app_plan.update"
    APP_PLAN_ACTIVATED = "app_plan.activate"
    APP_PLAN_DEACTIVATED = "app_plan.deactivate"
    APP_PLAN_ENTITLEMENTS_UPDATED = "app_plan.entitlements_update"
    APP_LICENSE_GRANTED = "app_license.grant"
    APP_LICENSE_REVOKED = "app_license.revoke"
    APP_SUBSCRIPTION_GRANTED = "app_subscription.grant"
    APP_SUBSCRIPTION_EXTENDED = "app_subscription.extend"
    APP_SUBSCRIPTION_REVOKED = "app_subscription.revoke"
    APP_INSTALLATION_ADMIN = "app_installation.admin_install"

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
    CATALOG_APP = "catalog_app"
    APP_PLAN = "app_plan"
    APP_LICENSE = "app_license"
    APP_SUBSCRIPTION = "app_subscription"
    CONVERSATION = "conversation"
