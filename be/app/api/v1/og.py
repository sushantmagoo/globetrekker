"""Open Graph HTML for link-preview crawlers (spec §4.7). Caddy rewrites crawler
requests for /j/* and /u/* to these endpoints."""

from html import escape
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.models import Journal, User, UserStatus, Visibility
from app.services.visibility import can_view

router = APIRouter(prefix="/og", tags=["og"], include_in_schema=False)

SITE = "Globetrekker"
DEFAULT_DESCRIPTION = "Travel journals from people exploring the world."


def _page(
    *, title: str, description: str, url: str, kind: str = "website", noindex: bool = False
) -> HTMLResponse:
    base = get_settings().public_app_url
    image = f"{base}/og-default.png"
    t, d, u = escape(title), escape(description), escape(url)
    robots = '<meta name="robots" content="noindex">' if noindex else ""
    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{t}</title>
<meta name="description" content="{d}">
{robots}
<link rel="canonical" href="{u}">
<meta property="og:site_name" content="{SITE}">
<meta property="og:type" content="{kind}">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{u}">
<meta property="og:image" content="{escape(image)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{escape(image)}">
</head><body><h1>{t}</h1><p>{d}</p><a href="{u}">Read on {SITE}</a></body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=300"})


@router.get("/j/{slug}")
async def journal_og(
    slug: str, session: SessionDep, t: Annotated[str | None, Query(max_length=64)] = None
) -> HTMLResponse:
    base = get_settings().public_app_url
    journal = await session.scalar(select(Journal).where(Journal.slug == slug))
    url = f"{base}/j/{slug}"
    if journal is None or not await can_view(session, journal, None, t):
        return _page(title=SITE, description=DEFAULT_DESCRIPTION, url=base, noindex=True)
    author = await session.get(User, journal.author_id)
    byline = f" by {author.display_name}" if author else ""
    place = f" · {journal.place_name}" if journal.place_name else ""
    return _page(
        title=f"{journal.title}{byline}",
        description=(journal.subtitle or journal.excerpt or DEFAULT_DESCRIPTION) + place,
        url=url,
        kind="article",
        noindex=journal.visibility != Visibility.public,
    )


@router.get("/u/{username}")
async def profile_og(username: str, session: SessionDep) -> HTMLResponse:
    base = get_settings().public_app_url
    user = await session.scalar(
        select(User).where(
            User.username == username.lower(),
            User.deleted_at.is_(None),
            User.status == UserStatus.active,
        )
    )
    if user is None:
        return _page(title=SITE, description=DEFAULT_DESCRIPTION, url=base, noindex=True)
    return _page(
        title=f"{user.display_name} (@{user.username}) on {SITE}",
        description=user.bio or f"Travel journals by {user.display_name}.",
        url=f"{base}/u/{user.username}",
        kind="profile",
    )
