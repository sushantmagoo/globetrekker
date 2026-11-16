from httpx import AsyncClient

from tests.conftest import PASSWORD, UserFactory, new_client

SIGNUP = {
    "email": "ana@example.com",
    "password": PASSWORD,
    "username": "ana_travels",
    "display_name": "Ana",
}


async def test_signup_logs_in(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/signup", json=SIGNUP)
    assert r.status_code == 201
    assert "gt_refresh" in r.cookies
    token = r.json()["access_token"]

    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "ana_travels"
    assert "email_verified" not in me.json()


async def test_signup_rejects_duplicates_and_weak_passwords(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/signup", json=SIGNUP)).status_code == 201
    r = await client.post(
        "/api/v1/auth/signup", json={**SIGNUP, "email": "ANA@example.com", "username": "other"}
    )
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["errors"][0]["field"] == "email"

    r = await client.post(
        "/api/v1/auth/signup",
        json={**SIGNUP, "email": "b@example.com", "username": "bee", "password": "password123"},
    )
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "password"


async def test_auth_endpoints_require_xhr_header() -> None:
    async with new_client() as c:
        del c.headers["X-Requested-With"]
        r = await c.post("/api/v1/auth/signup", json=SIGNUP)
        assert r.status_code == 403


async def test_login_wrong_password_and_lockout(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    bad = {"email": SIGNUP["email"], "password": "nope-nope-nope"}
    for _ in range(9):
        assert (await client.post("/api/v1/auth/login", json=bad)).status_code == 401
    # 10th failure locks the account; even the right password is refused for a while.
    assert (await client.post("/api/v1/auth/login", json=bad)).status_code == 401
    good = {"email": SIGNUP["email"], "password": PASSWORD}
    assert (await client.post("/api/v1/auth/login", json=good)).status_code == 429


async def test_login_unknown_email_gives_same_error(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": PASSWORD}
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password"


async def test_refresh_rotates_and_detects_reuse(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    first = client.cookies.get("gt_refresh")

    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    second = client.cookies.get("gt_refresh")
    assert second and second != first

    # Replaying the old token within the grace window is tolerated (concurrent tabs) ...
    async with new_client() as other:
        other.cookies.set("gt_refresh", first, path="/api/v1/auth")
        assert (await other.post("/api/v1/auth/refresh")).status_code == 200

    # ... but a token that was never issued is not.
    async with new_client() as other:
        other.cookies.set("gt_refresh", "made-up-token", path="/api/v1/auth")
        assert (await other.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_revokes_session(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    token = client.cookies.get("gt_refresh")
    assert (await client.post("/api/v1/auth/logout")).status_code == 204

    async with new_client() as other:
        other.cookies.set("gt_refresh", token, path="/api/v1/auth")
        assert (await other.post("/api/v1/auth/refresh")).status_code == 401


async def test_invalid_bearer_token(client: AsyncClient) -> None:
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer nonsense"})
    assert r.status_code == 401


async def test_update_profile_and_password(make_user: UserFactory) -> None:
    c = await make_user("lena")
    r = await c.patch(
        "/api/v1/me",
        json={"bio": "Slow travel.", "home_country": "de", "default_visibility": "followers"},
    )
    assert r.status_code == 200
    assert r.json()["home_country"] == "DE"
    assert r.json()["default_visibility"] == "followers"

    r = await c.patch(
        "/api/v1/me/password",
        json={"current_password": "wrong-password", "new_password": "another-good-pass"},
    )
    assert r.status_code == 400
    r = await c.patch(
        "/api/v1/me/password",
        json={"current_password": PASSWORD, "new_password": "another-good-pass"},
    )
    assert r.status_code == 204


async def test_delete_account_hides_profile(make_user: UserFactory, client: AsyncClient) -> None:
    c = await make_user("gone")
    assert (await client.get("/api/v1/users/gone")).status_code == 200
    assert (await c.delete("/api/v1/me")).status_code == 204
    assert (await client.get("/api/v1/users/gone")).status_code == 404
    assert (await c.get("/api/v1/me")).status_code == 401
