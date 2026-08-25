from __future__ import annotations

import uuid
from dataclasses import replace
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app.apps_catalog.seed as catalog_seed_module
import app.platform_admin.apps as platform_apps_module
from app.api_keys.scopes import SCOPE_AGENT_WRITE, normalize_scopes
from app.apps_catalog.access import AppAccessService
from app.apps_catalog.agent_product import (
    AGENT_REQUESTS_DAILY_ENTITLEMENT,
    AGENTS_AI_APP_SLUG,
    AGENTS_AI_PLAN_CODES,
)
from app.apps_catalog.models import (
    AppBillingType,
    AppPlan,
    AppPlanBillingInterval,
    AppPlanEntitlement,
    AppStatus,
    CatalogApp,
)
from app.apps_catalog.publication import validate_agents_ai_publish_ready
from app.apps_catalog.runtime_locks import (
    acquire_app_runtime_mutation_fence,
    acquire_runtime_admission_fences,
    begin_runtime_admission_transaction,
)
from app.apps_catalog.seed import APP_SPECS, PlanSpec
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.platform_admin.apps import PlatformAdminAppsService
from app.platform_admin.schemas import (
    PlatformAppPlanEntitlementIn,
    PlatformAppPlanUpdateRequest,
    PlatformAppUpdateRequest,
)


def _agents_app() -> CatalogApp:
    app = CatalogApp(
        id=uuid.uuid4(),
        slug=AGENTS_AI_APP_SLUG,
        name="Agents AI",
        short_description="Test fixture",
        description="Test fixture only",
        category_id=uuid.uuid4(),
        billing_type=AppBillingType.SUBSCRIPTION.value,
        status=AppStatus.COMING_SOON.value,
        connector_key=None,
        connector_kind=None,
    )
    plans: list[AppPlan] = []
    for index, code in enumerate(AGENTS_AI_PLAN_CODES):
        plan = AppPlan(
            id=uuid.uuid4(),
            app_id=app.id,
            code=code,
            name=code,
            billing_interval=AppPlanBillingInterval.MONTHLY.value,
            price_amount=Decimal("10.00") + index,
            currency="SAR",
            sort_order=(index + 1) * 10,
            is_default=index == 0,
            is_active=True,
        )
        plan.entitlements = [
            AppPlanEntitlement(
                app_plan_id=plan.id,
                key=AGENT_REQUESTS_DAILY_ENTITLEMENT,
                value=100 * (index + 1),
            )
        ]
        plans.append(plan)
    app.plans = plans
    return app


def _admin_service(app: CatalogApp) -> PlatformAdminAppsService:
    service = object.__new__(PlatformAdminAppsService)
    service.db = MagicMock()
    service.settings = Settings(_env_file=None, client_agent_api_enabled=True)
    service.repo = MagicMock()
    service.commerce = MagicMock()
    service._require_app = MagicMock(return_value=app)  # type: ignore[method-assign]
    service._audit_and_commit = MagicMock()  # type: ignore[method-assign]
    return service


def _signed_agents_seed_spec():
    base = next(item for item in APP_SPECS if item.slug == AGENTS_AI_APP_SLUG)
    plans = tuple(
        PlanSpec(
            code=code,
            name=code,
            description="Signed fixture values; not production pricing.",
            billing_interval=AppPlanBillingInterval.MONTHLY.value,
            price_amount=str(10 + index),
            currency="SAR",
            is_default=index == 0,
            sort_order=(index + 1) * 10,
            entitlements={
                AGENT_REQUESTS_DAILY_ENTITLEMENT: 100 * (index + 1)
            },
        )
        for index, code in enumerate(AGENTS_AI_PLAN_CODES)
    )
    return replace(base, plans=plans)


def test_agents_seed_is_coming_soon_without_invented_plans() -> None:
    spec = next(item for item in APP_SPECS if item.slug == AGENTS_AI_APP_SLUG)
    assert spec.status == AppStatus.COMING_SOON.value
    assert spec.billing_type == AppBillingType.SUBSCRIPTION.value
    assert spec.connector_key is None and spec.connector_kind is None
    assert spec.plans == ()
    assert spec.preserve_status is True


def test_signed_agents_seed_fences_before_mutation_and_validates_afterward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _signed_agents_seed_spec()
    app = _agents_app()
    app.status = AppStatus.PUBLISHED.value
    db = MagicMock()
    settings = Settings(_env_file=None, client_agent_api_enabled=True)
    events: list[str] = []

    monkeypatch.setattr(catalog_seed_module, "CATEGORY_SPECS", ())
    monkeypatch.setattr(catalog_seed_module, "APP_SPECS", (spec,))
    monkeypatch.setattr(
        catalog_seed_module,
        "acquire_app_runtime_mutation_fence",
        lambda target_db, slug: events.append(
            f"fence:{target_db is db}:{slug}"
        ),
    )

    def ensure(_repo, received_spec):
        assert received_spec is spec
        events.append("mutate")
        return app

    def validate(_repo, received_app, *, settings):
        assert received_app is app
        assert settings is settings_fixture
        events.append("validate")

    settings_fixture = settings
    monkeypatch.setattr(catalog_seed_module, "_ensure_app", ensure)
    monkeypatch.setattr(
        catalog_seed_module,
        "_validate_seeded_product_after_mutation",
        validate,
    )

    _categories, apps = catalog_seed_module.seed_app_catalog(
        db,
        settings=settings,
    )

    assert apps == [app]
    assert events == ["fence:True:agents-ai", "mutate", "validate"]
    db.flush.assert_called_once()


@pytest.mark.parametrize(
    "spec",
    [
        next(item for item in APP_SPECS if item.slug == AGENTS_AI_APP_SLUG),
        next(item for item in APP_SPECS if item.slug == "whatsapp"),
    ],
    ids=["agents-empty-coming-soon", "generic-app-with-plans"],
)
def test_empty_agents_and_generic_specs_keep_the_original_seed_path(
    monkeypatch: pytest.MonkeyPatch,
    spec,
) -> None:
    app = MagicMock()
    db = MagicMock()
    monkeypatch.setattr(catalog_seed_module, "CATEGORY_SPECS", ())
    monkeypatch.setattr(catalog_seed_module, "APP_SPECS", (spec,))
    monkeypatch.setattr(catalog_seed_module, "_ensure_app", lambda *_args: app)
    monkeypatch.setattr(
        catalog_seed_module,
        "acquire_app_runtime_mutation_fence",
        MagicMock(side_effect=AssertionError("unexpected runtime fence")),
    )
    monkeypatch.setattr(
        catalog_seed_module,
        "_validate_seeded_product_after_mutation",
        MagicMock(side_effect=AssertionError("unexpected product validation")),
    )

    _categories, apps = catalog_seed_module.seed_app_catalog(db)

    assert apps == [app]
    db.flush.assert_called_once()


def test_signed_seed_published_validation_refreshes_persisted_relationships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _agents_app()
    app.status = AppStatus.PUBLISHED.value
    loaded_plans = list(app.plans)
    refreshed = _agents_app()
    refreshed.status = AppStatus.PUBLISHED.value
    db = MagicMock()
    repo = MagicMock()
    repo.db = db
    repo.get_app_by_slug.return_value = refreshed
    settings = Settings(_env_file=None, client_agent_api_enabled=True)
    validator = MagicMock()
    monkeypatch.setattr(
        catalog_seed_module,
        "validate_product_publish_ready",
        validator,
    )

    catalog_seed_module._validate_seeded_product_after_mutation(
        repo,
        app,
        settings=settings,
    )

    db.flush.assert_called_once_with()
    for plan in loaded_plans:
        db.expire.assert_any_call(plan, ["entitlements"])
    db.expire.assert_any_call(app, ["plans"])
    repo.get_app_by_slug.assert_called_once_with(AGENTS_AI_APP_SLUG)
    validator.assert_called_once_with(refreshed, settings)


def test_signed_seed_does_not_require_launch_validation_while_coming_soon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _agents_app()
    db = MagicMock()
    repo = MagicMock()
    repo.db = db
    validator = MagicMock()
    monkeypatch.setattr(
        catalog_seed_module,
        "validate_product_publish_ready",
        validator,
    )

    catalog_seed_module._validate_seeded_product_after_mutation(
        repo,
        app,
        settings=Settings(_env_file=None, client_agent_api_enabled=False),
    )

    db.flush.assert_not_called()
    db.expire.assert_not_called()
    repo.get_app_by_slug.assert_not_called()
    validator.assert_not_called()


def test_agents_publication_requires_flag_and_locked_commercial_shape() -> None:
    app = _agents_app()
    with pytest.raises(AppError) as disabled:
        validate_agents_ai_publish_ready(
            app, Settings(_env_file=None, client_agent_api_enabled=False)
        )
    assert disabled.value.category == ErrorCategory.VALIDATION

    validate_agents_ai_publish_ready(
        app, Settings(_env_file=None, client_agent_api_enabled=True)
    )
    app.plans[0].entitlements[0].value = 0
    with pytest.raises(AppError) as invalid:
        validate_agents_ai_publish_ready(
            app, Settings(_env_file=None, client_agent_api_enabled=True)
        )
    assert invalid.value.category == ErrorCategory.VALIDATION


def test_agents_billing_identity_cannot_be_changed_around_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _agents_app()
    service = _admin_service(app)
    monkeypatch.setattr(
        platform_apps_module, "require_platform_admin_user", lambda _actor: None
    )
    monkeypatch.setattr(
        platform_apps_module,
        "acquire_app_runtime_mutation_fence",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(AppError) as blocked:
        service.update_app(
            object(),  # type: ignore[arg-type]
            app.id,
            PlatformAppUpdateRequest(billing_type=AppBillingType.FREE.value),
        )

    assert blocked.value.category == ErrorCategory.VALIDATION
    service._audit_and_commit.assert_not_called()  # type: ignore[attr-defined]


def test_published_agents_plan_quota_cannot_be_zeroed_after_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _agents_app()
    app.status = AppStatus.PUBLISHED.value
    plan = app.plans[0]
    service = _admin_service(app)
    service._require_plan = MagicMock(return_value=plan)  # type: ignore[method-assign]
    service.repo.plan_has_commercial_history.return_value = False
    service.repo.get_entitlement.return_value = plan.entitlements[0]
    monkeypatch.setattr(
        platform_apps_module, "require_platform_admin_user", lambda _actor: None
    )
    monkeypatch.setattr(
        platform_apps_module,
        "acquire_app_runtime_mutation_fence",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(AppError) as blocked:
        service.update_plan(
            object(),  # type: ignore[arg-type]
            app.id,
            plan.id,
            PlatformAppPlanUpdateRequest(
                entitlements=[
                    PlatformAppPlanEntitlementIn(
                        key=AGENT_REQUESTS_DAILY_ENTITLEMENT,
                        value=0,
                    )
                ]
            ),
        )

    assert blocked.value.category == ErrorCategory.VALIDATION
    service._audit_and_commit.assert_not_called()  # type: ignore[attr-defined]


def test_published_agents_cannot_gain_an_unvalidated_fourth_plan() -> None:
    app = _agents_app()
    app.status = AppStatus.PUBLISHED.value
    extra = AppPlan(
        id=uuid.uuid4(),
        app_id=app.id,
        code="agents-extra",
        name="Invalid extra plan",
        billing_interval=AppPlanBillingInterval.MONTHLY.value,
        price_amount=Decimal("99.00"),
        currency="SAR",
        sort_order=40,
        is_default=False,
        # Inactive plans are retained for existing subscribers, but cannot be
        # used to hide a fourth unreviewed commercial tier.
        is_active=False,
    )
    extra.entitlements = [
        AppPlanEntitlement(
            app_plan_id=extra.id,
            key=AGENT_REQUESTS_DAILY_ENTITLEMENT,
            value=999,
        )
    ]
    app.plans.append(extra)
    service = _admin_service(app)

    with pytest.raises(AppError) as blocked:
        service._validate_published_product_after_mutation(app)

    assert blocked.value.category == ErrorCategory.VALIDATION


def test_agents_validator_allows_a_launch_plan_to_stop_new_sales() -> None:
    app = _agents_app()
    app.plans[-1].is_active = False

    validate_agents_ai_publish_ready(
        app, Settings(_env_file=None, client_agent_api_enabled=True)
    )


def test_agent_scope_is_explicitly_allowlisted_but_not_defaulted() -> None:
    assert normalize_scopes([SCOPE_AGENT_WRITE]) == [SCOPE_AGENT_WRITE]
    assert SCOPE_AGENT_WRITE not in normalize_scopes(None)


def test_runtime_fences_are_one_ordered_shared_statement() -> None:
    db = MagicMock()
    acquire_runtime_admission_fences(
        db,
        workspace_id=uuid.UUID("00000000-0000-0000-0000-000000000123"),
        app_slugs=(AGENTS_AI_APP_SLUG,),
    )
    assert db.execute.call_count == 1
    sql = str(db.execute.call_args.args[0])
    assert sql.count("pg_advisory_xact_lock_shared") == 3
    assert sql.index("lock_0") < sql.index("lock_1") < sql.index("lock_2")


def test_seed_runtime_mutation_fence_is_one_exclusive_statement() -> None:
    db = MagicMock()

    acquire_app_runtime_mutation_fence(db, AGENTS_AI_APP_SLUG)

    db.execute.assert_called_once()
    sql = str(db.execute.call_args.args[0])
    assert "pg_advisory_xact_lock(" in sql
    assert "pg_advisory_xact_lock_shared" not in sql


def test_runtime_admission_rejects_non_read_committed_before_fences() -> None:
    db = MagicMock()
    db.in_transaction.return_value = False
    db.scalar.return_value = "repeatable read"

    with pytest.raises(AppError) as blocked:
        begin_runtime_admission_transaction(db)

    assert blocked.value.category == ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE
    assert blocked.value.retryable is True
    db.execute.assert_called_once()
    assert "SET TRANSACTION ISOLATION LEVEL READ COMMITTED" in str(
        db.execute.call_args.args[0]
    )


def test_runtime_access_database_failure_is_fail_closed() -> None:
    db = MagicMock()
    db.execute.side_effect = SQLAlchemyError("database unavailable")

    with pytest.raises(AppError) as blocked:
        AppAccessService(db).require_runtime_active(
            uuid.uuid4(),
            app_slug=AGENTS_AI_APP_SLUG,
            entitlement_keys=(AGENT_REQUESTS_DAILY_ENTITLEMENT,),
        )

    assert blocked.value.category == ErrorCategory.APP_RUNTIME_ACCESS_UNAVAILABLE
    assert blocked.value.retryable is True
