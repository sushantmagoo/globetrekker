import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk
from app.models.enums import NotificationType, ReportTarget, pg_enum
from app.models.user import User


def _user_fk(**kw: object) -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        **kw,  # type: ignore[arg-type]
    )


def _journal_fk(**kw: object) -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journals.id", ondelete="CASCADE"),
        **kw,  # type: ignore[arg-type]
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (
        CheckConstraint("follower_id <> followee_id", name="not_self"),
        Index("ix_follows_followee_id_created_at", "followee_id", "created_at"),
    )

    follower_id: Mapped[uuid.UUID] = _user_fk(primary_key=True)
    followee_id: Mapped[uuid.UUID] = _user_fk(primary_key=True)
    created_at: Mapped[datetime] = _created_at()


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (Index("ix_likes_journal_id", "journal_id"),)

    user_id: Mapped[uuid.UUID] = _user_fk(primary_key=True)
    journal_id: Mapped[uuid.UUID] = _journal_fk(primary_key=True)
    created_at: Mapped[datetime] = _created_at()


class Bookmark(Base):
    __tablename__ = "bookmarks"

    user_id: Mapped[uuid.UUID] = _user_fk(primary_key=True)
    journal_id: Mapped[uuid.UUID] = _journal_fk(primary_key=True)
    created_at: Mapped[datetime] = _created_at()


class Comment(TimestampMixin, Base):
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_journal_id_created_at", "journal_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    journal_id: Mapped[uuid.UUID] = _journal_fk()
    author_id: Mapped[uuid.UUID] = _user_fk()
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(String(2000))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User] = relationship(lazy="raise")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_recipient_created", "recipient_id", text("created_at DESC")),
        Index(
            "ix_notifications_recipient_unread",
            "recipient_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    recipient_id: Mapped[uuid.UUID] = _user_fk()
    actor_id: Mapped[uuid.UUID] = _user_fk()
    type: Mapped[NotificationType] = mapped_column(pg_enum("notification_type"))
    journal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journals.id", ondelete="CASCADE")
    )
    comment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE")
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()

    actor: Mapped[User] = relationship(foreign_keys=[actor_id], lazy="raise")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    reporter_id: Mapped[uuid.UUID] = _user_fk()
    target_type: Mapped[ReportTarget] = mapped_column(pg_enum("report_target"))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(String(500))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _created_at()
