import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk
from app.models.enums import JournalStatus, Visibility, pg_enum
from app.models.user import User

journal_tags = Table(
    "journal_tags",
    Base.metadata,
    Column(
        "journal_id",
        UUID(as_uuid=True),
        ForeignKey("journals.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    ),
    Index("ix_journal_tags_tag_id_journal_id", "tag_id", "journal_id"),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(CITEXT, unique=True)
    journal_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Trip(TimestampMixin, Base):
    __tablename__ = "trips"
    __table_args__ = (
        UniqueConstraint("owner_id", "slug", name="uq_trips_owner_id_slug"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="dates_ordered"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140))
    description: Mapped[str | None] = mapped_column(String(2000))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    visibility: Mapped[Visibility] = mapped_column(
        pg_enum("visibility"), server_default=Visibility.public.value
    )


# `immutable_unaccent` is created in the first migration: Postgres' unaccent() is not
# IMMUTABLE, so it can't be used directly in a generated column.
SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('simple'::regconfig, immutable_unaccent(coalesce(title, ''))), 'A') || "
    "setweight(to_tsvector('simple'::regconfig, immutable_unaccent(coalesce(excerpt, ''))), 'B') || "
    "setweight(to_tsvector('simple'::regconfig, immutable_unaccent(coalesce(content_text, ''))), 'C')"
)


class Journal(TimestampMixin, Base):
    __tablename__ = "journals"
    __table_args__ = (
        CheckConstraint("(lat IS NULL) = (lng IS NULL)", name="lat_lng_together"),
        CheckConstraint("lat IS NULL OR (lat BETWEEN -90 AND 90)", name="lat_range"),
        CheckConstraint("lng IS NULL OR (lng BETWEEN -180 AND 180)", name="lng_range"),
        CheckConstraint(
            "travel_end IS NULL OR travel_start IS NULL OR travel_end >= travel_start",
            name="travel_dates_ordered",
        ),
        CheckConstraint(
            "like_count >= 0 AND comment_count >= 0 AND bookmark_count >= 0",
            name="counters_non_negative",
        ),
        Index(
            "ix_journals_author_published",
            "author_id",
            text("published_at DESC"),
            postgresql_where=text("status = 'published' AND deleted_at IS NULL"),
        ),
        Index(
            "ix_journals_public_recent",
            text("published_at DESC"),
            text("id DESC"),
            postgresql_where=text(
                "status = 'published' AND visibility = 'public' AND deleted_at IS NULL"
            ),
        ),
        Index(
            "ix_journals_author_drafts",
            "author_id",
            text("updated_at DESC"),
            postgresql_where=text("status = 'draft' AND deleted_at IS NULL"),
        ),
        Index(
            "ix_journals_public_country",
            "country_code",
            postgresql_where=text(
                "status = 'published' AND visibility = 'public' AND deleted_at IS NULL"
            ),
        ),
        Index("ix_journals_trip_position", "trip_id", "trip_position"),
        Index("ix_journals_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="SET NULL")
    )
    trip_position: Mapped[int | None] = mapped_column(Integer)

    slug: Mapped[str] = mapped_column(String(140), unique=True)
    title: Mapped[str] = mapped_column(String(200), server_default="")
    subtitle: Mapped[str | None] = mapped_column(String(300))

    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("""'{"type": "doc", "content": []}'::jsonb""")
    )
    content_html: Mapped[str] = mapped_column(Text, server_default="")
    content_text: Mapped[str] = mapped_column(Text, server_default="")
    excerpt: Mapped[str] = mapped_column(String(300), server_default="")

    status: Mapped[JournalStatus] = mapped_column(
        pg_enum("journal_status"), server_default=JournalStatus.draft.value
    )
    visibility: Mapped[Visibility] = mapped_column(pg_enum("visibility"))
    share_token: Mapped[str] = mapped_column(String(32), unique=True)

    place_name: Mapped[str | None] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(CHAR(2))
    lat: Mapped[float | None] = mapped_column(Double)
    lng: Mapped[float | None] = mapped_column(Double)
    travel_start: Mapped[date | None] = mapped_column(Date)
    travel_end: Mapped[date | None] = mapped_column(Date)

    word_count: Mapped[int] = mapped_column(Integer, server_default="0")
    reading_minutes: Mapped[int] = mapped_column(Integer, server_default="0")
    like_count: Mapped[int] = mapped_column(Integer, server_default="0")
    comment_count: Mapped[int] = mapped_column(Integer, server_default="0")
    bookmark_count: Mapped[int] = mapped_column(Integer, server_default="0")

    version: Mapped[int] = mapped_column(Integer, server_default="1")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True), deferred=True
    )

    author: Mapped[User] = relationship(lazy="raise")
    tags: Mapped[list[Tag]] = relationship(secondary=journal_tags, lazy="raise", order_by=Tag.name)
