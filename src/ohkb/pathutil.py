"""Filesystem path confinement helpers."""

from __future__ import annotations

import re
from pathlib import Path

_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[/\\]")


def confined_path(base: str | Path, relative: str | Path, *, allow_base: bool = False) -> Path:
    """Resolve ``relative`` under ``base`` and reject every escape attempt.

    Resolution catches existing symlinks that point outside the trusted root.
    Parent traversal, absolute paths, control characters, and platform-specific
    drive paths are rejected before any filesystem mutation takes place.
    """
    base_path = Path(base).expanduser().resolve()
    raw = str(relative)
    if not raw or not raw.strip():
        if allow_base:
            return base_path
        raise ValueError("Path must not be empty.")
    if any(ord(char) < 32 for char in raw):
        raise ValueError("Path must not contain control characters.")

    normalized = raw.replace("\\", "/")
    rel_path = Path(normalized)
    if rel_path.is_absolute() or _WINDOWS_ABSOLUTE.match(normalized):
        raise ValueError("Absolute paths are not allowed.")
    segments = normalized.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError("Path must use canonical child segments.")

    current = base_path
    for segment in segments:
        current = current / segment
        if current.is_symlink():
            raise ValueError("Symbolic links are not allowed in managed paths.")

    candidate = (base_path / rel_path).resolve()
    try:
        candidate.relative_to(base_path)
    except ValueError as exc:
        raise ValueError("Path escapes the allowed data directory.") from exc
    if candidate == base_path and not allow_base:
        raise ValueError("Path must identify an item inside the data directory.")
    return candidate
