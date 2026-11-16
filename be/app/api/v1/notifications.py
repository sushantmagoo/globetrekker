from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.core.errors import bad_request
from app.models import Journal, Notification
from app.schemas import MarkReadIn, NotificationOut, Page, UnreadCountOut, UserSummary

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    user: CurrentUser,
    session: SessionDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[NotificationOut]:
    stmt = (
        select(Notification, Journal.slug, Journal.title)
        .options(selectinload(Notification.actor))
        .outerjoin(Journal, Journal.id == Notification.journal_id)
        .where(Notification.recipient_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        try:
            stmt = stmt.where(Notification.created_at < datetime.fromisoformat(cursor))
        except ValueError:
            raise bad_request("Invalid cursor") from None
    rows = (await session.execute(stmt)).all()
    items = [
        NotificationOut(
            id=n.id,
            type=n.type,
            actor=UserSummary.model_validate(n.actor),
            journal_slug=slug,
            journal_title=title,
            comment_id=n.comment_id,
            read_at=n.read_at,
            created_at=n.created_at,
        )
        for n, slug, title in rows[:limit]
    ]
    next_cursor = items[-1].created_at.isoformat() if len(rows) > limit else None
    return Page(items=items, next_cursor=next_cursor)


@router.get("/unread-count")
async def unread_count(user: CurrentUser, session: SessionDep) -> UnreadCountOut:
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
    )
    return UnreadCountOut(count=count or 0)


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(data: MarkReadIn, user: CurrentUser, session: SessionDep) -> None:
    stmt = update(Notification).where(
        Notification.recipient_id == user.id, Notification.read_at.is_(None)
    )
    if data.ids:
        stmt = stmt.where(Notification.id.in_(data.ids))
    await session.execute(stmt.values(read_at=datetime.now(UTC)))
    await session.commit()
