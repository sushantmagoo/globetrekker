import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from app.models.enums import JournalStatus, NotificationType, Visibility

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,30}$")
TAG_RE = re.compile(r"[^a-z0-9]+")


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](Schema):
    items: list[T]
    next_cursor: str | None = None


def _country(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    if not re.fullmatch(r"[A-Za-z]{2}", v):
        raise ValueError("Must be a 2-letter ISO country code")
    return v.upper()


CountryCode = Annotated[str | None, AfterValidator(_country)]


def _password(v: str) -> str:
    from app.core.security import COMMON_PASSWORDS

    if len(v) < 10:
        raise ValueError("Password must be at least 10 characters")
    if len(v) > 128:
        raise ValueError("Password must be at most 128 characters")
    if v.lower() in COMMON_PASSWORDS:
        raise ValueError("This password is too common")
    return v


Password = Annotated[str, AfterValidator(_password)]


# ---------- auth ----------
class SignupIn(BaseModel):
    email: EmailStr
    password: Password
    username: str = Field(min_length=3, max_length=30)
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip().lower()
        if not USERNAME_RE.fullmatch(v):
            raise ValueError("Use 3–30 lowercase letters, numbers or underscores")
        return v

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Display name is required")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


# ---------- users ----------
class UserSummary(Schema):
    id: uuid.UUID
    username: str
    display_name: str


class ProfileOut(UserSummary):
    bio: str | None
    home_country: str | None
    website_url: str | None
    follower_count: int
    following_count: int
    journal_count: int
    created_at: datetime
    is_following: bool = False
    is_me: bool = False


class MeOut(ProfileOut):
    email: str
    default_visibility: Visibility
    role: str


class MeUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    bio: str | None = Field(default=None, max_length=500)
    home_country: CountryCode = None
    website_url: HttpUrl | None = None
    default_visibility: Visibility | None = None


# ---------- journals ----------
class LocationIn(BaseModel):
    place_name: str = Field(min_length=1, max_length=200)
    country_code: CountryCode = None
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class JournalUpdateIn(BaseModel):
    version: int
    title: str | None = Field(default=None, max_length=200)
    subtitle: str | None = Field(default=None, max_length=300)
    content_json: dict[str, Any] | None = None
    visibility: Visibility | None = None
    location: LocationIn | None = None
    clear_location: bool = False
    travel_start: date | None = None
    travel_end: date | None = None
    tags: list[str] | None = Field(default=None, max_length=10)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        out: list[str] = []
        for raw in v:
            tag = TAG_RE.sub("-", raw.strip().lower()).strip("-")[:40]
            if tag and tag not in out:
                out.append(tag)
        return out

    @model_validator(mode="after")
    def _dates(self) -> "JournalUpdateIn":
        if self.travel_start and self.travel_end and self.travel_end < self.travel_start:
            raise ValueError("Travel end date must be after the start date")
        return self


class JournalCreatedOut(Schema):
    id: uuid.UUID
    slug: str
    version: int


class JournalCard(Schema):
    id: uuid.UUID
    slug: str
    title: str
    subtitle: str | None
    excerpt: str
    author: UserSummary
    status: JournalStatus
    visibility: Visibility
    place_name: str | None
    country_code: str | None
    lat: float | None
    lng: float | None
    travel_start: date | None
    travel_end: date | None
    reading_minutes: int
    like_count: int
    comment_count: int
    tags: list[str] = []
    published_at: datetime | None
    updated_at: datetime
    liked_by_me: bool = False
    bookmarked_by_me: bool = False


class JournalDetail(JournalCard):
    content_html: str
    word_count: int
    is_owner: bool = False
    share_token: str | None = None  # owner only


class JournalEditOut(JournalDetail):
    content_json: dict[str, Any]
    version: int


# ---------- comments ----------
class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parent_id: uuid.UUID | None = None

    @field_validator("body")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Comment can't be empty")
        return v


class CommentUpdateIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentOut(Schema):
    id: uuid.UUID
    journal_id: uuid.UUID
    parent_id: uuid.UUID | None
    author: UserSummary
    body: str
    created_at: datetime
    edited_at: datetime | None
    replies: list["CommentOut"] = []
    can_delete: bool = False
    can_edit: bool = False


# ---------- notifications ----------
class NotificationOut(Schema):
    id: uuid.UUID
    type: NotificationType
    actor: UserSummary
    journal_slug: str | None = None
    journal_title: str | None = None
    comment_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime


class UnreadCountOut(BaseModel):
    count: int


class MarkReadIn(BaseModel):
    ids: list[uuid.UUID] | None = None
