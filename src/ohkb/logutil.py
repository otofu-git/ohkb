"""Append-only activity log for ohkb operations."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ohkb.config import get_log_path


def _single_line(value: str, *, limit: int) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
    return " ".join(cleaned.split())[:limit]


def append_log(action: str, detail: str = "") -> None:
    """Append one sanitized, parse-friendly activity line to log.md."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"## [{ts}] {_single_line(action, limit=80) or 'unknown'}"
    if detail:
        line += f" | {_single_line(detail, limit=2000)}"
    path = get_log_path()
    if not path.exists():
        path.write_text("# ohkb activity log\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def read_log(limit: int = 50) -> list[str]:
    """Return the most recent activity lines (newest first)."""
    path = get_log_path()
    if not path.exists():
        return []
    lines = [
        line.rstrip("\n")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("## [")
    ]
    lines.reverse()
    return lines[: max(0, min(limit, 1000))]
