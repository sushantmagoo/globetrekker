import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ProblemError, bad_request, forbidden, not_found
from app.models import (
    Bookmark,
    Comment,
    Follow,
    Journal,
    Like,
    Notification,
    NotificationType,
    User,
)
from app.schemas import CommentIn, CommentOut, UserSummary

COMMENT_EDIT_WINDOW = timedelta(minutes=15)
LIKE_NOTIFICATION_COALESCE = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(UTC)


async def notify(
    session: AsyncSession,
    *,
    recipient_id: uuid.UUID,
    actor: User,
    type_: NotificationType,
    journal_id: uuid.UUID | None = None,
    comment_id: uuid.UUID | None = None,
) -> None:
    if recipient_id == actor.id:
        return
    if type_ == NotificationType.like:
        recent = await session.scalar(
            select(
                exists().where(
                    Notification.recipient_id == recipient_id,
                    Notification.actor_id == actor.id,
                    Notification.type == NotificationType.like,
                    Notification.journal_id == journal_id,
                    Notification.created_at > _now() - LIKE_NOTIFICATION_COALESCE,
                )
            )
        )
        if recent:
            return
    session.add(
        Notification(
            recipient_id=recipient_id,
            actor_id=actor.id,
            type=type_,
            journal_id=journal_id,
            comment_id=comment_id,
        )
    )


# ---------- follows ----------
async def follow(session: AsyncSession, follower: User, followee: User) -> None:
    if follower.id == followee.id:
        raise bad_request("You can't follow yourself")
    inserted = await session.scalar(
        insert(Follow)
        .values(follower_id=follower.id, followee_id=followee.id)
        .on_conflict_do_nothing()
        .returning(Follow.follower_id)
    )
    if inserted is None:
        return
    await session.execute(
        update(User).where(User.id == follower.id).values(following_count=User.following_count + 1)
    )
    await session.execute(
        update(User).where(User.id == followee.id).values(follower_count=User.follower_count + 1)
    )
    await notify(session, recipient_id=followee.id, actor=follower, type_=NotificationType.follow)


async def unfollow(session: AsyncSession, follower: User, followee: User) -> None:
    deleted = await session.scalar(
        delete(Follow)
        .where(Follow.follower_id == follower.id, Follow.followee_id == followee.id)
        .returning(Follow.follower_id)
    )
    if deleted is None:
        return
    await session.execute(
        update(User).where(User.id == follower.id).values(following_count=User.following_count - 1)
    )
    await session.execute(
        update(User).where(User.id == followee.id).values(follower_count=User.follower_count - 1)
    )


# ---------- likes and bookmarks ----------
async def like(session: AsyncSession, user: User, journal: Journal) -> None:
    inserted = await session.scalar(
        insert(Like)
        .values(user_id=user.id, journal_id=journal.id)
        .on_conflict_do_nothing()
        .returning(Like.user_id)
    )
    if inserted is None:
        return
    await session.execute(
        update(Journal).where(Journal.id == journal.id).values(like_count=Journal.like_count + 1)
    )
    await notify(
        session,
        recipient_id=journal.author_id,
        actor=user,
        type_=NotificationType.like,
        journal_id=journal.id,
    )


async def unlike(session: AsyncSession, user: User, journal: Journal) -> None:
    deleted = await session.scalar(
        delete(Like)
        .where(Like.user_id == user.id, Like.journal_id == journal.id)
        .returning(Like.user_id)
    )
    if deleted is not None:
        await session.execute(
            update(Journal)
            .where(Journal.id == journal.id)
            .values(like_count=Journal.like_count - 1)
        )


async def bookmark(session: AsyncSession, user: User, journal: Journal) -> None:
    inserted = await session.scalar(
        insert(Bookmark)
        .values(user_id=user.id, journal_id=journal.id)
        .on_conflict_do_nothing()
        .returning(Bookmark.user_id)
    )
    if inserted is not None:
        await session.execute(
            update(Journal)
            .where(Journal.id == journal.id)
            .values(bookmark_count=Journal.bookmark_count + 1)
        )


async def unbookmark(session: AsyncSession, user: User, journal: Journal) -> None:
    deleted = await session.scalar(
        delete(Bookmark)
        .where(Bookmark.user_id == user.id, Bookmark.journal_id == journal.id)
        .returning(Bookmark.user_id)
    )
    if deleted is not None:
        await session.execute(
            update(Journal)
            .where(Journal.id == journal.id)
            .values(bookmark_count=Journal.bookmark_count - 1)
        )


# ---------- comments ----------
def _comment_out(c: Comment, viewer: User | None, journal_author_id: uuid.UUID) -> CommentOut:
    is_author = viewer is not None and viewer.id == c.author_id
    return CommentOut(
        id=c.id,
        journal_id=c.journal_id,
        parent_id=c.parent_id,
        author=UserSummary.model_validate(c.author),
        body=c.body,
        created_at=c.created_at,
        edited_at=c.edited_at,
        can_edit=is_author and _now() - c.created_at <= COMMENT_EDIT_WINDOW,
        can_delete=is_author or (viewer is not None and viewer.id == journal_author_id),
    )


async def list_comments(
    session: AsyncSession, journal: Journal, viewer: User | None
) -> list[CommentOut]:
    rows = (
        await session.scalars(
            select(Comment)
            .options(selectinload(Comment.author))
            .where(Comment.journal_id == journal.id, Comment.deleted_at.is_(None))
            .order_by(Comment.created_at)
            .limit(500)
        )
    ).all()
    top: dict[uuid.UUID, CommentOut] = {}
    replies: list[Comment] = []
    for c in rows:
        if c.parent_id is None:
            top[c.id] = _comment_out(c, viewer, journal.author_id)
        else:
            replies.append(c)
    for r in replies:
        parent = top.get(r.parent_id)  # type: ignore[arg-type]
        if parent is not None:
            parent.replies.append(_comment_out(r, viewer, journal.author_id))
    return list(top.values())


async def add_comment(
    session: AsyncSession, journal: Journal, author: User, data: CommentIn
) -> CommentOut:
    parent: Comment | None = None
    if data.parent_id is not None:
        parent = await session.get(Comment, data.parent_id)
        if parent is None or parent.journal_id != journal.id or parent.deleted_at is not None:
            raise not_found("Comment")
        if parent.parent_id is not None:
            parent = await session.get(Comment, parent.parent_id)  # only one level of replies
            assert parent is not None
    comment = Comment(
        journal_id=journal.id,
        author_id=author.id,
        parent_id=parent.id if parent else None,
        body=data.body,
    )
    session.add(comment)
    await session.flush()
    await session.execute(
        update(Journal)
        .where(Journal.id == journal.id)
        .values(comment_count=Journal.comment_count + 1)
    )
    await notify(
        session,
        recipient_id=journal.author_id,
        actor=author,
        type_=NotificationType.comment,
        journal_id=journal.id,
        comment_id=comment.id,
    )
    if parent is not None and parent.author_id != journal.author_id:
        await notify(
            session,
            recipient_id=parent.author_id,
            actor=author,
            type_=NotificationType.reply,
            journal_id=journal.id,
            comment_id=comment.id,
        )
    await session.refresh(comment, attribute_names=["author"])
    return _comment_out(comment, author, journal.author_id)


async def get_comment(session: AsyncSession, comment_id: uuid.UUID) -> Comment:
    comment = await session.scalar(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.id == comment_id, Comment.deleted_at.is_(None))
    )
    if comment is None:
        raise not_found("Comment")
    return comment


async def edit_comment(
    session: AsyncSession, comment: Comment, journal: Journal, user: User, body: str
) -> CommentOut:
    if comment.author_id != user.id:
        raise forbidden()
    if _now() - comment.created_at > COMMENT_EDIT_WINDOW:
        raise ProblemError(403, "Forbidden", "Comments can only be edited for 15 minutes")
    body = body.strip()
    if not body:
        raise bad_request("Comment can't be empty")
    comment.body = body
    comment.edited_at = _now()
    await session.flush()
    return _comment_out(comment, user, journal.author_id)


async def delete_comment(
    session: AsyncSession, comment: Comment, journal: Journal, user: User
) -> None:
    if user.id not in (comment.author_id, journal.author_id):
        raise forbidden()
    now = _now()
    # Deleting a top-level comment removes its replies too.
    ids = [comment.id]
    if comment.parent_id is None:
        ids += list(
            await session.scalars(
                select(Comment.id).where(
                    Comment.parent_id == comment.id, Comment.deleted_at.is_(None)
                )
            )
        )
    await session.execute(update(Comment).where(Comment.id.in_(ids)).values(deleted_at=now))
    await session.execute(
        update(Journal)
        .where(Journal.id == journal.id)
        .values(comment_count=Journal.comment_count - len(ids))
    )
