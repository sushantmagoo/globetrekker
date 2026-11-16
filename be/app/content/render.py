"""ProseMirror (TipTap) JSON → validated, sanitised HTML + plain text.

The editor's JSON is the canonical format. We never trust HTML from the client: HTML is
rendered here from an allowlist of node and mark types and then passed through nh3.
"""

import html
import json
import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

import nh3

MAX_JSON_BYTES = 1_000_000
MAX_DEPTH = 40
WORDS_PER_MINUTE = 230
EXCERPT_LEN = 280

BLOCK_NODES = {
    "paragraph",
    "heading",
    "bulletList",
    "orderedList",
    "listItem",
    "blockquote",
    "horizontalRule",
    "codeBlock",
    "videoEmbed",
}
INLINE_NODES = {"text", "hardBreak"}
MARKS = {"bold", "italic", "underline", "strike", "code", "highlight", "link"}
ALIGNMENTS = {"left", "center", "right", "justify"}

ALLOWED_TAGS = {
    "p",
    "h2",
    "h3",
    "ul",
    "ol",
    "li",
    "blockquote",
    "hr",
    "pre",
    "code",
    "br",
    "strong",
    "em",
    "u",
    "s",
    "mark",
    "a",
    "div",
    "iframe",
}
ALLOWED_ATTRS = {
    "a": {"href"},
    "ol": {"start"},
    "iframe": {"src", "title", "allow", "allowfullscreen", "loading", "referrerpolicy"},
}
ALLOWED_CLASSES = {
    "p": {"ta-left", "ta-center", "ta-right", "ta-justify"},
    "h2": {"ta-left", "ta-center", "ta-right", "ta-justify"},
    "h3": {"ta-left", "ta-center", "ta-right", "ta-justify"},
    "div": {"video-embed"},
}

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VIMEO_ID = re.compile(r"^\d{6,12}$")


class ContentError(ValueError):
    """Raised when the document doesn't match the allowed schema."""


@dataclass(frozen=True)
class RenderedContent:
    html: str
    text: str
    excerpt: str
    word_count: int
    reading_minutes: int


def normalize_video_url(url: str) -> str | None:
    """Return a privacy-friendly embed URL for YouTube/Vimeo, or None if not allowed."""
    try:
        u = urlparse(url.strip())
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    video_id: str | None = None
    if host in ("youtube.com", "youtube-nocookie.com"):
        if u.path == "/watch":
            video_id = next(iter(parse_qs(u.query).get("v", [])), None)
        elif u.path.startswith(("/embed/", "/shorts/", "/live/")):
            video_id = u.path.split("/")[2]
        if video_id and _YT_ID.match(video_id):
            return f"https://www.youtube-nocookie.com/embed/{video_id}"
    elif host == "youtu.be":
        video_id = u.path.lstrip("/").split("/")[0]
        if _YT_ID.match(video_id):
            return f"https://www.youtube-nocookie.com/embed/{video_id}"
    elif host in ("vimeo.com", "player.vimeo.com"):
        parts = [p for p in u.path.split("/") if p]
        video_id = parts[-1] if parts else None
        if video_id and _VIMEO_ID.match(video_id):
            return f"https://player.vimeo.com/video/{video_id}"
    return None


def _safe_href(href: Any) -> str | None:
    if not isinstance(href, str):
        return None
    clean: str = href.strip()
    if urlparse(clean).scheme.lower() in ("http", "https", "mailto"):
        return clean
    return None


def _align_class(node: dict[str, Any]) -> str:
    align = (node.get("attrs") or {}).get("textAlign")
    if align in ALIGNMENTS and align != "left":
        return f' class="ta-{align}"'
    return ""


class _Renderer:
    def __init__(self) -> None:
        self.text_blocks: list[str] = []

    def render_doc(self, doc: Any) -> str:
        if not isinstance(doc, dict) or doc.get("type") != "doc":
            raise ContentError("Document root must be of type 'doc'")
        return "".join(self._block(n, 1) for n in self._children(doc))

    @staticmethod
    def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
        content = node.get("content", [])
        if not isinstance(content, list) or not all(isinstance(c, dict) for c in content):
            raise ContentError("Node content must be a list of nodes")
        return content

    def _block(self, node: dict[str, Any], depth: int) -> str:
        if depth > MAX_DEPTH:
            raise ContentError("Document is nested too deeply")
        t = node.get("type")
        if t == "image":
            raise ContentError("Images are not supported")
        if t not in BLOCK_NODES:
            raise ContentError(f"Unsupported block: {t!r}")
        kids = self._children(node)

        if t == "paragraph":
            inner, plain = self._inline(kids)
            self.text_blocks.append(plain)
            return f"<p{_align_class(node)}>{inner}</p>"
        if t == "heading":
            level = (node.get("attrs") or {}).get("level", 2)
            level = 3 if level == 3 else 2
            inner, plain = self._inline(kids)
            self.text_blocks.append(plain)
            return f"<h{level}{_align_class(node)}>{inner}</h{level}>"
        if t == "codeBlock":
            inner, plain = self._inline(kids, allow_marks=False)
            self.text_blocks.append(plain)
            return f"<pre><code>{inner}</code></pre>"
        if t == "horizontalRule":
            return "<hr>"
        if t == "videoEmbed":
            src = normalize_video_url(str((node.get("attrs") or {}).get("src", "")))
            if not src:
                raise ContentError("Only YouTube and Vimeo videos can be embedded")
            return (
                '<div class="video-embed"><iframe src="' + html.escape(src) + '" '
                'title="Embedded video" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" '
                'allow="encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>'
            )

        inner = "".join(self._block(k, depth + 1) for k in kids)
        if t == "bulletList":
            return f"<ul>{inner}</ul>"
        if t == "orderedList":
            start = (node.get("attrs") or {}).get("start", 1)
            start_attr = f' start="{int(start)}"' if isinstance(start, int) and start != 1 else ""
            return f"<ol{start_attr}>{inner}</ol>"
        if t == "listItem":
            return f"<li>{inner}</li>"
        # blockquote
        return f"<blockquote>{inner}</blockquote>"

    def _inline(self, nodes: list[dict[str, Any]], allow_marks: bool = True) -> tuple[str, str]:
        out: list[str] = []
        plain: list[str] = []
        for n in nodes:
            t = n.get("type")
            if t == "image":
                raise ContentError("Images are not supported")
            if t not in INLINE_NODES:
                raise ContentError(f"Unsupported inline node: {t!r}")
            if t == "hardBreak":
                out.append("<br>")
                plain.append("\n")
                continue
            text = n.get("text", "")
            if not isinstance(text, str):
                raise ContentError("Text node must contain a string")
            plain.append(text)
            piece = html.escape(text, quote=False)
            if allow_marks:
                piece = self._apply_marks(piece, n.get("marks") or [])
            out.append(piece)
        return "".join(out), "".join(plain)

    @staticmethod
    def _apply_marks(piece: str, marks: list[Any]) -> str:
        # Wrap in reverse so the first mark is the outermost element.
        for mark in reversed(marks):
            if not isinstance(mark, dict):
                raise ContentError("Invalid mark")
            m = mark.get("type")
            if m not in MARKS:
                raise ContentError(f"Unsupported mark: {m!r}")
            if m == "link":
                href = _safe_href((mark.get("attrs") or {}).get("href"))
                if href:
                    piece = f'<a href="{html.escape(href)}">{piece}</a>'
                continue
            tag = {
                "bold": "strong",
                "italic": "em",
                "underline": "u",
                "strike": "s",
                "code": "code",
                "highlight": "mark",
            }[m]
            piece = f"<{tag}>{piece}</{tag}>"
        return piece


def sanitize_html(raw: str) -> str:
    return nh3.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        allowed_classes=ALLOWED_CLASSES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener nofollow ugc",
        strip_comments=True,
    )


def make_excerpt(text: str, limit: int = EXCERPT_LEN) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:!?-") + "…"


def render_document(doc: Any) -> RenderedContent:
    if len(json.dumps(doc, separators=(",", ":"))) > MAX_JSON_BYTES:
        raise ContentError("Journal is too large")
    renderer = _Renderer()
    raw_html = renderer.render_doc(doc)
    text = "\n".join(b for b in renderer.text_blocks if b.strip())
    words = len(text.split())
    return RenderedContent(
        html=sanitize_html(raw_html),
        text=text,
        excerpt=make_excerpt(text),
        word_count=words,
        reading_minutes=max(1, math.ceil(words / WORDS_PER_MINUTE)) if words else 0,
    )
