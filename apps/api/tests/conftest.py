from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Ensure test settings before app import.
os.environ["APP_ENV"] = "test"
os.environ.setdefault("APP_ROOT_DOMAIN", "geem.dm")
os.environ["AUTH_REQUIRED"] = "true"
os.environ["LEGACY_MVP_WRITES_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-jwt-secret-not-for-production"
# Avoid shared Redis IP buckets flaking identity tests when the suite is re-run within 60s.
os.environ.setdefault("AUTH_RATE_LIMIT_PER_MINUTE", "10000")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://mai@localhost:5432/geem_test",
)
# Host .env ClickPay keys must not flip the test suite onto a live gateway.
os.environ["CLICKPAY_PROFILE_ID"] = ""
os.environ["CLICKPAY_SERVER_KEY"] = ""

from app.core.config import get_settings

get_settings.cache_clear()

from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> Generator[None, None, None]:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    # Import domain models onto metadata.
    import app.db.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_tables() -> Generator[None, None, None]:
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE "
                "purchases, credit_packs, payment_gateway_configs, "
                "ai_usage_reservations, storage_reservations, workspace_resource_usage, "
                "storage_usage_events, usage_period_counters, credit_ledger_entries, "
                "credit_accounts, subscriptions, plan_entitlements, plans, "
                "messages, conversations, "
                "expert_documents, expert_sources, workspace_expert_grants, experts, "
                "usage_events, chunks, document_pages, ingestion_jobs, documents, "
                "sessions, workspace_memberships, workspaces, users "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def register_user(client: TestClient):
    def _register(
        email: str | None = None,
        password: str = "password123",
    ) -> dict:
        mail = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
        res = client.post("/api/auth/register", json={"email": mail, "password": password})
        assert res.status_code == 200, res.text
        body = res.json()
        body["_password"] = password
        body["_email"] = mail
        body["_refresh"] = res.cookies.get(get_settings().refresh_cookie_name)
        return body

    return _register
