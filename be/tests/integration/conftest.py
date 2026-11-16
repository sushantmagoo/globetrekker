"""Test setup: a real Postgres 18 (testcontainers, or TEST_DATABASE_URL), migrated with
Alembic, truncated between tests. Settings are read at import time, so the environment
must be prepared before any `app.*` import."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

BE_DIR = Path(__file__).resolve().parents[2]
_container: Any = None


def _database_url() -> str:
    global _container
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    from testcontainers.community.postgres import PostgresContainer

    _container = PostgresContainer("postgres:18-alpine", driver="asyncpg")
    _container.start()
    return str(_container.get_connection_url())


os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = _database_url()
os.environ["PUBLIC_APP_URL"] = "http://testserver"

subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BE_DIR, check=True, env=os.environ
)

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

TABLES = (
    "notifications, reports, comments, likes, bookmarks, follows, journal_tags, tags, "
    "journals, trips, refresh_tokens, users"
)
PASSWORD = "correct-horse-battery"


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _container is not None:
        _container.stop()


@pytest.fixture(autouse=True)
async def _clean_db() -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


def new_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with new_client() as c:
        yield c


UserFactory = Callable[..., Awaitable[AsyncClient]]


@pytest.fixture
async def make_user() -> AsyncIterator[UserFactory]:
    """Create a signed-up user; returns an authed client."""
    clients: list[AsyncClient] = []

    async def _make(username: str) -> AsyncClient:
        c = new_client()
        clients.append(c)
        r = await c.post(
            "/api/v1/auth/signup",
            json={
                "email": f"{username}@example.com",
                "password": PASSWORD,
                "username": username,
                "display_name": username.title(),
            },
        )
        assert r.status_code == 201, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        return c

    yield _make
    for c in clients:
        await c.aclose()


def doc(*paragraphs: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paragraphs
        ],
    }


async def published_journal(
    c: AsyncClient, title: str = "Sunrise over Bagan", visibility: str = "public", **extra: Any
) -> dict[str, Any]:
    created = (await c.post("/api/v1/journals")).json()
    r = await c.patch(
        f"/api/v1/journals/{created['id']}",
        json={
            "version": created["version"],
            "title": title,
            "content_json": doc("We woke at four to watch the balloons rise over the temples."),
            "visibility": visibility,
            **extra,
        },
    )
    assert r.status_code == 200, r.text
    r = await c.post(f"/api/v1/journals/{created['id']}/publish")
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data
