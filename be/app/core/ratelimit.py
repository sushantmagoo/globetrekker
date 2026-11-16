"""In-memory rate limiting (per worker process). See spec §4.4."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=get_settings().app_env != "test",
    headers_enabled=False,
)
