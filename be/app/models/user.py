import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk
from app.models.enums import UserRole, UserStatus, Visibility, pg_enum


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("username::text ~ '^[a-z0-9_]{3,30}$'", name="username_format"),
        CheckConstraint(
            "follower_count >= 0 AND following_count >= 0 AND journal_count >= 0",
            name="counters_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    username: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    bio: Mapped[str | None] = mapped_column(String(500))
    home_country: Mapped[str | None] = mapped_column(CHAR(2))
    website_url: Mapped[str | None] = mapped_column(String(255))
    default_visibility: Mapped[Visibility] = mapped_column(
        pg_enum("visibility"), server_default=Visibility.public.value
    )

    role: Mapped[UserRole] = mapped_column(
        pg_enum("user_role"), server_default=UserRole.member.value
    )
    status: Mapped[UserStatus] = mapped_column(
        pg_enum("user_status"), server_default=UserStatus.active.value
    )

    follower_count: Mapped[int] = mapped_column(Integer, server_default="0")
    following_count: Mapped[int] = mapped_column(Integer, server_default="0")
    journal_count: Mapped[int] = mapped_column(Integer, server_default="0")

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
