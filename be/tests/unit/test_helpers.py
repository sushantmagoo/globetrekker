import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.schemas import CommentIn, JournalUpdateIn, LocationIn, SignupIn
from app.services.journals import (
    SLUG_SUFFIX_LEN,
    decode_cursor,
    encode_cursor,
    new_slug,
    slugify,
)

# ---------- slugs ----------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Three Days in Kyoto", "three-days-in-kyoto"),
        ("  Café — São Paulo!  ", "cafe-sao-paulo"),
        ("🌋🌋", "untitled"),
        ("", "untitled"),
        ("a" * 300, "a" * 120),
    ],
)
def test_slugify(title: str, expected: str) -> None:
    assert slugify(title) == expected


def test_new_slug_keeps_a_given_suffix() -> None:
    slug = new_slug("Kyoto")
    assert slug.startswith("kyoto-") and len(slug) == len("kyoto-") + SLUG_SUFFIX_LEN
    assert new_slug("Osaka", slug[-SLUG_SUFFIX_LEN:]).endswith(slug[-SLUG_SUFFIX_LEN:])


# ---------- cursors ----------


def test_cursor_round_trip() -> None:
    ts, jid = datetime(2026, 4, 1, 12, 30, tzinfo=UTC), uuid.uuid4()
    assert decode_cursor(encode_cursor(ts, jid)) == (ts, jid)


@pytest.mark.parametrize("cursor", ["garbage", "eyJub3QiOiJhIGxpc3QifQ", ""])
def test_bad_cursor_is_a_400(cursor: str) -> None:
    with pytest.raises(ProblemError) as exc:
        decode_cursor(cursor)
    assert exc.value.status == 400


# ---------- security ----------


def test_password_hashing() -> None:
    h = hash_password("correct-horse-battery")
    assert h.startswith("$argon2id$")
    assert verify_password("correct-horse-battery", h)
    assert not verify_password("wrong-password", h)


def test_access_token_round_trip() -> None:
    uid = uuid.uuid4()
    payload = decode_access_token(create_access_token(uid, "member"))
    assert payload["sub"] == str(uid) and payload["role"] == "member"


def test_expired_and_foreign_tokens_are_rejected() -> None:
    secret = get_settings().jwt_secret
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": "x",
            "typ": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired)
    wrong_type = jwt.encode(
        {"sub": "x", "typ": "refresh", "iat": now, "exp": now + timedelta(minutes=5)},
        secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(wrong_type)
    forged = jwt.encode(
        {"sub": "x", "typ": "access", "iat": now, "exp": now + timedelta(minutes=5)},
        "some-other-secret-that-is-long-enough",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_opaque_tokens_store_only_a_hash() -> None:
    raw, digest = generate_token()
    assert digest == hash_token(raw) and raw not in digest and len(digest) == 64


# ---------- request validation ----------


def test_signup_normalises_username_and_rejects_bad_input() -> None:
    ok = SignupIn(
        email="a@example.com",
        password="long-enough-pass",
        username=" Ana_1 ",
        display_name="  Ana   B ",
    )
    assert ok.username == "ana_1" and ok.display_name == "Ana B"
    for bad in [
        {"username": "a"},
        {"username": "has space"},
        {"password": "short"},
        {"password": "password123"},
    ]:
        with pytest.raises(ValidationError):
            SignupIn(
                **{
                    "email": "a@example.com",
                    "password": "long-enough-pass",
                    "username": "ana",
                    "display_name": "Ana",
                    **bad,
                }
            )


def test_tags_are_normalised_and_deduplicated() -> None:
    data = JournalUpdateIn(version=1, tags=["Street Food", "street-food", " #Hiking ", ""])
    assert data.tags == ["street-food", "hiking"]
    with pytest.raises(ValidationError):
        JournalUpdateIn(version=1, tags=[f"t{i}" for i in range(11)])


def test_travel_dates_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        JournalUpdateIn(version=1, travel_start="2026-04-05", travel_end="2026-04-01")


def test_location_validation() -> None:
    assert (
        LocationIn(place_name="Cusco", country_code="pe", lat=-13.5, lng=-71.9).country_code == "PE"
    )
    with pytest.raises(ValidationError):
        LocationIn(place_name="Nowhere", lat=91, lng=0)
    with pytest.raises(ValidationError):
        LocationIn(place_name="Nowhere", country_code="PER", lat=0, lng=0)


def test_comments_are_trimmed_and_not_blank() -> None:
    assert CommentIn(body="  hi  ").body == "hi"
    with pytest.raises(ValidationError):
        CommentIn(body="   ")
