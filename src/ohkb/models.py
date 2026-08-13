"""Data models for ohkb knowledge entries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import yaml

MAX_SLUG_BYTES = 180


@dataclass
class Entry:
    """A single knowledge entry stored as a Markdown file with YAML frontmatter."""

    title: str
    category: str
    content: str
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    entity_type: str = "concept"
    source: str = "manual"
    created: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def slug(self) -> str:
        """Generate a bounded filesystem slug from the title."""
        value = self.title.lower().strip()
        value = re.sub(r"[^\w\s-]", "", value)
        value = re.sub(r"[\s_]+", "-", value)
        value = re.sub(r"-+", "-", value).strip("-") or "untitled"
        return value.encode("utf-8")[:MAX_SLUG_BYTES].decode("utf-8", errors="ignore") or "untitled"

    @property
    def filename(self) -> str:
        """Return the canonical relative path: category/slug.md."""
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValueError("Category must not be empty.")
        return f"{self.category}/{self.slug}.md"

    def to_markdown(self) -> str:
        """Serialize to Markdown with YAML frontmatter."""
        meta: dict[str, Any] = {
            "title": self.title,
            "category": self.category,
            "tags": self.tags,
            "aliases": self.aliases,
            "entity_type": self.entity_type,
            "source": self.source,
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
        }
        front = yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return f"---\n{front}---\n\n{self.content}\n"

    @classmethod
    def from_markdown(cls, text: str, category: str | None = None) -> Entry:
        """Parse a Markdown file with validated YAML frontmatter fields."""
        match = re.match(r"^---\n(.+?)\n---\n\n?(.*)", text, re.DOTALL)
        if not match:
            raise ValueError("Invalid frontmatter format")

        meta = yaml.safe_load(match.group(1))
        if not isinstance(meta, dict):
            raise ValueError("Frontmatter must be a mapping.")
        content = match.group(2).rstrip("\n")

        parsed_category = category if category is not None else _string_field(meta, "category", "")
        return cls(
            title=_string_field(meta, "title", ""),
            category=parsed_category,
            content=content,
            tags=_string_list(meta, "tags"),
            aliases=_string_list(meta, "aliases"),
            entity_type=_string_field(meta, "entity_type", "concept"),
            source=_string_field(meta, "source", "manual"),
            created=_parse_dt(meta.get("created")),
            updated=_parse_dt(meta.get("updated")),
        )


def _string_field(meta: dict[str, Any], key: str, default: str) -> str:
    value = meta.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"Frontmatter field '{key}' must be a string.")
    return value


def _string_list(meta: dict[str, Any], key: str) -> list[str]:
    value = meta.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Frontmatter field '{key}' must be a list of strings.")
    return value


def _parse_dt(value: Any) -> datetime:
    """Parse a datetime from string or return current UTC time."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(timezone.utc)
