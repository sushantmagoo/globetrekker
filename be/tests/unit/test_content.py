import pytest

from app.content.render import ContentError, normalize_video_url, render_document


def p(*inline: dict[str, object], **attrs: object) -> dict[str, object]:
    node: dict[str, object] = {"type": "paragraph", "content": list(inline)}
    if attrs:
        node["attrs"] = attrs
    return node


def t(text: str, *marks: dict[str, object]) -> dict[str, object]:
    return {"type": "text", "text": text, "marks": list(marks)}


def d(*blocks: dict[str, object]) -> dict[str, object]:
    return {"type": "doc", "content": list(blocks)}


def test_renders_marks_headings_and_lists() -> None:
    out = render_document(
        d(
            {"type": "heading", "attrs": {"level": 2}, "content": [t("Day one")]},
            p(t("Bold", {"type": "bold"}), t(" and "), t("italic", {"type": "italic"})),
            {
                "type": "bulletList",
                "content": [{"type": "listItem", "content": [p(t("Temples"))]}],
            },
        )
    )
    assert out.html == (
        "<h2>Day one</h2><p><strong>Bold</strong> and <em>italic</em></p>"
        "<ul><li><p>Temples</p></li></ul>"
    )
    assert out.text == "Day one\nBold and italic\nTemples"
    assert out.word_count == 6
    assert out.reading_minutes == 1


def test_text_is_escaped() -> None:
    out = render_document(d(p(t("<script>alert(1)</script> & co"))))
    assert "<script>" not in out.html
    assert "&lt;script&gt;" in out.html


def test_links_get_safe_rel_and_bad_schemes_are_dropped() -> None:
    good = render_document(
        d(p(t("site", {"type": "link", "attrs": {"href": "https://example.com"}})))
    )
    assert 'href="https://example.com"' in good.html
    assert 'rel="noopener nofollow ugc"' in good.html

    bad = render_document(
        d(p(t("click", {"type": "link", "attrs": {"href": "javascript:alert(1)"}})))
    )
    assert "javascript" not in bad.html
    assert "<a" not in bad.html


def test_text_alignment_becomes_a_class() -> None:
    out = render_document(d(p(t("centred"), textAlign="center")))
    assert out.html == '<p class="ta-center">centred</p>'


def test_images_are_rejected() -> None:
    with pytest.raises(ContentError, match="Images"):
        render_document(d({"type": "image", "attrs": {"src": "https://x/y.png"}}))


def test_unknown_nodes_and_marks_are_rejected() -> None:
    with pytest.raises(ContentError):
        render_document(d({"type": "iframe"}))
    with pytest.raises(ContentError):
        render_document(d(p(t("x", {"type": "onclick"}))))


def test_video_embed_is_normalised() -> None:
    out = render_document(
        d({"type": "videoEmbed", "attrs": {"src": "https://youtu.be/dQw4w9WgXcQ"}})
    )
    assert 'src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"' in out.html
    with pytest.raises(ContentError):
        render_document(d({"type": "videoEmbed", "attrs": {"src": "https://evil.com/x"}}))


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        ),
        (
            "https://youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        ),
        ("https://vimeo.com/76979871", "https://player.vimeo.com/video/76979871"),
        ("https://player.vimeo.com/video/76979871", "https://player.vimeo.com/video/76979871"),
        ("javascript:alert(1)", None),
        ("https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ", None),
    ],
)
def test_normalize_video_url(url: str, expected: str | None) -> None:
    assert normalize_video_url(url) == expected


def test_excerpt_is_trimmed_on_a_word_boundary() -> None:
    out = render_document(d(p(t("word " * 200))))
    assert len(out.excerpt) <= 281
    assert out.excerpt.endswith("…")
    assert out.reading_minutes == 1


def test_empty_document() -> None:
    out = render_document(d())
    assert out.html == "" and out.word_count == 0 and out.reading_minutes == 0
