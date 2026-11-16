from httpx import AsyncClient

from tests.conftest import UserFactory, doc, published_journal


async def test_draft_lifecycle(make_user: UserFactory) -> None:
    c = await make_user("marco")
    created = (await c.post("/api/v1/journals")).json()
    assert created["slug"].startswith("untitled-")

    r = await c.patch(
        f"/api/v1/journals/{created['id']}",
        json={
            "version": created["version"],
            "title": "Three Days in Kyoto",
            "content_json": doc("Bamboo, temples and too much matcha."),
            "tags": ["Japan", " food ", "japan"],
            "location": {"place_name": "Kyoto", "country_code": "jp", "lat": 35.01, "lng": 135.77},
            "travel_start": "2026-04-01",
            "travel_end": "2026-04-03",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"].startswith("three-days-in-kyoto-")
    assert body["slug"][-6:] == created["slug"][-6:]
    assert body["tags"] == ["food", "japan"]
    assert body["country_code"] == "JP"
    assert body["content_html"] == "<p>Bamboo, temples and too much matcha.</p>"
    assert body["version"] == created["version"] + 1

    drafts = (await c.get("/api/v1/me/drafts")).json()
    assert [d["id"] for d in drafts] == [created["id"]]


async def test_stale_version_conflicts(make_user: UserFactory) -> None:
    c = await make_user("marco")
    created = (await c.post("/api/v1/journals")).json()
    url = f"/api/v1/journals/{created['id']}"
    assert (await c.patch(url, json={"version": 1, "title": "A"})).status_code == 200
    r = await c.patch(url, json={"version": 1, "title": "B"})
    assert r.status_code == 409


async def test_images_are_rejected(make_user: UserFactory) -> None:
    c = await make_user("marco")
    created = (await c.post("/api/v1/journals")).json()
    r = await c.patch(
        f"/api/v1/journals/{created['id']}",
        json={
            "version": 1,
            "content_json": {"type": "doc", "content": [{"type": "image", "attrs": {"src": "x"}}]},
        },
    )
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "content_json"


async def test_publish_requires_title_and_content(make_user: UserFactory) -> None:
    c = await make_user("marco")
    created = (await c.post("/api/v1/journals")).json()
    r = await c.post(f"/api/v1/journals/{created['id']}/publish")
    assert r.status_code == 422
    fields = {e["field"] for e in r.json()["errors"]}
    assert fields == {"title", "content_json"}


async def test_slug_is_frozen_after_publish(make_user: UserFactory) -> None:
    c = await make_user("marco")
    j = await published_journal(c)
    r = await c.patch(f"/api/v1/journals/{j['id']}", json={"version": j["version"], "title": "New"})
    assert r.json()["slug"] == j["slug"]
    me = (await c.get("/api/v1/me")).json()
    assert me["journal_count"] == 1


async def test_other_users_cannot_edit(make_user: UserFactory) -> None:
    owner = await make_user("owner")
    other = await make_user("other")
    j = await published_journal(owner)
    assert (await other.get(f"/api/v1/journals/{j['id']}/edit")).status_code == 404
    r = await other.patch(
        f"/api/v1/journals/{j['id']}", json={"version": j["version"], "title": "x"}
    )
    assert r.status_code == 404
    assert (await other.delete(f"/api/v1/journals/{j['id']}")).status_code == 404


async def test_visibility_rules(make_user: UserFactory, client: AsyncClient) -> None:
    owner = await make_user("owner")
    fan = await make_user("fan")
    stranger = await make_user("stranger")
    await fan.put("/api/v1/users/owner/follow")

    public = await published_journal(owner, "Public", "public")
    followers = await published_journal(owner, "Followers", "followers")
    unlisted = await published_journal(owner, "Unlisted", "unlisted")
    private = await published_journal(owner, "Private", "private")

    async def status(c: AsyncClient, j: dict[str, object], token: str | None = None) -> int:
        params = {"t": token} if token else None
        return (await c.get(f"/api/v1/journals/{j['slug']}", params=params)).status_code

    assert await status(client, public) == 200
    assert await status(client, followers) == 404
    assert await status(fan, followers) == 200
    assert await status(stranger, followers) == 404
    assert await status(client, unlisted) == 404
    assert await status(client, unlisted, "wrong-token") == 404
    assert await status(client, unlisted, str(unlisted["share_token"])) == 200
    assert await status(fan, private) == 404
    assert await status(owner, private) == 200

    # Profile listings never include unlisted/private journals for other people.
    def titles(r: object) -> set[str]:
        return {j["title"] for j in r.json()["items"]}  # type: ignore[attr-defined]

    assert titles(await client.get("/api/v1/users/owner/journals")) == {"Public"}
    assert titles(await fan.get("/api/v1/users/owner/journals")) == {"Public", "Followers"}
    assert titles(await owner.get("/api/v1/users/owner/journals")) == {
        "Public",
        "Followers",
        "Unlisted",
        "Private",
    }


async def test_rotating_share_token_invalidates_old_link(
    make_user: UserFactory, client: AsyncClient
) -> None:
    owner = await make_user("owner")
    j = await published_journal(owner, visibility="unlisted")
    rotated = (await owner.post(f"/api/v1/journals/{j['id']}/share-token")).json()
    assert rotated["share_token"] != j["share_token"]
    url = f"/api/v1/journals/{j['slug']}"
    assert (await client.get(url, params={"t": j["share_token"]})).status_code == 404
    assert (await client.get(url, params={"t": rotated["share_token"]})).status_code == 200


async def test_unpublish_and_delete(make_user: UserFactory, client: AsyncClient) -> None:
    c = await make_user("marco")
    j = await published_journal(c)
    url = f"/api/v1/journals/{j['slug']}"
    assert (await client.get(url)).status_code == 200
    assert (await c.post(f"/api/v1/journals/{j['id']}/unpublish")).status_code == 200
    assert (await client.get(url)).status_code == 404
    assert (await c.get(url)).status_code == 200  # owner still sees the draft
    assert (await c.delete(f"/api/v1/journals/{j['id']}")).status_code == 204
    assert (await c.get(url)).status_code == 404
    assert (await c.get("/api/v1/me")).json()["journal_count"] == 0


async def test_og_page(make_user: UserFactory, client: AsyncClient) -> None:
    c = await make_user("marco")
    j = await published_journal(c, "Tea & <Trains>")
    r = await client.get(f"/api/v1/og/j/{j['slug']}")
    assert r.status_code == 200
    assert 'property="og:title" content="Tea &amp; &lt;Trains&gt; by Marco"' in r.text

    private = await published_journal(c, "Secret", "private")
    r = await client.get(f"/api/v1/og/j/{private['slug']}")
    assert "Secret" not in r.text
