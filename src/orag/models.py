"""Data models for orag knowledge entries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import yaml


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
        """Generate a filename slug from the title."""
        s = self.title.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s)
        s = re.sub(r"-+", "-", s).strip("-")
        return s or "untitled"

    @property
    def filename(self) -> str:
        """Return the relative path: category/slug.md"""
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
        """Parse a Markdown file with YAML frontmatter into an Entry."""
        match = re.match(r"^---\n(.+?)\n---\n\n?(.*)", text, re.DOTALL)
        if not match:
            raise ValueError("Invalid frontmatter format")

        meta = yaml.safe_load(match.group(1))
        content = match.group(2).rstrip("\n")

        return cls(
            title=meta.get("title", ""),
            category=category or meta.get("category", ""),
            content=content,
            tags=meta.get("tags", []),
            aliases=meta.get("aliases", []),
            entity_type=meta.get("entity_type", "concept"),
            source=meta.get("source", "manual"),
            created=_parse_dt(meta.get("created")),
            updated=_parse_dt(meta.get("updated")),
        )


def _parse_dt(val: Any) -> datetime:
    """Parse a datetime from string or return current UTC time."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            pass
    return datetime.now(timezone.utc)
