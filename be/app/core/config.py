from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-please-32b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql+asyncpg://globetrekker:globetrekker@localhost:5432/globetrekker"

    jwt_secret: str = DEV_JWT_SECRET
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 30

    public_app_url: str = "http://localhost:5173"
    cors_origins: str = ""  # comma separated
    # Turn off only for automated test stacks (e2e), never in production.
    rate_limit_enabled: bool = True

    sentry_dsn: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.is_production and (self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32):
            raise ValueError("JWT_SECRET must be set to at least 32 characters in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
