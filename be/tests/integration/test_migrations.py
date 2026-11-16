"""Migrations run against a separate, empty database on the same Postgres server:
upgrade → downgrade → upgrade must succeed, and the result must match the models."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from tests.integration.conftest import BE_DIR

DB_NAME = "gt_migration_check"


async def _admin(sql: str) -> None:
    url = make_url(os.environ["DATABASE_URL"])
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=url.database,
    )
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture
async def empty_db_url() -> AsyncIterator[str]:
    await _admin(f"DROP DATABASE IF EXISTS {DB_NAME}")
    await _admin(f"CREATE DATABASE {DB_NAME}")
    yield (
        make_url(os.environ["DATABASE_URL"])
        .set(database=DB_NAME)
        .render_as_string(hide_password=False)
    )
    await _admin(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)")


def _alembic(url: str, *args: str) -> str:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=BE_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout + result.stderr


async def test_migrations_upgrade_downgrade_and_match_models(empty_db_url: str) -> None:
    _alembic(empty_db_url, "upgrade", "head")
    _alembic(empty_db_url, "downgrade", "base")
    _alembic(empty_db_url, "upgrade", "head")
    assert "No new upgrade operations detected" in _alembic(empty_db_url, "check")
