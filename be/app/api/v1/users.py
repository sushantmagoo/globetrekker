import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.api.v1.auth import REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.core.errors import bad_request, not_found
from app.core.security import hash_password, verify_password
from app.models import Bookmark, Follow, Journal, JournalStatus, User, UserStatus
from app.schemas import (
    ChangePasswordIn,
    JournalCard,
    MeOut,
    MeUpdateIn,
    Page,
    ProfileOut,
    UserSummary,
)
from app.services import auth as auth_service
from app.services import journals as journal_service
from app.services import social
from app.services.visibility import is_following, listed_for_viewer

router = APIRouter(tags=["users"])

Limit = Annotated[int, Query(ge=1, le=50)]


def _me_out(user: User) -> MeOut:
    return MeOut.model_validate(
        {
            **ProfileOut.model_validate(user).model_dump(),
            "email": user.email,
            "default_visibility": user.default_visibility,
            "role": user.role.value,
            "is_me": True,
        }
    )


async def _get_user(session: SessionDep, username: str) -> User:
    user = await session.scalar(
        select(User).where(
            User.username == username.lower(),
            User.deleted_at.is_(None),
            User.status == UserStatus.active,
        )
    )
    if user is None:
        raise not_found("User")
    return user


# ---------- me ----------
@router.get("/me")
async def get_me(user: CurrentUser) -> MeOut:
    return _me_out(user)


@router.patch("/me")
async def update_me(data: MeUpdateIn, user: CurrentUser, session: SessionDep) -> MeOut:
    fields = data.model_fields_set
    if "display_name" in fields and data.display_name:
        user.display_name = " ".join(data.display_name.split())
    if "bio" in fields:
        user.bio = (data.bio or "").strip() or None
    if "home_country" in fields:
        user.home_country = data.home_country
    if "website_url" in fields:
        user.website_url = str(data.website_url) if data.website_url else None
    if "default_visibility" in fields and data.default_visibility:
        user.default_visibility = data.default_visibility
    await session.commit()
    return _me_out(user)


@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(data: ChangePasswordIn, user: CurrentUser, session: SessionDep) -> None:
    if not verify_password(data.current_password, user.password_hash):
        raise bad_request(
            "Current password is incorrect",
            errors=[{"field": "current_password", "message": "Incorrect password"}],
        )
    user.password_hash = hash_password(data.new_password)
    await session.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(user: CurrentUser, session: SessionDep, response: Response) -> None:
    user.deleted_at = datetime.now(UTC)
    user.status = UserStatus.deleted
    await auth_service.revoke_all_sessions(session, user.id)
    await session.commit()
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


@router.get("/me/drafts")
async def my_drafts(user: CurrentUser, session: SessionDep, limit: Limit = 50) -> list[JournalCard]:
    rows = (
        await session.scalars(
            journal_service.with_card_relations(select(Journal))
            .where(
                Journal.author_id == user.id,
                Journal.status == JournalStatus.draft,
                Journal.deleted_at.is_(None),
            )
            .order_by(Journal.updated_at.desc())
            .limit(limit)
        )
    ).all()
    return await journal_service.to_cards(session, rows, user)


@router.get("/me/bookmarks")
async def my_bookmarks(
    user: CurrentUser, session: SessionDep, limit: Limit = 50
) -> list[JournalCard]:
    rows = (
        await session.scalars(
            journal_service.with_card_relations(select(Journal))
            .join(Bookmark, Bookmark.journal_id == Journal.id)
            .where(Bookmark.user_id == user.id, listed_for_viewer(user))
            .order_by(Bookmark.created_at.desc())
            .limit(limit)
        )
    ).all()
    return await journal_service.to_cards(session, rows, user)


# ---------- profiles ----------
@router.get("/users/{username}")
async def get_profile(username: str, viewer: OptionalUser, session: SessionDep) -> ProfileOut:
    user = await _get_user(session, username)
    out = ProfileOut.model_validate(user)
    out.is_me = viewer is not None and viewer.id == user.id
    out.is_following = await is_following(session, viewer, user.id)
    return out


@router.get("/users/{username}/journals")
async def profile_journals(
    username: str,
    viewer: OptionalUser,
    session: SessionDep,
    cursor: str | None = None,
    limit: Limit = 20,
) -> Page[JournalCard]:
    user = await _get_user(session, username)
    stmt = select(Journal).where(Journal.author_id == user.id, listed_for_viewer(viewer))
    rows, next_cursor = await journal_service.paginate_published(session, stmt, cursor, limit)
    return Page(
        items=await journal_service.to_cards(session, rows, viewer), next_cursor=next_cursor
    )


async def _follow_list(
    session: SessionDep, user_id: uuid.UUID, *, followers: bool, cursor: str | None, limit: int
) -> Page[UserSummary]:
    other = Follow.follower_id if followers else Follow.followee_id
    mine = Follow.followee_id if followers else Follow.follower_id
    stmt = (
        select(User, Follow.created_at)
        .join(Follow, other == User.id)
        .where(mine == user_id, User.deleted_at.is_(None))
        .order_by(Follow.created_at.desc())
        .limit(limit + 1)
    )
    if cursor:
        try:
            stmt = stmt.where(Follow.created_at < datetime.fromisoformat(cursor))
        except ValueError:
            raise bad_request("Invalid cursor") from None
    rows = (await session.execute(stmt)).all()
    next_cursor = rows[limit - 1][1].isoformat() if len(rows) > limit else None
    return Page(
        items=[UserSummary.model_validate(u) for u, _ in rows[:limit]], next_cursor=next_cursor
    )


@router.get("/users/{username}/followers")
async def followers(
    username: str, session: SessionDep, cursor: str | None = None, limit: Limit = 20
) -> Page[UserSummary]:
    user = await _get_user(session, username)
    return await _follow_list(session, user.id, followers=True, cursor=cursor, limit=limit)


@router.get("/users/{username}/following")
async def following(
    username: str, session: SessionDep, cursor: str | None = None, limit: Limit = 20
) -> Page[UserSummary]:
    user = await _get_user(session, username)
    return await _follow_list(session, user.id, followers=False, cursor=cursor, limit=limit)


@router.put("/users/{username}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def follow_user(username: str, user: CurrentUser, session: SessionDep) -> None:
    target = await _get_user(session, username)
    await social.follow(session, user, target)
    await session.commit()


@router.delete("/users/{username}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(username: str, user: CurrentUser, session: SessionDep) -> None:
    target = await _get_user(session, username)
    await social.unfollow(session, user, target)
    await session.commit()
