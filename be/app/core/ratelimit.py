"""In-memory rate limiting (per worker process). See spec §4.4."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    enabled=_settings.rate_limit_enabled and _settings.app_env != "test",
    headers_enabled=False,
)
