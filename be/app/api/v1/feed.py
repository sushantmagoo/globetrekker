from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import Float, and_, cast, exists, func, or_, select

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.core.errors import bad_request
from app.models import Follow, Journal, JournalStatus, Tag, Visibility, journal_tags
from app.schemas import JournalCard, Page
from app.services import journals as journal_service
from app.services.visibility import author_active

router = APIRouter(prefix="/feed", tags=["feed"])

Limit = Annotated[int, Query(ge=1, le=50)]
TRENDING_WINDOW = timedelta(days=14)


def _published() -> list[object]:
    return [
        Journal.status == JournalStatus.published,
        Journal.deleted_at.is_(None),
        author_active(),
    ]


@router.get("/home")
async def home_feed(
    user: CurrentUser, session: SessionDep, cursor: str | None = None, limit: Limit = 20
) -> Page[JournalCard]:
    follows_author = exists().where(
        Follow.follower_id == user.id, Follow.followee_id == Journal.author_id
    )
    stmt = select(Journal).where(
        *_published(),  # type: ignore[arg-type]
        or_(
            Journal.author_id == user.id,
            and_(follows_author, Journal.visibility.in_([Visibility.public, Visibility.followers])),
        ),
    )
    rows, next_cursor = await journal_service.paginate_published(session, stmt, cursor, limit)
    return Page(items=await journal_service.to_cards(session, rows, user), next_cursor=next_cursor)


@router.get("/explore")
async def explore_feed(
    viewer: OptionalUser,
    session: SessionDep,
    sort: Literal["recent", "trending"] = "recent",
    tag: Annotated[str | None, Query(max_length=40)] = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    cursor: str | None = None,
    limit: Limit = 20,
) -> Page[JournalCard]:
    stmt = select(Journal).where(
        *_published(),  # type: ignore[arg-type]
        Journal.visibility == Visibility.public,
    )
    if tag:
        stmt = stmt.where(
            exists().where(
                journal_tags.c.journal_id == Journal.id,
                journal_tags.c.tag_id == Tag.id,
                Tag.name == tag.lower(),
            )
        )
    if country:
        stmt = stmt.where(Journal.country_code == country.upper())

    if sort == "recent":
        rows, next_cursor = await journal_service.paginate_published(session, stmt, cursor, limit)
        return Page(
            items=await journal_service.to_cards(session, rows, viewer), next_cursor=next_cursor
        )

    # Trending: score decays with age; offset pagination is fine for a bounded window.
    try:
        offset = int(cursor) if cursor else 0
    except ValueError:
        raise bad_request("Invalid cursor") from None
    age_hours = func.extract("epoch", func.now() - Journal.published_at) / 3600
    score = cast(Journal.like_count + 2 * Journal.comment_count + 1, Float) / func.power(
        age_hours + 2, 1.5
    )
    stmt = (
        journal_service.with_card_relations(stmt)
        .where(Journal.published_at > func.now() - TRENDING_WINDOW)
        .order_by(score.desc(), Journal.id.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    trending = (await session.scalars(stmt)).all()
    has_more = len(trending) > limit
    return Page(
        items=await journal_service.to_cards(session, trending[:limit], viewer),
        next_cursor=str(offset + limit) if has_more else None,
    )
