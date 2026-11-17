import base64
import json
import re
import secrets
import string
import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy import Select, delete, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.content.render import ContentError, render_document
from app.core.errors import ProblemError, bad_request, conflict, not_found
from app.core.telemetry import JOURNEY, tracer
from app.models import (
    Bookmark,
    Journal,
    JournalStatus,
    Like,
    Tag,
    User,
    journal_tags,
)
from app.schemas import JournalCard, JournalDetail, JournalEditOut, JournalUpdateIn, UserSummary

# Journey events carry `journey` so Grafana can show them next to the request logs.
log = structlog.get_logger(journey=JOURNEY)

BASE62 = string.ascii_letters + string.digits
SLUG_SUFFIX_LEN = 6


def slugify(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_title).strip("-").lower()
    return slug[:120].strip("-") or "untitled"


def new_slug(title: str, suffix: str | None = None) -> str:
    suffix = suffix or "".join(secrets.choice(BASE62) for _ in range(SLUG_SUFFIX_LEN))
    return f"{slugify(title)}-{suffix}"


def new_share_token() -> str:
    return secrets.token_urlsafe(18)  # 24 chars


# ---------- cursors ----------
def encode_cursor(published_at: datetime, journal_id: uuid.UUID) -> str:
    raw = json.dumps([published_at.isoformat(), str(journal_id)])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        ts, jid = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(ts), uuid.UUID(jid)
    except (ValueError, TypeError) as exc:
        raise bad_request("Invalid cursor") from exc


def with_card_relations(stmt: Select[Journal]) -> Select[Journal]:
    return stmt.options(selectinload(Journal.author), selectinload(Journal.tags))


async def paginate_published(
    session: AsyncSession, stmt: Select[Journal], cursor: str | None, limit: int
) -> tuple[Sequence[Journal], str | None]:
    """Keyset pagination on (published_at DESC, id DESC)."""
    if cursor:
        ts, jid = decode_cursor(cursor)
        stmt = stmt.where(tuple_(Journal.published_at, Journal.id) < tuple_(ts, jid))
    stmt = (
        with_card_relations(stmt)
        .order_by(Journal.published_at.desc(), Journal.id.desc())
        .limit(limit + 1)
    )
    rows = (await session.scalars(stmt)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        assert last.published_at is not None
        next_cursor = encode_cursor(last.published_at, last.id)
    return rows, next_cursor


# ---------- serialisation ----------
async def viewer_flags(
    session: AsyncSession, viewer: User | None, journal_ids: Sequence[uuid.UUID]
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    if viewer is None or not journal_ids:
        return set(), set()
    liked = set(
        await session.scalars(
            select(Like.journal_id).where(
                Like.user_id == viewer.id, Like.journal_id.in_(journal_ids)
            )
        )
    )
    bookmarked = set(
        await session.scalars(
            select(Bookmark.journal_id).where(
                Bookmark.user_id == viewer.id, Bookmark.journal_id.in_(journal_ids)
            )
        )
    )
    return liked, bookmarked


def _card_fields(j: Journal, *, raw_title: bool = False) -> dict[str, object]:
    return {
        "id": j.id,
        "slug": j.slug,
        "title": j.title if raw_title else (j.title or "Untitled"),
        "subtitle": j.subtitle,
        "excerpt": j.excerpt,
        "author": UserSummary.model_validate(j.author),
        "status": j.status,
        "visibility": j.visibility,
        "place_name": j.place_name,
        "country_code": j.country_code,
        "lat": j.lat,
        "lng": j.lng,
        "travel_start": j.travel_start,
        "travel_end": j.travel_end,
        "reading_minutes": j.reading_minutes,
        "like_count": j.like_count,
        "comment_count": j.comment_count,
        "tags": [t.name for t in j.tags],
        "published_at": j.published_at,
        "updated_at": j.updated_at,
    }


async def to_cards(
    session: AsyncSession, journals: Sequence[Journal], viewer: User | None
) -> list[JournalCard]:
    liked, bookmarked = await viewer_flags(session, viewer, [j.id for j in journals])
    return [
        JournalCard(
            **_card_fields(j),  # type: ignore[arg-type]
            liked_by_me=j.id in liked,
            bookmarked_by_me=j.id in bookmarked,
        )
        for j in journals
    ]


async def to_detail(session: AsyncSession, j: Journal, viewer: User | None) -> JournalDetail:
    liked, bookmarked = await viewer_flags(session, viewer, [j.id])
    is_owner = viewer is not None and viewer.id == j.author_id
    return JournalDetail(
        **_card_fields(j),  # type: ignore[arg-type]
        liked_by_me=j.id in liked,
        bookmarked_by_me=j.id in bookmarked,
        content_html=j.content_html,
        word_count=j.word_count,
        is_owner=is_owner,
        share_token=j.share_token if is_owner else None,
    )


def to_edit(j: Journal) -> JournalEditOut:
    return JournalEditOut(
        **_card_fields(j, raw_title=True),  # type: ignore[arg-type]
        content_html=j.content_html,
        word_count=j.word_count,
        is_owner=True,
        share_token=j.share_token,
        content_json=j.content_json,
        version=j.version,
    )


# ---------- loading ----------
async def get_by_slug(session: AsyncSession, slug: str) -> Journal:
    journal = await session.scalar(
        with_card_relations(select(Journal)).where(
            Journal.slug == slug, Journal.deleted_at.is_(None)
        )
    )
    if journal is None:
        raise not_found("Journal")
    return journal


async def get_owned(
    session: AsyncSession, journal_id: uuid.UUID, owner: User, *, lock: bool = False
) -> Journal:
    stmt = with_card_relations(select(Journal)).where(
        Journal.id == journal_id, Journal.deleted_at.is_(None)
    )
    if lock:
        stmt = stmt.with_for_update(of=Journal)
    journal = await session.scalar(stmt)
    # Someone else's journal looks the same as a missing one.
    if journal is None or journal.author_id != owner.id:
        raise not_found("Journal")
    return journal


# ---------- mutations ----------
async def create_draft(session: AsyncSession, author: User) -> Journal:
    journal = Journal(
        author_id=author.id,
        slug=new_slug("untitled"),
        visibility=author.default_visibility,
        share_token=new_share_token(),
    )
    session.add(journal)
    await session.flush()
    return journal


async def _set_tags(session: AsyncSession, journal: Journal, names: list[str]) -> None:
    current = {t.name for t in journal.tags}
    wanted = set(names)
    if current == wanted:
        return
    if wanted:
        await session.execute(
            insert(Tag).values([{"name": n} for n in wanted]).on_conflict_do_nothing()
        )
    rows = await session.execute(select(Tag.name, Tag.id).where(Tag.name.in_(wanted | current)))
    tag_ids = {name: tag_id for name, tag_id in rows}
    removed = [tag_ids[n] for n in current - wanted if n in tag_ids]
    added = [tag_ids[n] for n in wanted - current]
    if removed:
        await session.execute(
            delete(journal_tags).where(
                journal_tags.c.journal_id == journal.id, journal_tags.c.tag_id.in_(removed)
            )
        )
        await session.execute(
            update(Tag).where(Tag.id.in_(removed)).values(journal_count=Tag.journal_count - 1)
        )
    if added:
        await session.execute(
            insert(journal_tags).values([{"journal_id": journal.id, "tag_id": t} for t in added])
        )
        await session.execute(
            update(Tag).where(Tag.id.in_(added)).values(journal_count=Tag.journal_count + 1)
        )
    await session.refresh(journal, attribute_names=["tags"])


async def update_journal(session: AsyncSession, journal: Journal, data: JournalUpdateIn) -> Journal:
    if data.version != journal.version:
        log.warning(
            "journal autosave conflict",
            journal_id=str(journal.id),
            client_version=data.version,
            server_version=journal.version,
        )
        raise conflict("This journal was changed elsewhere. Reload to get the latest version.")
    fields = data.model_fields_set

    if "title" in fields and data.title is not None:
        journal.title = " ".join(data.title.split())
        # The slug follows the title until the journal is first published.
        if journal.published_at is None:
            journal.slug = new_slug(journal.title or "untitled", journal.slug[-SLUG_SUFFIX_LEN:])
    if "subtitle" in fields:
        journal.subtitle = (data.subtitle or "").strip() or None
    if "content_json" in fields and data.content_json is not None:
        with tracer.start_as_current_span("journal.render") as span:
            try:
                rendered = render_document(data.content_json)
            except ContentError as exc:
                # The reason is safe to log (node/mark names), the content is not.
                log.warning("journal content rejected", journal_id=str(journal.id))
                span.set_attribute("journal.render.rejected", True)
                raise ProblemError(
                    422,
                    "Validation Error",
                    str(exc),
                    errors=[{"field": "content_json", "message": str(exc)}],
                ) from exc
            span.set_attributes(
                {
                    "journal.word_count": rendered.word_count,
                    "journal.reading_minutes": rendered.reading_minutes,
                }
            )
        journal.content_json = data.content_json
        journal.content_html = rendered.html
        journal.content_text = rendered.text
        journal.excerpt = rendered.excerpt
        journal.word_count = rendered.word_count
        journal.reading_minutes = rendered.reading_minutes
    if "visibility" in fields and data.visibility is not None:
        journal.visibility = data.visibility
    if data.clear_location:
        journal.place_name = journal.country_code = None
        journal.lat = journal.lng = None
    elif "location" in fields and data.location is not None:
        journal.place_name = data.location.place_name
        journal.country_code = data.location.country_code
        journal.lat = data.location.lat
        journal.lng = data.location.lng
    if "travel_start" in fields:
        journal.travel_start = data.travel_start
    if "travel_end" in fields:
        journal.travel_end = data.travel_end
    if journal.travel_start and journal.travel_end and journal.travel_end < journal.travel_start:
        raise bad_request("Travel end date must be after the start date")
    if "tags" in fields and data.tags is not None:
        await _set_tags(session, journal, data.tags)

    journal.version += 1
    await session.flush()
    return journal


async def publish(session: AsyncSession, journal: Journal, author: User) -> Journal:
    errors = []
    if not journal.title.strip():
        errors.append({"field": "title", "message": "Add a title before publishing"})
    if journal.word_count == 0:
        errors.append({"field": "content_json", "message": "Write something before publishing"})
    if errors:
        log.warning(
            "journal publish rejected",
            journal_id=str(journal.id),
            missing=",".join(e["field"] for e in errors),
        )
        raise ProblemError(422, "Validation Error", "This journal isn't ready yet", errors=errors)
    if journal.status != JournalStatus.published:
        journal.status = JournalStatus.published
        journal.published_at = journal.published_at or datetime.now(UTC)
        journal.version += 1
        await session.execute(
            update(User).where(User.id == author.id).values(journal_count=User.journal_count + 1)
        )
    await session.flush()
    return journal


async def unpublish(session: AsyncSession, journal: Journal, author: User) -> Journal:
    if journal.status == JournalStatus.published:
        journal.status = JournalStatus.draft
        journal.version += 1
        await session.execute(
            update(User).where(User.id == author.id).values(journal_count=User.journal_count - 1)
        )
    await session.flush()
    return journal


async def soft_delete(session: AsyncSession, journal: Journal, author: User) -> None:
    if journal.status == JournalStatus.published:
        await session.execute(
            update(User).where(User.id == author.id).values(journal_count=User.journal_count - 1)
        )
    journal.deleted_at = datetime.now(UTC)
    await session.flush()
