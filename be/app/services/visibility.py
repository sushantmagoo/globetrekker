"""Single source of truth for who can read a journal (spec §4.6)."""

import hmac

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Follow, Journal, JournalStatus, User, UserStatus, Visibility


async def is_following(session: AsyncSession, follower: User | None, followee_id: object) -> bool:
    if follower is None:
        return False
    return bool(
        await session.scalar(
            select(
                exists().where(Follow.follower_id == follower.id, Follow.followee_id == followee_id)
            )
        )
    )


async def can_view(
    session: AsyncSession, journal: Journal, viewer: User | None, share_token: str | None = None
) -> bool:
    if journal.deleted_at is not None:
        return False
    if viewer is not None and viewer.id == journal.author_id:
        return True
    author = await session.get(User, journal.author_id)
    if author is None or author.deleted_at is not None or author.status != UserStatus.active:
        return False
    if journal.status != JournalStatus.published:
        return False
    match journal.visibility:
        case Visibility.public:
            return True
        case Visibility.unlisted:
            return bool(share_token) and hmac.compare_digest(share_token or "", journal.share_token)
        case Visibility.followers:
            return await is_following(session, viewer, journal.author_id)
        case _:
            return False


def author_active() -> ColumnElement[bool]:
    return exists().where(
        User.id == Journal.author_id, User.deleted_at.is_(None), User.status == UserStatus.active
    )


def listed_for_viewer(viewer: User | None) -> ColumnElement[bool]:
    """SQL filter for journals that may appear in lists (profile tabs, feeds).
    Unlisted and private journals never appear except to their owner."""
    published = and_(
        Journal.status == JournalStatus.published, Journal.deleted_at.is_(None), author_active()
    )
    if viewer is None:
        return and_(published, Journal.visibility == Visibility.public)
    follows_author = exists().where(
        Follow.follower_id == viewer.id, Follow.followee_id == Journal.author_id
    )
    return or_(
        and_(
            Journal.author_id == viewer.id,
            Journal.deleted_at.is_(None),
            Journal.status == JournalStatus.published,
        ),
        and_(published, Journal.visibility == Visibility.public),
        and_(published, Journal.visibility == Visibility.followers, follows_author),
    )
