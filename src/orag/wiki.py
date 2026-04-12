"""Wiki file management -- read/write/edit Markdown files."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from orag.config import get_archive_dir, get_wiki_dir
from orag.models import Entry


def save_entry(entry: Entry, overwrite: bool = False) -> Path:
    """Write an entry to disk as a Markdown file.

    Returns the absolute path to the written file.
    Raises FileExistsError if file exists and overwrite is False.
    """
    wiki_dir = get_wiki_dir()
    file_path = wiki_dir / entry.filename

    if file_path.exists() and not overwrite:
        raise FileExistsError(f"Entry already exists: {entry.filename}. Use --overwrite to replace.")

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(entry.to_markdown(), encoding="utf-8")
    return file_path


def read_entry(rel_path: str) -> Entry:
    """Read an entry from disk.

    Args:
        rel_path: Relative path like 'python/free-threaded-python.md'
    """
    wiki_dir = get_wiki_dir()
    file_path = wiki_dir / rel_path

    if not file_path.exists():
        raise FileNotFoundError(f"Entry not found: {rel_path}")

    text = file_path.read_text(encoding="utf-8")
    parts = rel_path.split("/", 1)
    category = parts[0] if len(parts) > 1 else ""
    return Entry.from_markdown(text, category=category)


def read_file_lines(rel_path: str) -> list[str]:
    """Read a file and return lines (for line-numbered display)."""
    wiki_dir = get_wiki_dir()
    file_path = wiki_dir / rel_path

    if not file_path.exists():
        raise FileNotFoundError(f"Entry not found: {rel_path}")

    return file_path.read_text(encoding="utf-8").splitlines()


def edit_line(rel_path: str, line_num: int, new_content: str) -> None:
    """Replace a single line in a file (1-indexed)."""
    wiki_dir = get_wiki_dir()
    file_path = wiki_dir / rel_path
    lines = file_path.read_text(encoding="utf-8").splitlines()

    if line_num < 1 or line_num > len(lines):
        raise IndexError(f"Line {line_num} out of range (1-{len(lines)})")

    lines[line_num - 1] = new_content
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def edit_lines(rel_path: str, start: int, end: int, new_content: str) -> None:
    """Replace a range of lines (1-indexed, inclusive)."""
    wiki_dir = get_wiki_dir()
    file_path = wiki_dir / rel_path
    lines = file_path.read_text(encoding="utf-8").splitlines()

    if start < 1 or end > len(lines) or start > end:
        raise IndexError(f"Lines {start}-{end} out of range (1-{len(lines)})")

    replacement = new_content.splitlines()
    lines[start - 1 : end] = replacement
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def insert_after(rel_path: str, line_num: int, new_content: str) -> None:
    """Insert content after a specific line (1-indexed)."""
    wiki_dir = get_wiki_dir()
    file_path = wiki_dir / rel_path
    lines = file_path.read_text(encoding="utf-8").splitlines()

    if line_num < 0 or line_num > len(lines):
        raise IndexError(f"Line {line_num} out of range (0-{len(lines)})")

    new_lines = new_content.splitlines()
    lines[line_num:line_num] = new_lines
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def delete_line(rel_path: str, line_num: int) -> None:
    """Delete a single line (1-indexed)."""
    wiki_dir = get_wiki_dir()
    file_path = wiki_dir / rel_path
    lines = file_path.read_text(encoding="utf-8").splitlines()

    if line_num < 1 or line_num > len(lines):
        raise IndexError(f"Line {line_num} out of range (1-{len(lines)})")

    del lines[line_num - 1]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def archive_entry(rel_path: str, reason: str = "") -> Path:
    """Move an entry to the archive directory.

    Returns the path in the archive.
    """
    wiki_dir = get_wiki_dir()
    archive_dir = get_archive_dir()

    src = wiki_dir / rel_path
    if not src.exists():
        raise FileNotFoundError(f"Entry not found: {rel_path}")

    dst = archive_dir / rel_path
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Append archive metadata to the file before moving
    text = src.read_text(encoding="utf-8")
    archive_note = f"\n\n<!-- archived: {datetime.now(timezone.utc).isoformat()} reason: {reason} -->\n"
    dst.write_text(text + archive_note, encoding="utf-8")
    src.unlink()

    # Clean up empty category directory
    parent = src.parent
    if parent != wiki_dir and not any(parent.iterdir()):
        parent.rmdir()

    return dst


def build_tree(
    wiki_dir: Path | None = None,
    *,
    path: str = "",
    depth: int = 2,
) -> dict:
    """Build a tree structure rooted at `path`, limited to `depth` levels.

    Args:
        wiki_dir: Root wiki directory (defaults to configured wiki dir).
        path: Relative path within the wiki to use as the root (e.g. "python").
              Empty string means the wiki root.
        depth: How many levels deep to expand. Children beyond this depth are
               represented as ``{"_truncated": True}`` so callers know they can
               drill down further.

    Returns a nested dict. Each directory node looks like::

        {
            "python": {
                "free-threaded-python.md": None,   # file leaf
                "internals": {"_truncated": True},  # dir truncated by depth
            }
        }

    The top-level result is the node for `path` itself.
    Internal directories whose names start with ``_`` are skipped.
    """
    wiki_dir = wiki_dir or get_wiki_dir()
    root = wiki_dir / path if path else wiki_dir

    if not root.exists():
        raise FileNotFoundError(f"Path not found in wiki: {path!r}")

    def _expand(directory: Path, remaining: int) -> dict:
        node: dict = {}
        try:
            children = sorted(directory.iterdir())
        except PermissionError:
            return node

        for child in children:
            if child.name.startswith("_"):
                continue  # skip internal entries (_index.md, _tables/, etc.)
            if child.is_dir():
                if remaining > 1:
                    node[child.name] = _expand(child, remaining - 1)
                else:
                    # Depth limit reached -- mark as truncated so CLI can hint
                    node[child.name] = {"_truncated": True}
            elif child.suffix == ".md":
                node[child.name] = None  # file leaf

        return node

    return _expand(root, depth)


def update_frontmatter(
    rel_path: str,
    *,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    add_aliases: list[str] | None = None,
    remove_aliases: list[str] | None = None,
    title: str | None = None,
    category: str | None = None,
    entity_type: str | None = None,
) -> Entry:
    """Update metadata of an entry without touching the content body.

    If category changes, the file is moved to the new category directory.
    Returns the updated entry.
    """
    entry = read_entry(rel_path)
    old_path = rel_path

    if add_tags:
        for t in add_tags:
            if t not in entry.tags:
                entry.tags.append(t)
    if remove_tags:
        entry.tags = [t for t in entry.tags if t not in remove_tags]
    if add_aliases:
        for a in add_aliases:
            if a not in entry.aliases:
                entry.aliases.append(a)
    if remove_aliases:
        entry.aliases = [a for a in entry.aliases if a not in remove_aliases]
    if title is not None:
        entry.title = title
    if entity_type is not None:
        entry.entity_type = entity_type

    entry.updated = datetime.now(timezone.utc)

    wiki_dir = get_wiki_dir()

    if category is not None and category != entry.category:
        # Move file to new category
        old_file = wiki_dir / old_path
        entry.category = category
        new_file = wiki_dir / entry.filename
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text(entry.to_markdown(), encoding="utf-8")
        old_file.unlink()

        # Clean up empty old directory
        old_parent = old_file.parent
        if old_parent != wiki_dir and not any(old_parent.iterdir()):
            old_parent.rmdir()
    else:
        save_entry(entry, overwrite=True)

    return entry
