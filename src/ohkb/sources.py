"""Immutable local-file source intake."""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ohkb.config import get_sources_dir
from ohkb.pathutil import confined_path

MAX_SOURCE_BYTES = 100 * 1024 * 1024


def add_source_file(path: str | Path, *, name: str | None = None) -> dict:
    """Copy a local file into sources/."""
    src = Path(path).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    size = src.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ValueError(f"Source file exceeds {MAX_SOURCE_BYTES} bytes.")

    dest_name = _safe_name(name or src.name)
    dest = _unique_dest(dest_name)
    shutil.copy2(src, dest)

    rel = dest.relative_to(get_sources_dir()).as_posix()
    return {"path": rel, "status": "created", "bytes": dest.stat().st_size, "origin": str(src)}


def list_sources() -> list[dict]:
    """List regular, non-symlink files under sources/."""
    root = get_sources_dir()
    items: list[dict] = []
    for file_path in sorted(root.rglob("*")):
        if file_path.is_symlink() or not file_path.is_file():
            continue
        try:
            safe_path = confined_path(root, file_path.relative_to(root))
        except ValueError:
            continue
        items.append(
            {
                "path": safe_path.relative_to(root).as_posix(),
                "bytes": safe_path.stat().st_size,
                "mtime": safe_path.stat().st_mtime,
            }
        )
    return items


def _safe_name(name: str) -> str:
    basename = name.strip().replace("\\", "/").split("/")[-1]
    basename = re.sub(r"[^\w.\-]+", "_", basename, flags=re.UNICODE)
    if basename in {"", ".", ".."}:
        basename = "source"
    encoded = basename.encode("utf-8")[:200]
    return encoded.decode("utf-8", errors="ignore") or "source"


def _unique_dest(name: str) -> Path:
    root = get_sources_dir()
    dest = confined_path(root, name)
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return confined_path(root, f"{stem}__{ts}{suffix}")
