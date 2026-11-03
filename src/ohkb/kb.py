"""KnowledgeBase -- unified service layer for all ohkb operations.

This module extracts the dual-write logic (filesystem + FTS5 index) from cli.py
into a single reusable class. Both the CLI and MCP server call into this layer.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ohkb.bootstrap import init_ohkb
from ohkb.config import get_wiki_dir
from ohkb.extract import extract_file
from ohkb.logutil import append_log, read_log
from ohkb.models import Entry
from ohkb.pathutil import confined_path
from ohkb.sources import add_source_file, list_sources
from ohkb.store import Store
from ohkb.wiki import (
    archive_entry,
    build_tree,
    delete_line,
    edit_line,
    edit_lines,
    insert_after,
    iter_wiki_entries,
    list_archives,
    read_entry,
    read_file_lines,
    restore_entry,
    save_entry,
    touch_updated,
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
        if not query or not query.strip():
            return []
        if limit < 1 or limit > 100:
            raise ValueError("Limit must be between 1 and 100.")
        try:
            results = self._store.search(query, category=category, limit=limit)
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                return []
            raise

        # Normalize BM25 rank into a 0.0–1.0 score relative to the best result.
        # SQLite's bm25() returns negative values (more negative = better match).
        # A simple abs() + round(2) breaks for high-frequency terms (e.g. brand
        # names that appear in almost every document) where IDF collapses the raw
        # value to ~1e-6, rounding to 0.00.  Relative normalisation ensures the
        # top result always scores 1.0 and every returned result scores > 0.
        if results:
            best = max(abs(r.get("rank", 0)) for r in results)
            for r in results:
                raw = abs(r.pop("rank", 0))
                r["score"] = round(raw / best, 4) if best > 0 else 0.0
        else:
            for r in results:
                r.pop("rank", None)
                r["score"] = 0.0

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

    def catalog(self) -> list[dict]:
        """Every indexed entry for the knowledge base index, read from SQLite (no file reads).

        Returns a list sorted by category and path, each with keys:
            path, title, category, tags (list), chars (body length)
        """
        try:
            rows = self._store.catalog()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                return []
            raise
        for row in rows:
            row["tags"] = [tag for tag in (row["tags"] or "").split(",") if tag]
            row["chars"] = row["chars"] or 0
        return rows

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
                "data_dir": "/home/user/.ohkb",
                "in_sync": true,
            }
        """
        stats = self._store.stats()
        wiki_dir = get_wiki_dir()
        disk_paths = set(iter_wiki_entries())
        indexed_paths = self._store.indexed_paths()
        return {
            "indexed_entries": stats["total_entries"],
            "files_on_disk": len(disk_paths),
            "categories": stats["categories"],
            "data_dir": str(wiki_dir.parent),
            "in_sync": disk_paths == indexed_paths,
        }

    def lint(self) -> list[dict]:
        """Check knowledge base health.

        Returns a list of issue dicts:
            {"path": str, "level": str, "issue": str, "detail": str}

        Levels: error, warning, info
        """
        issues: list[dict] = []
        wiki_dir = get_wiki_dir()
        disk_paths = set(iter_wiki_entries())
        indexed_paths = self._store.indexed_paths()

        # Index ↔ disk drift
        for path in sorted(disk_paths - indexed_paths):
            issues.append(
                {
                    "path": path,
                    "level": "error",
                    "issue": "unindexed",
                    "detail": "File exists on disk but is missing from the search index. "
                    "Run: ohkb reindex",
                }
            )
        for path in sorted(indexed_paths - disk_paths):
            issues.append(
                {
                    "path": path,
                    "level": "error",
                    "issue": "missing_file",
                    "detail": "Indexed path has no file on disk. Run: ohkb reindex",
                }
            )

        for rel in sorted(disk_paths):
            md_file = confined_path(wiki_dir, rel)
            text = md_file.read_text(encoding="utf-8")

            # Oversized files
            if len(text) > MAX_ENTRY_CHARS:
                issues.append(
                    {
                        "path": rel,
                        "level": "warning",
                        "issue": "oversized",
                        "detail": f"File is {len(text)} chars (recommended max: {MAX_ENTRY_CHARS})",
                    }
                )

            try:
                # Path-derived category is authoritative for nested paths
                path_category = str(Path(rel).parent).replace("\\", "/") if "/" in rel else ""
                entry = Entry.from_markdown(text, category=path_category)

                if not entry.tags:
                    issues.append(
                        {
                            "path": rel,
                            "level": "warning",
                            "issue": "missing_tags",
                            "detail": "No tags defined. Search quality will be poor.",
                        }
                    )
                if not entry.aliases:
                    issues.append(
                        {
                            "path": rel,
                            "level": "warning",
                            "issue": "missing_aliases",
                            "detail": "No aliases defined. Consider adding synonyms.",
                        }
                    )

                # Frontmatter category vs on-disk path
                fm_category = Entry.from_markdown(text).category
                if fm_category and path_category and fm_category != path_category:
                    issues.append(
                        {
                            "path": rel,
                            "level": "warning",
                            "issue": "category_mismatch",
                            "detail": (
                                f"Frontmatter category '{fm_category}' does not match "
                                f"path category '{path_category}'."
                            ),
                        }
                    )

                # Slug mismatch: file name should match title slug
                expected = entry.filename
                if expected != rel:
                    issues.append(
                        {
                            "path": rel,
                            "level": "info",
                            "issue": "slug_mismatch",
                            "detail": (
                                f"Filename does not match title slug (expected '{expected}')."
                            ),
                        }
                    )
            except ValueError:
                issues.append(
                    {
                        "path": rel,
                        "level": "error",
                        "issue": "invalid_frontmatter",
                        "detail": "Could not parse YAML frontmatter.",
                    }
                )

        # Empty category directories (any depth)
        for dir_path in sorted(wiki_dir.rglob("*")):
            if dir_path.is_symlink() or not dir_path.is_dir():
                continue
            try:
                confined_path(wiki_dir, dir_path.relative_to(wiki_dir))
            except ValueError:
                continue
            rel_parts = dir_path.relative_to(wiki_dir).parts
            if any(part.startswith("_") for part in rel_parts):
                continue
            if dir_path == wiki_dir:
                continue
            # Empty if no .md files anywhere underneath
            has_md = any(dir_path.rglob("*.md"))
            if not has_md:
                rel = str(dir_path.relative_to(wiki_dir)).replace("\\", "/") + "/"
                issues.append(
                    {
                        "path": rel,
                        "level": "info",
                        "issue": "empty_category",
                        "detail": "Category directory is empty.",
                    }
                )

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
        if not title or not title.strip():
            raise ValueError("Title must not be empty.")
        if not category or not category.strip():
            raise ValueError("Category must not be empty.")
        confined_path(get_wiki_dir(), f"{category}/entry.md")

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
        append_log("learn", entry.filename)

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
        Frontmatter lines cannot be edited — use meta() for metadata.

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

        # Stamp the updated timestamp in the frontmatter, then re-index.
        touch_updated(path)
        entry = read_entry(path)
        self._store.upsert(entry)

        file_lines = read_file_lines(path)
        full_text = "\n".join(file_lines)
        append_log("edit", f"{path} ({action})")
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
            FileExistsError: if rename/move would overwrite an existing entry.
        """
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

        # If the path changed (category or title rename), remove the old index entry.
        if entry.filename != path:
            self._store.delete(path)

        self._store.upsert(entry)
        append_log("meta", f"{path} -> {entry.filename}")

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
        append_log("forget", f"{path} ({reason})" if reason else path)

        return {
            "path": path,
            "archived_to": str(archive_path),
            "status": "archived",
        }

    def restore(
        self,
        original_path: str | None = None,
        *,
        archive_path: str | None = None,
        overwrite: bool = False,
    ) -> dict:
        """Restore an archived entry into the wiki and re-index it.

        Returns:
            {"path": str, "restored_from": str, "status": "restored"}
        """
        wiki_path, used_archive = restore_entry(
            original_path,
            archive_path=archive_path,
            overwrite=overwrite,
        )
        entry = read_entry(wiki_path)
        self._store.upsert(entry)
        append_log("restore", wiki_path)
        return {
            "path": wiki_path,
            "restored_from": used_archive,
            "status": "restored",
        }

    def list_archives(self, original_path: str | None = None) -> list[dict]:
        """List archived entries (optionally filtered by original path)."""
        return list_archives(original_path)

    def init(self, *, force: bool = False) -> dict:
        """Scaffold data directory, sources/, log, and agent schema."""
        return init_ohkb(force=force)

    def source_add(self, target: str, *, name: str | None = None) -> dict:
        """Copy an immutable local file into the sources directory."""
        result = add_source_file(target, name=name)
        append_log("source_add", result["path"])
        return result

    def source_list(self) -> list[dict]:
        """List files under sources/."""
        return list_sources()

    def activity_log(self, limit: int = 50) -> list[str]:
        """Return recent activity log lines (newest first)."""
        return read_log(limit=limit)

    def extract(self, target: str) -> dict:
        """Extract plain text from a local file (no LLM)."""
        result = extract_file(target)
        append_log("extract", target)
        return result

    def related(self, path: str, *, limit: int = 10) -> list[dict]:
        """Return entries that share tags with the given path.

        Uses indexed tag overlap only (no embeddings). Excludes `path` itself.
        """
        row = self._store.get(path)
        if row is None:
            # Fall back to reading the file so related works even if slightly stale
            try:
                entry = read_entry(path)
                tags = entry.tags
            except FileNotFoundError:
                raise
        else:
            tags = [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()]

        if not tags:
            return []

        # Score candidates by shared tag count via full list (KB sizes are modest)
        scored: list[tuple[int, dict]] = []
        for other in self._store.list_all():
            if other["path"] == path:
                continue
            other_tags = {t.strip() for t in (other.get("tags") or "").split(",") if t.strip()}
            shared = len(set(tags) & other_tags)
            if shared >= 1:
                scored.append(
                    (
                        shared,
                        {
                            "path": other["path"],
                            "title": other["title"],
                            "category": other["category"],
                            "tags": other.get("tags", ""),
                            "shared_tags": shared,
                        },
                    )
                )

        scored.sort(key=lambda x: (-x[0], x[1]["path"]))
        return [item for _, item in scored[:limit]]

    def reindex(self) -> dict:
        """Rebuild the FTS5 index from wiki files on disk.

        Files are source of truth. Clears the index and re-upserts every entry.

        Returns:
            {
                "indexed": int,
                "errors": [{"path": str, "error": str}],
                "status": "ok" | "partial",
            }
        """
        self._store.clear_all()
        indexed = 0
        errors: list[dict] = []

        for rel in iter_wiki_entries():
            try:
                entry = read_entry(rel)
                # Ensure index path matches the on-disk path even if the title
                # slug would differ (slug_mismatch is reported by lint only).
                # Temporarily force filename via category/title is not enough
                # when slug ≠ basename — index by actual path.
                self._store.upsert_at_path(entry, rel)
                indexed += 1
            except Exception as exc:
                errors.append({"path": rel, "error": str(exc)})

        append_log("reindex", f"indexed={indexed}")
        return {
            "indexed": indexed,
            "errors": errors,
            "status": "ok" if not errors else "partial",
        }
