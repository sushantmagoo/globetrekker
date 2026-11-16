import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.api.v1.journals import ShareToken, load_published_visible
from app.core.errors import not_found
from app.models import Journal
from app.schemas import CommentIn, CommentOut, CommentUpdateIn
from app.services import social
from app.services.visibility import can_view

router = APIRouter(tags=["social"])


@router.put("/journals/{journal_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def like(
    journal_id: uuid.UUID, user: CurrentUser, session: SessionDep, t: ShareToken = None
) -> None:
    journal = await load_published_visible(session, journal_id, user, t)
    await social.like(session, user, journal)
    await session.commit()


@router.delete("/journals/{journal_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def unlike(journal_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    journal = await session.get(Journal, journal_id)
    if journal is None:
        raise not_found("Journal")
    await social.unlike(session, user, journal)
    await session.commit()


@router.put("/journals/{journal_id}/bookmark", status_code=status.HTTP_204_NO_CONTENT)
async def bookmark(
    journal_id: uuid.UUID, user: CurrentUser, session: SessionDep, t: ShareToken = None
) -> None:
    journal = await load_published_visible(session, journal_id, user, t)
    await social.bookmark(session, user, journal)
    await session.commit()


@router.delete("/journals/{journal_id}/bookmark", status_code=status.HTTP_204_NO_CONTENT)
async def unbookmark(journal_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    journal = await session.get(Journal, journal_id)
    if journal is None:
        raise not_found("Journal")
    await social.unbookmark(session, user, journal)
    await session.commit()


@router.get("/journals/{journal_id}/comments")
async def list_comments(
    journal_id: uuid.UUID, viewer: OptionalUser, session: SessionDep, t: ShareToken = None
) -> list[CommentOut]:
    journal = await load_published_visible(session, journal_id, viewer, t)
    return await social.list_comments(session, journal, viewer)


@router.post("/journals/{journal_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment(
    journal_id: uuid.UUID,
    data: CommentIn,
    user: CurrentUser,
    session: SessionDep,
    t: ShareToken = None,
) -> CommentOut:
    journal = await load_published_visible(session, journal_id, user, t)
    out = await social.add_comment(session, journal, user, data)
    await session.commit()
    return out


@router.patch("/comments/{comment_id}")
async def edit_comment(
    comment_id: uuid.UUID, data: CommentUpdateIn, user: CurrentUser, session: SessionDep
) -> CommentOut:
    comment = await social.get_comment(session, comment_id)
    journal = await session.get(Journal, comment.journal_id)
    if journal is None or not await can_view(session, journal, user):
        raise not_found("Comment")
    out = await social.edit_comment(session, comment, journal, user, data.body)
    await session.commit()
    return out


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(comment_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    comment = await social.get_comment(session, comment_id)
    journal = await session.get(Journal, comment.journal_id)
    if journal is None:
        raise not_found("Comment")
    await social.delete_comment(session, comment, journal, user)
    await session.commit()
