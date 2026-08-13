"""Wiki file management -- read/write/edit Markdown files."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from ohkb.config import get_archive_dir, get_wiki_dir
from ohkb.models import Entry
from ohkb.pathutil import confined_path


def save_entry(entry: Entry, overwrite: bool = False) -> Path:
    """Write an entry to disk as a Markdown file.

    Returns the absolute path to the written file.
    Raises FileExistsError if file exists and overwrite is False.
    """
    wiki_dir = get_wiki_dir()
    file_path = confined_path(wiki_dir, entry.filename)

    if file_path.exists() and not overwrite:
        raise FileExistsError(
            f"Entry already exists: {entry.filename}. Use --overwrite to replace."
        )

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(entry.to_markdown(), encoding="utf-8")
    return file_path


def read_entry(rel_path: str) -> Entry:
    """Read an entry from disk.

    Args:
        rel_path: Relative path like 'python/free-threaded-python.md'
    """
    wiki_dir = get_wiki_dir()
    file_path = confined_path(wiki_dir, rel_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Entry not found: {rel_path}")

    text = file_path.read_text(encoding="utf-8")
    parent = file_path.relative_to(wiki_dir).parent.as_posix()
    category = "" if parent == "." else parent
    return Entry.from_markdown(text, category=category)


def read_file_lines(rel_path: str) -> list[str]:
    """Read a file and return lines (for line-numbered display)."""
    wiki_dir = get_wiki_dir()
    file_path = confined_path(wiki_dir, rel_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Entry not found: {rel_path}")

    return file_path.read_text(encoding="utf-8").splitlines()


def frontmatter_line_range(lines: list[str]) -> tuple[int, int] | None:
    """Return 1-indexed inclusive line range of the YAML frontmatter block.

    Includes both opening and closing ``---`` delimiters. Returns None if the
    file has no valid frontmatter block at the top.
    """
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return (1, i + 1)
    return None


def _assert_body_lines(rel_path: str, *line_nums: int | None) -> None:
    """Raise ValueError if any line number falls inside the frontmatter block."""
    lines = read_file_lines(rel_path)
    fm = frontmatter_line_range(lines)
    if fm is None:
        return
    start, end = fm
    for n in line_nums:
        if n is not None and start <= n <= end:
            raise ValueError(
                f"Cannot edit frontmatter line {n} (lines {start}-{end}). "
                "Use 'ohkb meta' to change metadata."
            )


def edit_line(rel_path: str, line_num: int, new_content: str) -> None:
    """Replace a single line in a file (1-indexed)."""
    _assert_body_lines(rel_path, line_num)
    wiki_dir = get_wiki_dir()
    file_path = confined_path(wiki_dir, rel_path)
    lines = file_path.read_text(encoding="utf-8").splitlines()

    if line_num < 1 or line_num > len(lines):
        raise IndexError(f"Line {line_num} out of range (1-{len(lines)})")

    lines[line_num - 1] = new_content
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def edit_lines(rel_path: str, start: int, end: int, new_content: str) -> None:
    """Replace a range of lines (1-indexed, inclusive)."""
    for n in range(start, end + 1):
        _assert_body_lines(rel_path, n)
    wiki_dir = get_wiki_dir()
    file_path = confined_path(wiki_dir, rel_path)
    lines = file_path.read_text(encoding="utf-8").splitlines()

    if start < 1 or end > len(lines) or start > end:
        raise IndexError(f"Lines {start}-{end} out of range (1-{len(lines)})")

    replacement = new_content.splitlines()
    lines[start - 1 : end] = replacement
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def insert_after(rel_path: str, line_num: int, new_content: str) -> None:
    """Insert content after a specific line (1-indexed)."""
    lines = read_file_lines(rel_path)
    fm = frontmatter_line_range(lines)
    # Allow insert after the closing --- (body start); block inserts inside FM.
    if fm is not None:
        start, end = fm
        if line_num < end:
            raise ValueError(
                f"Cannot insert inside frontmatter (lines {start}-{end}). "
                f"Use --after {end} to insert at the start of the body, "
                "or use 'ohkb meta' for metadata changes."
            )

    wiki_dir = get_wiki_dir()
    file_path = confined_path(wiki_dir, rel_path)
    lines = file_path.read_text(encoding="utf-8").splitlines()

    if line_num < 0 or line_num > len(lines):
        raise IndexError(f"Line {line_num} out of range (0-{len(lines)})")

    new_lines = new_content.splitlines()
    lines[line_num:line_num] = new_lines
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def delete_line(rel_path: str, line_num: int) -> None:
    """Delete a single line (1-indexed)."""
    _assert_body_lines(rel_path, line_num)
    wiki_dir = get_wiki_dir()
    file_path = confined_path(wiki_dir, rel_path)
    lines = file_path.read_text(encoding="utf-8").splitlines()

    if line_num < 1 or line_num > len(lines):
        raise IndexError(f"Line {line_num} out of range (1-{len(lines)})")

    del lines[line_num - 1]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cleanup_empty_dirs(start: Path, stop: Path) -> None:
    """Remove empty directories from start up to (but not including) stop."""
    parent = start
    while parent != stop:
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
            else:
                break
        except FileNotFoundError:
            break


def write_entry_relocating(entry: Entry, old_path: str) -> str:
    """Write entry to its canonical path, removing old_path if it differs.

    Returns the new relative path (entry.filename).
    Raises FileExistsError if the target path already exists as a different file.
    """
    wiki_dir = get_wiki_dir()
    old_file = confined_path(wiki_dir, old_path)
    new_path = entry.filename
    new_file = confined_path(wiki_dir, new_path)

    if not old_file.exists():
        raise FileNotFoundError(f"Entry not found: {old_path}")

    same_path = old_file.resolve() == new_file.resolve()
    if same_path:
        new_file.write_text(entry.to_markdown(), encoding="utf-8")
        return new_path

    if new_file.exists():
        raise FileExistsError(
            f"Cannot rename to {new_path}: target already exists. "
            "Forget or rename the existing entry first."
        )

    new_file.parent.mkdir(parents=True, exist_ok=True)
    new_file.write_text(entry.to_markdown(), encoding="utf-8")
    old_file.unlink()
    _cleanup_empty_dirs(old_file.parent, wiki_dir)
    return new_path


def archive_entry(rel_path: str, reason: str = "") -> Path:
    """Move an entry to the archive directory.

    If an archive for the same path already exists, the new archive is stored
    with a timestamp suffix so previous versions are preserved::

        archive/cat/entry.md
        archive/cat/entry__20260407T120000123456Z.md

    Returns the absolute path of the archived file.
    """
    wiki_dir = get_wiki_dir()
    archive_dir = get_archive_dir()

    src = confined_path(wiki_dir, rel_path)
    if not src.exists():
        raise FileNotFoundError(f"Entry not found: {rel_path}")

    dst = confined_path(archive_dir, rel_path)
    if dst.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        p = Path(rel_path)
        versioned = p.with_name(f"{p.stem}__{ts}{p.suffix}")
        dst = confined_path(archive_dir, versioned)

    dst.parent.mkdir(parents=True, exist_ok=True)

    text = src.read_text(encoding="utf-8")
    ts_iso = datetime.now(timezone.utc).isoformat()
    safe_reason = " ".join(reason.split()).replace("--", "-")[:500]
    safe_reason = re.sub(r"(?i)\boriginal\s*:", "original-", safe_reason)
    archive_note = f"\n\n<!-- archived: {ts_iso} reason: {safe_reason} original: {rel_path} -->\n"
    dst.write_text(text + archive_note, encoding="utf-8")
    src.unlink()
    _cleanup_empty_dirs(src.parent, wiki_dir)

    return dst


def list_archives(original_path: str | None = None) -> list[dict]:
    """List archived files.

    Args:
        original_path: If set, only archives for this original wiki path.

    Returns list of dicts: path (archive-relative), original, mtime.
    """
    archive_dir = get_archive_dir()
    results: list[dict] = []

    for md_file in sorted(archive_dir.rglob("*.md")):
        if md_file.is_symlink():
            continue
        rel = md_file.relative_to(archive_dir).as_posix()
        try:
            md_file = confined_path(archive_dir, rel)
        except ValueError:
            continue
        original = _infer_original_path(rel, md_file)
        if original_path is not None and original != original_path:
            continue
        results.append(
            {
                "path": rel,
                "original": original,
                "mtime": md_file.stat().st_mtime,
            }
        )

    results.sort(key=lambda r: r["mtime"], reverse=True)
    return results


def _infer_original_path(archive_rel: str, file_path: Path | None = None) -> str:
    """Infer the original wiki path from an archive relative path or file footer."""
    if file_path is not None and file_path.exists():
        text = file_path.read_text(encoding="utf-8")
        m = re.search(
            r"<!-- archived:.*\soriginal:\s*([^\s>]+)\s*-->\s*$",
            text,
            flags=re.DOTALL,
        )
        if m:
            return m.group(1).strip()

    # Fallback: strip versioning suffix entry__TIMESTAMP.md → entry.md
    p = Path(archive_rel)
    stem = p.stem
    if "__" in stem:
        base_stem = stem.rsplit("__", 1)[0]
        # Only strip if the suffix looks like a timestamp
        suffix = stem.rsplit("__", 1)[1]
        if re.fullmatch(r"\d{8}T\d{6,}\d*Z?", suffix):
            return str(p.with_name(base_stem + p.suffix)).replace("\\", "/")
    return archive_rel


def restore_entry(
    original_path: str | None = None,
    *,
    archive_path: str | None = None,
    overwrite: bool = False,
) -> tuple[str, str]:
    """Restore an archived entry back into the wiki.

    Provide either ``original_path`` (restores the most recent archive for that
    path) or ``archive_path`` (specific archive-relative file).

    Returns:
        (restored_wiki_path, used_archive_path)

    Raises:
        FileNotFoundError: no matching archive.
        FileExistsError: wiki target exists and overwrite is False.
    """
    archive_dir = get_archive_dir()
    wiki_dir = get_wiki_dir()

    if archive_path:
        src = confined_path(archive_dir, archive_path)
        if not src.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")
        used_archive = archive_path
        original = _infer_original_path(archive_path, src)
    elif original_path:
        matches = list_archives(original_path)
        if not matches:
            raise FileNotFoundError(f"No archive found for: {original_path}")
        used_archive = matches[0]["path"]
        src = confined_path(archive_dir, used_archive)
        original = original_path
    else:
        raise ValueError("Specify original_path or archive_path.")

    text = src.read_text(encoding="utf-8")
    # Strip trailing archive footer comments
    text = re.sub(r"\n\n<!-- archived:.*?-->\n?\s*$", "\n", text, flags=re.DOTALL)
    if not text.endswith("\n"):
        text += "\n"

    dst = confined_path(wiki_dir, original)
    if dst.exists() and not overwrite:
        raise FileExistsError(f"Entry already exists: {original}. Use --overwrite to replace.")

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    src.unlink()
    _cleanup_empty_dirs(src.parent, archive_dir)

    return original, used_archive


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
    wiki_dir = (wiki_dir or get_wiki_dir()).resolve()
    if depth < 1 or depth > 20:
        raise ValueError("Depth must be between 1 and 20.")
    root = confined_path(wiki_dir, path) if path else wiki_dir

    if not root.exists():
        raise FileNotFoundError(f"Path not found in wiki: {path!r}")
    if not root.is_dir():
        raise ValueError(f"Tree path is not a directory: {path!r}")

    def _expand(directory: Path, remaining: int) -> dict:
        node: dict = {}
        try:
            children = sorted(directory.iterdir())
        except PermissionError:
            return node

        for child in children:
            if child.name.startswith("_") or child.is_symlink():
                continue
            try:
                confined_path(wiki_dir, child.relative_to(wiki_dir))
            except ValueError:
                continue
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


def touch_updated(rel_path: str) -> None:
    """Update the `updated` timestamp in the frontmatter of a file.

    Called after line-level edits (edit_line, edit_lines, insert_after,
    delete_line) so the frontmatter stays in sync with the actual content.
    """
    wiki_dir = get_wiki_dir()
    file_path = confined_path(wiki_dir, rel_path)
    text = file_path.read_text(encoding="utf-8")
    now_iso = datetime.now(timezone.utc).isoformat()
    # Replace the `updated:` line in the YAML frontmatter block only.
    # The frontmatter is between the first two `---` lines.
    updated_text = re.sub(
        r"(?m)^(updated:\s*)(.+)$",
        lambda m: m.group(1) + now_iso,
        text,
        count=1,
    )
    file_path.write_text(updated_text, encoding="utf-8")


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

    If category or title changes the on-disk path, the file is relocated and
    the old path is removed. Returns the updated entry.
    """
    entry = read_entry(rel_path)

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
    if category is not None:
        entry.category = category

    entry.updated = datetime.now(timezone.utc)
    write_entry_relocating(entry, rel_path)
    return entry


def iter_wiki_entries() -> list[str]:
    """Return sorted relative paths of all knowledge entry files in the wiki."""
    wiki_dir = get_wiki_dir()
    paths: list[str] = []
    for md_file in wiki_dir.rglob("*.md"):
        if md_file.is_symlink():
            continue
        rel = md_file.relative_to(wiki_dir).as_posix()
        if rel.startswith("_") or any(part.startswith("_") for part in Path(rel).parts):
            continue
        try:
            confined_path(wiki_dir, rel)
        except ValueError:
            continue
        paths.append(rel)
    return sorted(paths)
