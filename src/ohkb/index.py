"""Automatic _index.md generation for the knowledge base.

The _index.md file lives at the root of the wiki directory and provides
a structured summary of the entire knowledge base. MCP clients read this
first to understand what knowledge is available before making targeted queries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ohkb.config import get_wiki_dir
from ohkb.models import Entry
from ohkb.pathutil import confined_path

# Filename for the index (underscore prefix = internal, skipped by tree/lint)
INDEX_FILENAME = "_index.md"


def generate_index_content(wiki_dir: Path | None = None) -> str:
    """Generate the full text content of _index.md from current wiki state.

    Scans all Markdown files, groups them by category, and produces a
    human/LLM-readable summary with entry titles, tags, and char counts.
    """
    wiki_dir = (wiki_dir or get_wiki_dir()).resolve()

    # Collect category -> [rel_paths] without following or indexing symlinks.
    categories: dict[str, list[str]] = {}
    for md_file in sorted(wiki_dir.rglob("*.md")):
        if md_file.is_symlink():
            continue
        rel = md_file.relative_to(wiki_dir)
        if any(part.startswith("_") for part in rel.parts):
            continue
        try:
            confined_path(wiki_dir, rel)
        except ValueError:
            continue
        category = rel.parent.as_posix()
        rel_str = rel.as_posix()
        categories.setdefault(category, []).append(rel_str)

    for cat in categories:
        categories[cat] = sorted(categories[cat])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_entries = sum(len(files) for files in categories.values())
    total_categories = len(categories)

    lines: list[str] = [
        "# Knowledge Base Index",
        "",
        f"Last updated: {now}",
        f"Total: {total_entries} entries across {total_categories} categories",
        "",
    ]

    if not categories:
        lines.append("*Knowledge base is empty.*")
        return "\n".join(lines) + "\n"

    lines.append("## Categories")
    lines.append("")

    for category, files in categories.items():
        lines.append(f"### {category} ({len(files)} entries)")
        lines.append("")

        for rel_path in files:
            file_path = confined_path(wiki_dir, rel_path)
            if not file_path.exists():
                continue

            text = file_path.read_text(encoding="utf-8")
            chars = len(text)

            # Try to extract metadata for a richer summary
            try:
                entry = Entry.from_markdown(text, category=category)
                tags_str = ", ".join(entry.tags) if entry.tags else "none"
                lines.append(
                    f"- **{entry.title}** (`{rel_path}`, {chars} chars) -- tags: {tags_str}"
                )
            except Exception:
                # Fallback: just show filename and size
                lines.append(f"- `{rel_path}` ({chars} chars)")

        lines.append("")

    return "\n".join(lines) + "\n"


def refresh_index(wiki_dir: Path | None = None) -> Path:
    """Regenerate _index.md and write it to disk.

    Returns the absolute path to the written _index.md file.
    """
    wiki_dir = wiki_dir or get_wiki_dir()
    content = generate_index_content(wiki_dir)
    index_path = confined_path(wiki_dir, INDEX_FILENAME)
    index_path.write_text(content, encoding="utf-8")
    return index_path


def read_index(wiki_dir: Path | None = None) -> str:
    """Read the current _index.md content.

    If the file does not exist, generates it first.
    """
    wiki_dir = wiki_dir or get_wiki_dir()
    index_path = confined_path(wiki_dir, INDEX_FILENAME)

    if not index_path.exists():
        refresh_index(wiki_dir)

    return index_path.read_text(encoding="utf-8")
