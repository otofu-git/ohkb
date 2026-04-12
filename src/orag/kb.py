"""KnowledgeBase -- unified service layer for all orag operations.

This module extracts the dual-write logic (filesystem + FTS5 index) from cli.py
into a single reusable class. Both the CLI and MCP server call into this layer.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from orag.config import get_wiki_dir
from orag.models import Entry
from orag.store import Store
from orag.wiki import (
    archive_entry,
    build_tree,
    delete_line,
    edit_line,
    edit_lines,
    insert_after,
    read_entry,
    read_file_lines,
    save_entry,
    update_frontmatter,
)

# Maximum recommended file size in characters
MAX_ENTRY_CHARS = 3000


class KnowledgeBase:
    """High-level knowledge base operations with consistent dual-write semantics.

    Every mutating operation writes to the filesystem first, then updates the
    FTS5 index. The caller does not need to coordinate these two stores.
    """

    def __init__(self, store: Store | None = None) -> None:
        self._store = store or Store()

    @property
    def store(self) -> Store:
        return self._store

    def close(self) -> None:
        """Release database resources."""
        self._store.close()

    # ── Read operations ─────────────────────────────────────────────────────

    def search(self, query: str, category: str | None = None, limit: int = 20) -> list[dict]:
        """Full-text search over the knowledge base.

        Returns a list of result dicts with keys:
            path, title, category, tags, aliases, entity_type, score
        """
        try:
            results = self._store.search(query, category=category, limit=limit)
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                return []
            raise

        # Normalize the rank into a positive score for readability
        for r in results:
            r["score"] = round(abs(r.pop("rank", 0)), 2)

        return results

    def get(self, path: str) -> dict:
        """Read a knowledge entry with line numbers, char count, and line count.

        Returns:
            {
                "path": "category/file.md",
                "chars": 847,
                "lines": 21,
                "content": ["line1", "line2", ...]
            }

        Raises FileNotFoundError if the file does not exist.
        """
        lines = read_file_lines(path)
        full_text = "\n".join(lines)
        return {
            "path": path,
            "chars": len(full_text),
            "lines": len(lines),
            "content": lines,
        }

    def tree(self, path: str = "", *, depth: int = 2) -> dict:
        """Browse knowledge structure rooted at `path`, limited to `depth` levels.

        Args:
            path: Relative path within the wiki (e.g. "python"). Empty = wiki root.
            depth: How many directory levels to expand. Directories beyond this
                   depth appear as ``{"_truncated": True}``.

        Returns:
            {
                "path": "python",
                "depth": 2,
                "tree": {
                    "free-threaded-python.md": None,
                    "internals": {"_truncated": True},
                },
            }

        Raises:
            FileNotFoundError: if path does not exist in the wiki.
        """
        nodes = build_tree(path=path, depth=depth)
        return {
            "path": path or "/",
            "depth": depth,
            "tree": nodes,
        }

    def status(self) -> dict:
        """Knowledge base statistics.

        Returns:
            {
                "indexed_entries": 42,
                "files_on_disk": 42,
                "categories": ["python", "rust"],
                "data_dir": "/home/user/.orag",
            }
        """
        stats = self._store.stats()
        wiki_dir = get_wiki_dir()
        file_count = sum(
            1
            for f in wiki_dir.rglob("*.md")
            if not f.relative_to(wiki_dir).parts[0].startswith("_")
        )
        return {
            "indexed_entries": stats["total_entries"],
            "files_on_disk": file_count,
            "categories": stats["categories"],
            "data_dir": str(get_wiki_dir().parent),
        }

    def lint(self) -> list[dict]:
        """Check knowledge base health.

        Returns a list of issue dicts:
            {"path": str, "level": str, "issue": str, "detail": str}

        Levels: error, warning, info
        """
        issues: list[dict] = []
        wiki_dir = get_wiki_dir()

        for md_file in wiki_dir.rglob("*.md"):
            rel = str(md_file.relative_to(wiki_dir))
            # Skip internal files (_index.md, _tables/, etc.)
            if rel.startswith("_"):
                continue

            text = md_file.read_text(encoding="utf-8")

            # Oversized files
            if len(text) > MAX_ENTRY_CHARS:
                issues.append({
                    "path": rel,
                    "level": "warning",
                    "issue": "oversized",
                    "detail": f"File is {len(text)} chars (recommended max: {MAX_ENTRY_CHARS})",
                })

            # Missing tags or aliases
            try:
                entry = Entry.from_markdown(text)
                if not entry.tags:
                    issues.append({
                        "path": rel,
                        "level": "warning",
                        "issue": "missing_tags",
                        "detail": "No tags defined. Search quality will be poor.",
                    })
                if not entry.aliases:
                    issues.append({
                        "path": rel,
                        "level": "warning",
                        "issue": "missing_aliases",
                        "detail": "No aliases defined. Consider adding synonyms.",
                    })
            except ValueError:
                issues.append({
                    "path": rel,
                    "level": "error",
                    "issue": "invalid_frontmatter",
                    "detail": "Could not parse YAML frontmatter.",
                })

        # Empty category directories
        for cat_dir in wiki_dir.iterdir():
            if cat_dir.is_dir() and not cat_dir.name.startswith("_"):
                md_files = list(cat_dir.glob("*.md"))
                if not md_files:
                    issues.append({
                        "path": cat_dir.name + "/",
                        "level": "info",
                        "issue": "empty_category",
                        "detail": "Category directory is empty.",
                    })

        return issues

    # ── Write operations ────────────────────────────────────────────────────

    def learn(
        self,
        content: str,
        title: str,
        category: str,
        tags: list[str] | None = None,
        aliases: list[str] | None = None,
        entity_type: str = "concept",
        source: str = "manual",
        overwrite: bool = False,
    ) -> dict:
        """Store a new knowledge entry.

        Writes the Markdown file, then indexes it in FTS5.

        Returns:
            {"path": "category/slug.md", "status": "created", "chars": 123}

        Raises:
            FileExistsError: if the entry already exists and overwrite is False.
            ValueError: if content is empty.
        """
        if not content or not content.strip():
            raise ValueError("Content must not be empty.")

        warnings: list[str] = []
        tag_list = tags or []
        alias_list = aliases or []

        if not tag_list:
            warnings.append("No tags provided. Search quality depends on good tags.")
        if not alias_list:
            warnings.append("No aliases provided. Consider adding synonyms for better search.")

        entry = Entry(
            title=title,
            category=category,
            content=content.strip(),
            tags=tag_list,
            aliases=alias_list,
            entity_type=entity_type,
            source=source,
        )

        # Filesystem write
        save_entry(entry, overwrite=overwrite)

        # FTS index
        self._store.upsert(entry)

        result: dict = {
            "path": entry.filename,
            "status": "created",
            "chars": len(entry.content),
        }
        if warnings:
            result["warnings"] = warnings

        return result

    def edit(
        self,
        path: str,
        *,
        line: int | None = None,
        lines: tuple[int, int] | None = None,
        after: int | None = None,
        delete: int | None = None,
        content: str = "",
    ) -> dict:
        """Edit a knowledge entry at the line level.

        Exactly one of line, lines, after, or delete must be specified.

        Returns:
            {"path": str, "action": str, "chars": int, "lines": int}

        Raises:
            ValueError: if no edit operation is specified or arguments are invalid.
            FileNotFoundError: if the file does not exist.
            IndexError: if line numbers are out of range.
        """
        ops = sum(x is not None for x in [line, lines, after, delete])
        if ops != 1:
            raise ValueError("Specify exactly one of: line, lines, after, or delete.")

        if delete is not None:
            delete_line(path, delete)
            action = f"deleted line {delete}"
        elif line is not None:
            edit_line(path, line, content)
            action = f"replaced line {line}"
        elif lines is not None:
            start, end = lines
            if start > end:
                raise ValueError(f"Invalid range: {start}-{end}")
            edit_lines(path, start, end, content)
            action = f"replaced lines {start}-{end}"
        elif after is not None:
            insert_after(path, after, content)
            action = f"inserted after line {after}"
        else:
            raise ValueError("No edit operation specified.")  # pragma: no cover

        # Re-index after edit
        entry = read_entry(path)
        self._store.upsert(entry)

        file_lines = read_file_lines(path)
        full_text = "\n".join(file_lines)
        return {
            "path": path,
            "action": action,
            "chars": len(full_text),
            "lines": len(file_lines),
        }

    def meta(
        self,
        path: str,
        *,
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
        add_aliases: list[str] | None = None,
        remove_aliases: list[str] | None = None,
        title: str | None = None,
        category: str | None = None,
        entity_type: str | None = None,
    ) -> dict:
        """Update metadata of a knowledge entry.

        Returns:
            {"path": str, "status": "updated"}

        Raises:
            FileNotFoundError: if the file does not exist.
        """
        old_category = path.split("/")[0] if "/" in path else ""

        entry = update_frontmatter(
            path,
            add_tags=add_tags,
            remove_tags=remove_tags,
            add_aliases=add_aliases,
            remove_aliases=remove_aliases,
            title=title,
            category=category,
            entity_type=entity_type,
        )

        # If category changed, remove old index entry
        if category and category != old_category:
            self._store.delete(path)

        self._store.upsert(entry)

        return {"path": entry.filename, "status": "updated"}

    def forget(self, path: str, reason: str = "") -> dict:
        """Archive a knowledge entry.

        Moves the file to the archive directory and removes it from the index.

        Returns:
            {"path": str, "archived_to": str, "status": "archived"}

        Raises:
            FileNotFoundError: if the file does not exist.
        """
        archive_path = archive_entry(path, reason=reason)
        self._store.delete(path)

        return {
            "path": path,
            "archived_to": str(archive_path),
            "status": "archived",
        }
