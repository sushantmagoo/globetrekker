import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.core.errors import not_found
from app.core.telemetry import JOURNEY, journals_published, set_span_attributes
from app.models import Journal, JournalStatus, User
from app.schemas import JournalCreatedOut, JournalDetail, JournalEditOut, JournalUpdateIn
from app.services import journals as journal_service
from app.services.visibility import can_view

router = APIRouter(prefix="/journals", tags=["journals"])

# Journey events carry `journey` so Grafana can show them next to the request logs.
log = structlog.get_logger(journey=JOURNEY)

ShareToken = Annotated[str | None, Query(alias="t", max_length=64)]


async def load_visible(
    session: SessionDep, journal_id: uuid.UUID, viewer: User | None, token: str | None
) -> Journal:
    """Load a journal by id that the viewer is allowed to read (404 otherwise)."""
    journal = await session.get(Journal, journal_id)
    if journal is None or not await can_view(session, journal, viewer, token):
        raise not_found("Journal")
    return journal


async def load_published_visible(
    session: SessionDep, journal_id: uuid.UUID, viewer: User | None, token: str | None
) -> Journal:
    journal = await load_visible(session, journal_id, viewer, token)
    if journal.status != JournalStatus.published:
        raise not_found("Journal")
    return journal


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_journal(user: CurrentUser, session: SessionDep) -> JournalCreatedOut:
    journal = await journal_service.create_draft(session, user)
    await session.commit()
    set_span_attributes(
        {"journal.id": str(journal.id), "journal.visibility": journal.visibility.value}
    )
    log.info("journal draft created", journal_id=str(journal.id))
    return JournalCreatedOut.model_validate(journal)


@router.get("/{slug}")
async def read_journal(
    slug: str, viewer: OptionalUser, session: SessionDep, response: Response, t: ShareToken = None
) -> JournalDetail:
    journal = await journal_service.get_by_slug(session, slug)
    set_span_attributes(
        {
            "journal.id": str(journal.id),
            "journal.visibility": journal.visibility.value,
            "journal.access": "share_link" if t else "direct",
            "viewer.signed_in": viewer is not None,
        }
    )
    if not await can_view(session, journal, viewer, t):
        raise not_found("Journal")
    if journal.visibility.value != "public" or journal.status != JournalStatus.published:
        response.headers["X-Robots-Tag"] = "noindex"
    response.headers["Cache-Control"] = "private, no-store"
    return await journal_service.to_detail(session, journal, viewer)


@router.get("/{journal_id}/edit")
async def get_for_edit(
    journal_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> JournalEditOut:
    journal = await journal_service.get_owned(session, journal_id, user)
    return journal_service.to_edit(journal)


@router.patch("/{journal_id}")
async def update_journal(
    journal_id: uuid.UUID, data: JournalUpdateIn, user: CurrentUser, session: SessionDep
) -> JournalEditOut:
    set_span_attributes({"journal.id": str(journal_id)})
    journal = await journal_service.get_owned(session, journal_id, user, lock=True)
    await journal_service.update_journal(session, journal, data)
    await session.commit()
    set_span_attributes(
        {"journal.version": journal.version, "journal.word_count": journal.word_count}
    )
    log.info(
        "journal autosaved",
        journal_id=str(journal.id),
        version=journal.version,
        word_count=journal.word_count,
    )
    return journal_service.to_edit(journal)


@router.post("/{journal_id}/publish")
async def publish_journal(
    journal_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> JournalEditOut:
    set_span_attributes({"journal.id": str(journal_id)})
    journal = await journal_service.get_owned(session, journal_id, user, lock=True)
    first_publish = journal.status != JournalStatus.published
    await journal_service.publish(session, journal, user)
    await session.commit()
    visibility = journal.visibility.value
    set_span_attributes(
        {"journal.visibility": visibility, "journal.word_count": journal.word_count}
    )
    if first_publish:
        journals_published.add(1, {"journal.visibility": visibility})
    log.info(
        "journal published",
        journal_id=str(journal.id),
        visibility=visibility,
        word_count=journal.word_count,
        first_publish=first_publish,
    )
    return journal_service.to_edit(journal)


@router.post("/{journal_id}/unpublish")
async def unpublish_journal(
    journal_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> JournalEditOut:
    journal = await journal_service.get_owned(session, journal_id, user, lock=True)
    await journal_service.unpublish(session, journal, user)
    await session.commit()
    return journal_service.to_edit(journal)


@router.post("/{journal_id}/share-token")
async def rotate_share_token(
    journal_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> JournalEditOut:
    journal = await journal_service.get_owned(session, journal_id, user, lock=True)
    journal.share_token = journal_service.new_share_token()
    await session.commit()
    return journal_service.to_edit(journal)


@router.delete("/{journal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journal(journal_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    journal = await journal_service.get_owned(session, journal_id, user, lock=True)
    await journal_service.soft_delete(session, journal, user)
    await session.commit()
