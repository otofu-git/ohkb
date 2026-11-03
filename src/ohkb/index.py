"""Knowledge base index: the `_index.md` file and the bounded overview agents read.

Both are built from the search index (`_meta.db`) instead of re-reading every Markdown
file, so they take milliseconds even with thousands of entries.

- `_index.md` lives at the root of the wiki directory. It lists every entry and is written
  on demand (`ohkb index`, `refresh_index()`). Mutating commands delete it
  (`invalidate_index()`) rather than rewriting it, so it is never stale and a write does not
  cost time proportional to the size of the knowledge base.
- `generate_overview()` is what the MCP `index` tool and the `ohkb://index` resource return.
  It is the full listing when that fits in `OVERVIEW_MAX_CHARS`; otherwise categories with
  entry counts and common tags. Agent hosts cap tool results (Claude Code at about 25k
  tokens), and a full listing of a few thousand entries is several hundred thousand
  characters.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ohkb.config import get_wiki_dir
from ohkb.pathutil import confined_path

if TYPE_CHECKING:  # kb → bootstrap → index: import KnowledgeBase lazily at runtime
    from ohkb.kb import KnowledgeBase

# Filename for the index (underscore prefix = internal, skipped by tree/lint)
INDEX_FILENAME = "_index.md"

# Character budget for what the MCP `index` tool and resource return.
OVERVIEW_MAX_CHARS = 12_000

# Common tags shown per category in the overview.
_OVERVIEW_TAGS = 5


def _catalog(kb: KnowledgeBase | None) -> list[dict]:
    if kb is not None:
        return kb.catalog()
    from ohkb.kb import KnowledgeBase

    own = KnowledgeBase()
    try:
        return own.catalog()
    finally:
        own.close()


def _in_category(entry_category: str, category: str) -> bool:
    """Prefix match, as in search: 'python' includes 'python/internals'."""
    return entry_category == category or entry_category.startswith(category + "/")


def _label(category: str) -> str:
    return category or "(root)"


def _entry_line(row: dict) -> str:
    tags = ", ".join(row["tags"]) if row["tags"] else "none"
    return f"- **{row['title']}** (`{row['path']}`, {row['chars']} chars) -- tags: {tags}"


def _listing(rows: list[dict], heading: str) -> list[str]:
    """Full listing lines: every entry grouped by category."""
    by_category: dict[str, list[dict]] = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(row)
    lines = [
        f"# {heading}",
        "",
        f"Total: {len(rows)} entries across {len(by_category)} categories",
        "",
    ]
    if not rows:
        lines.append("*Knowledge base is empty.*")
        return lines
    lines += ["## Categories", ""]
    for category, entries in by_category.items():
        lines += [f"### {_label(category)} ({len(entries)} entries)", ""]
        lines += [_entry_line(row) for row in entries]
        lines.append("")
    return lines


def generate_index_content(
    wiki_dir: Path | None = None,
    *,
    kb: KnowledgeBase | None = None,
    category: str | None = None,
) -> str:
    """Full `_index.md` text: every indexed entry grouped by category.

    Built from the search index, so files written outside ohkb appear after `ohkb reindex`.
    `category` limits the listing to that category and its sub-categories. `wiki_dir` is
    accepted for compatibility; the listing does not read files.
    """
    rows = _catalog(kb)
    if category:
        rows = [row for row in rows if _in_category(row["category"], category)]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = _listing(rows, "Knowledge Base Index")
    lines.insert(2, f"Last updated: {now}")
    if category:
        lines.insert(3, f"Category: {category}")
    return "\n".join(lines) + "\n"


def generate_overview(
    *,
    kb: KnowledgeBase | None = None,
    category: str | None = None,
    max_chars: int = OVERVIEW_MAX_CHARS,
) -> str:
    """What an agent gets from `index`: the full listing if it fits, else a bounded summary.

    Without `category`, the summary lists categories with entry counts and common tags,
    largest first. With `category`, it lists the entries in that category until the budget
    is used. Either way the result stays within about `max_chars` characters.
    """
    rows = _catalog(kb)
    if category:
        rows = [row for row in rows if _in_category(row["category"], category)]
        if not rows:
            return f"No entries in category '{category}'. Use 'search' to find entries.\n"

    heading = f"Knowledge Base Index — {category}" if category else "Knowledge Base Index"
    full = "\n".join(_listing(rows, heading)) + "\n"
    if len(full) <= max_chars:
        return full

    if category:
        lines = [
            f"# {heading}",
            "",
            f"{len(rows)} entries — too many to list in full. "
            "Use 'search' to find specific entries.",
            "",
        ]
        size = sum(len(line) + 1 for line in lines)
        for shown, row in enumerate(rows):
            line = _entry_line(row)
            if size + len(line) + 1 > max_chars - 80:
                lines.append(f"- … and {len(rows) - shown} more entries")
                break
            lines.append(line)
            size += len(line) + 1
        return "\n".join(lines) + "\n"

    groups: dict[str, list] = {}
    for row in rows:
        group = groups.setdefault(row["category"], [0, Counter()])
        group[0] += 1
        group[1].update(row["tags"])
    lines = [
        "# Knowledge Base Overview",
        "",
        f"Total: {len(rows)} entries across {len(groups)} categories.",
        f"The full list is too long to show ({len(full):,} characters). Find entries with "
        "'search' and read them with 'get'; pass a category to 'index' to list its entries.",
        "",
        "## Categories (entries — common tags), largest first",
        "",
    ]
    size = sum(len(line) + 1 for line in lines)
    ordered = sorted(groups.items(), key=lambda item: (-item[1][0], item[0]))
    for shown, (name, (count, tags)) in enumerate(ordered):
        common = ", ".join(tag for tag, _ in tags.most_common(_OVERVIEW_TAGS)) or "none"
        line = f"- {_label(name)} — {count} — {common}"
        if size + len(line) + 1 > max_chars - 80:
            lines.append(f"- … and {len(ordered) - shown} more categories")
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines) + "\n"


def refresh_index(wiki_dir: Path | None = None, *, kb: KnowledgeBase | None = None) -> Path:
    """Regenerate _index.md and write it to disk.

    Returns the absolute path to the written _index.md file.
    """
    wiki_dir = wiki_dir or get_wiki_dir()
    content = generate_index_content(wiki_dir, kb=kb)
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


def invalidate_index(wiki_dir: Path | None = None) -> None:
    """Delete _index.md after a write so it is rebuilt on next read instead of going stale.

    A symlinked _index.md is left alone (managed paths never follow symlinks).
    """
    wiki_dir = wiki_dir or get_wiki_dir()
    try:
        index_path = confined_path(wiki_dir, INDEX_FILENAME)
    except ValueError:
        return
    index_path.unlink(missing_ok=True)
