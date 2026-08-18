"""Workspace App Store HTTP API (Phase 9A/9B)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.apps_catalog.commerce import AppCommerceService
from app.apps_catalog.policy import require_browse, require_manage_apps
from app.apps_catalog.schemas import (
    AppCategoryOut,
    AppCheckoutRequest,
    AppInstallationListOut,
    AppInstallationOut,
    AppRenewRequest,
    CatalogAppListOut,
    CatalogAppOut,
)
from app.apps_catalog.service import AppCatalogService, AppInstallationService
from app.billing.checkout_router import _checkout_out, _spa_origin_from_request
from app.billing.schemas import CheckoutOut
from app.db.session import get_db
from app.identity.dependencies import client_ip, get_current_user
from app.identity.models import User
from app.workspaces.dependencies import require_workspace
from app.workspaces.models import Workspace, WorkspaceMembership

router = APIRouter(prefix="/api/apps", tags=["apps"])


@router.get("/categories", response_model=list[AppCategoryOut])
def list_categories(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> list[AppCategoryOut]:
    workspace, membership = pair
    require_browse(membership)
    _ = workspace
    return AppCatalogService(db).list_categories()


@router.get("/installations", response_model=AppInstallationListOut)
def list_installations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> AppInstallationListOut:
    workspace, membership = pair
    require_browse(membership)
    return AppInstallationService(db).list_installations(
        workspace=workspace,
        membership=membership,
        limit=limit,
        offset=offset,
    )


@router.get("/installations/{installation_id}", response_model=AppInstallationOut)
def get_installation(
    installation_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> AppInstallationOut:
    workspace, membership = pair
    require_browse(membership)
    return AppInstallationService(db).get_installation(
        workspace=workspace,
        membership=membership,
        installation_id=installation_id,
    )


@router.get("", response_model=CatalogAppListOut)
def list_apps(
    category: str | None = Query(None),
    billing_type: str | None = Query(None),
    installed: bool | None = Query(None),
    q: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> CatalogAppListOut:
    workspace, membership = pair
    require_browse(membership)
    return AppCatalogService(db).list_apps(
        workspace=workspace,
        membership=membership,
        category=category,
        billing_type=billing_type,
        installed=installed,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/{app_slug}", response_model=CatalogAppOut)
def get_app(
    app_slug: str,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> CatalogAppOut:
    workspace, membership = pair
    require_browse(membership)
    return AppCatalogService(db).get_app(
        workspace=workspace,
        membership=membership,
        slug=app_slug,
    )


@router.post("/{app_slug}/checkout", response_model=CheckoutOut)
def checkout_app(
    app_slug: str,
    body: AppCheckoutRequest,
    request: Request,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    workspace, membership = pair
    require_manage_apps(membership)
    purchase, _token = AppCommerceService(db).create_checkout(
        workspace,
        user,
        app_slug=app_slug,
        plan_id=body.plan_id,
        customer_ip=client_ip(request),
        spa_origin=_spa_origin_from_request(request),
    )
    db.commit()
    return _checkout_out(purchase)


@router.post("/{app_slug}/renew", response_model=CheckoutOut)
def renew_app(
    app_slug: str,
    request: Request,
    body: AppRenewRequest | None = None,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    workspace, membership = pair
    require_manage_apps(membership)
    plan_id = body.plan_id if body else None
    purchase, _token = AppCommerceService(db).create_renewal_checkout(
        workspace,
        user,
        app_slug=app_slug,
        plan_id=plan_id,
        customer_ip=client_ip(request),
        spa_origin=_spa_origin_from_request(request),
    )
    db.commit()
    return _checkout_out(purchase)


@router.post("/{app_slug}/install", response_model=AppInstallationOut, status_code=201)
def install_app(
    app_slug: str,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> AppInstallationOut:
    workspace, membership = pair
    require_manage_apps(membership)
    return AppInstallationService(db).install_app(
        workspace=workspace,
        actor_id=membership.user_id,
        slug=app_slug,
    )


@router.delete("/{app_slug}/install", response_model=AppInstallationOut)
def uninstall_app(
    app_slug: str,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> AppInstallationOut:
    workspace, membership = pair
    require_manage_apps(membership)
    return AppInstallationService(db).uninstall_app(
        workspace=workspace,
        actor_id=membership.user_id,
        slug=app_slug,
    )
