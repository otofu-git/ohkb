"""Local file text extraction helpers — no LLM calls or network access."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

MAX_EXTRACT_BYTES = 10 * 1024 * 1024


class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML → text (stdlib only)."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True
        elif tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False
        elif tag in ("p", "div", "li", "h1", "h2", "h3", "h4"):
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def extract_file(path: str | Path) -> dict:
    """Extract text from a local file.

    Supports plain text and HTML by extension/content. Binary PDFs are rejected
    with a clear error (no native PDF dependency in core).

    Returns:
        {"kind": "file", "path": str, "chars": int, "text": str}
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not p.is_file():
        raise ValueError(f"Not a file: {path}")
    size = p.stat().st_size
    if size > MAX_EXTRACT_BYTES:
        raise ValueError(f"File exceeds extraction limit of {MAX_EXTRACT_BYTES} bytes.")

    suffix = p.suffix.lower()
    if suffix in (".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".gif", ".zip"):
        raise ValueError(
            f"Unsupported binary type '{suffix}'. "
            "Convert to text/markdown first, or paste text into learn."
        )

    data = p.read_bytes()
    # Sniff UTF-8 / latin-1
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")

    if suffix in (".html", ".htm") or text.lstrip().lower().startswith(("<!doctype html", "<html")):
        text = html_to_text(text)

    text = text.strip()
    if not text:
        raise ValueError(f"No extractable text in: {path}")

    return {
        "kind": "file",
        "path": str(p),
        "chars": len(text),
        "text": text,
    }


def html_to_text(html: str) -> str:
    """Convert HTML to plain text using the stdlib parser."""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()
