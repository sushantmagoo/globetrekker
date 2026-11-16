from httpx import AsyncClient

from tests.integration.conftest import UserFactory, published_journal


async def test_follow_counts_and_notification(make_user: UserFactory) -> None:
    ana = await make_user("ana")
    ben = await make_user("ben")
    assert (await ben.put("/api/v1/users/ana/follow")).status_code == 204
    assert (await ben.put("/api/v1/users/ana/follow")).status_code == 204  # idempotent

    profile = (await ben.get("/api/v1/users/ana")).json()
    assert profile["follower_count"] == 1
    assert profile["is_following"] is True
    followers = (await ana.get("/api/v1/users/ana/followers")).json()
    assert [u["username"] for u in followers["items"]] == ["ben"]

    assert (await ana.get("/api/v1/notifications/unread-count")).json()["count"] == 1
    notes = (await ana.get("/api/v1/notifications")).json()["items"]
    assert notes[0]["type"] == "follow"
    assert notes[0]["actor"]["username"] == "ben"
    await ana.post("/api/v1/notifications/read", json={})
    assert (await ana.get("/api/v1/notifications/unread-count")).json()["count"] == 0

    assert (await ben.delete("/api/v1/users/ana/follow")).status_code == 204
    assert (await ben.get("/api/v1/users/ana")).json()["follower_count"] == 0
    assert (await ana.put("/api/v1/users/ana/follow")).status_code == 400


async def test_likes_and_bookmarks(make_user: UserFactory) -> None:
    ana = await make_user("ana")
    ben = await make_user("ben")
    j = await published_journal(ana)

    for _ in range(2):
        assert (await ben.put(f"/api/v1/journals/{j['id']}/like")).status_code == 204
    await ben.put(f"/api/v1/journals/{j['id']}/bookmark")
    detail = (await ben.get(f"/api/v1/journals/{j['slug']}")).json()
    assert detail["like_count"] == 1
    assert detail["liked_by_me"] is True
    assert detail["bookmarked_by_me"] is True
    assert [b["id"] for b in (await ben.get("/api/v1/me/bookmarks")).json()] == [j["id"]]

    # Liking again after unliking within the hour doesn't spam the author.
    await ben.delete(f"/api/v1/journals/{j['id']}/like")
    await ben.put(f"/api/v1/journals/{j['id']}/like")
    notes = (await ana.get("/api/v1/notifications")).json()["items"]
    assert [n["type"] for n in notes] == ["like"]


async def test_cannot_like_private_journal(make_user: UserFactory) -> None:
    ana = await make_user("ana")
    ben = await make_user("ben")
    j = await published_journal(ana, visibility="private")
    assert (await ben.put(f"/api/v1/journals/{j['id']}/like")).status_code == 404


async def test_comments_and_replies(make_user: UserFactory, client: AsyncClient) -> None:
    ana = await make_user("ana")
    ben = await make_user("ben")
    cara = await make_user("cara")
    j = await published_journal(ana)
    base = f"/api/v1/journals/{j['id']}/comments"

    top = (await ben.post(base, json={"body": "  Gorgeous!  "})).json()
    assert top["body"] == "Gorgeous!"
    reply = (await cara.post(base, json={"body": "Agreed", "parent_id": top["id"]})).json()
    # Replying to a reply attaches to the top-level comment.
    nested = (await ana.post(base, json={"body": "Thanks", "parent_id": reply["id"]})).json()
    assert nested["parent_id"] == top["id"]

    listed = (await client.get(base)).json()
    assert len(listed) == 1
    assert [r["body"] for r in listed[0]["replies"]] == ["Agreed", "Thanks"]
    assert (await client.get(f"/api/v1/journals/{j['slug']}")).json()["comment_count"] == 3

    types = sorted(n["type"] for n in (await ben.get("/api/v1/notifications")).json()["items"])
    assert types == ["reply", "reply"]

    r = await ben.patch(f"/api/v1/comments/{top['id']}", json={"body": "Stunning!"})
    assert r.status_code == 200 and r.json()["edited_at"] is not None
    assert (
        await cara.patch(f"/api/v1/comments/{top['id']}", json={"body": "x"})
    ).status_code == 403

    # The journal owner can delete any comment; replies go with it.
    assert (await ana.delete(f"/api/v1/comments/{top['id']}")).status_code == 204
    assert (await client.get(base)).json() == []
    assert (await client.get(f"/api/v1/journals/{j['slug']}")).json()["comment_count"] == 0


async def test_home_feed(make_user: UserFactory) -> None:
    ana = await make_user("ana")
    ben = await make_user("ben")
    cara = await make_user("cara")
    await ben.put("/api/v1/users/ana/follow")

    await published_journal(ana, "Ana public", "public")
    await published_journal(ana, "Ana followers", "followers")
    await published_journal(ana, "Ana private", "private")
    await published_journal(cara, "Cara public", "public")
    await published_journal(ben, "Ben own", "public")

    titles = [j["title"] for j in (await ben.get("/api/v1/feed/home")).json()["items"]]
    assert titles == ["Ben own", "Ana followers", "Ana public"]


async def test_explore_pagination_and_filters(make_user: UserFactory, client: AsyncClient) -> None:
    ana = await make_user("ana")
    for i in range(5):
        await published_journal(
            ana,
            f"Trip {i}",
            tags=["peru"] if i % 2 else [],
            location={"place_name": "Cusco", "country_code": "PE", "lat": -13.5, "lng": -71.9}
            if i == 4
            else None,
        )
    await published_journal(ana, "Hidden", "followers")

    page1 = (await client.get("/api/v1/feed/explore", params={"limit": 3})).json()
    assert [j["title"] for j in page1["items"]] == ["Trip 4", "Trip 3", "Trip 2"]
    page2 = (
        await client.get(
            "/api/v1/feed/explore", params={"limit": 3, "cursor": page1["next_cursor"]}
        )
    ).json()
    assert [j["title"] for j in page2["items"]] == ["Trip 1", "Trip 0"]
    assert page2["next_cursor"] is None

    tagged = (await client.get("/api/v1/feed/explore", params={"tag": "peru"})).json()
    assert {j["title"] for j in tagged["items"]} == {"Trip 1", "Trip 3"}
    by_country = (await client.get("/api/v1/feed/explore", params={"country": "pe"})).json()
    assert [j["title"] for j in by_country["items"]] == ["Trip 4"]

    trending = (await client.get("/api/v1/feed/explore", params={"sort": "trending"})).json()
    assert len(trending["items"]) == 5


async def test_deleted_author_content_disappears(
    make_user: UserFactory, client: AsyncClient
) -> None:
    ana = await make_user("ana")
    j = await published_journal(ana)
    await ana.delete("/api/v1/me")
    assert (await client.get(f"/api/v1/journals/{j['slug']}")).status_code == 404
    assert (await client.get("/api/v1/feed/explore")).json()["items"] == []
