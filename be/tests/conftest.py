"""Shared pytest setup.

- tests/unit:        pure logic, no database or network (fast).
- tests/integration: real HTTP through FastAPI into a real Postgres 18
                     (testcontainers, or TEST_DATABASE_URL in CI).
"""

import os

os.environ.setdefault("APP_ENV", "test")
