from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM


class UserRole(StrEnum):
    member = "member"
    admin = "admin"


class UserStatus(StrEnum):
    active = "active"
    suspended = "suspended"
    deleted = "deleted"


class JournalStatus(StrEnum):
    draft = "draft"
    published = "published"


class Visibility(StrEnum):
    public = "public"
    followers = "followers"
    unlisted = "unlisted"
    private = "private"


class NotificationType(StrEnum):
    follow = "follow"
    like = "like"
    comment = "comment"
    reply = "reply"


class ReportTarget(StrEnum):
    journal = "journal"
    comment = "comment"
    user = "user"


ALL_ENUMS: dict[str, type[StrEnum]] = {
    "user_role": UserRole,
    "user_status": UserStatus,
    "journal_status": JournalStatus,
    "visibility": Visibility,
    "notification_type": NotificationType,
    "report_target": ReportTarget,
}


def pg_enum(name: str) -> ENUM:
    """Postgres ENUM column type. Types are created explicitly in migrations
    (create_type=False) because several tables share the same type."""
    cls = ALL_ENUMS[name]
    return ENUM(
        cls,
        name=name,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )
