"""Scaffold an ohkb data directory (init)."""

from __future__ import annotations

from ohkb.config import (
    get_agent_schema_path,
    get_archive_dir,
    get_data_dir,
    get_log_path,
    get_sources_dir,
    get_wiki_dir,
)
from ohkb.index import refresh_index
from ohkb.logutil import append_log

_AGENT_SCHEMA = """# ohkb agent schema

You are using **ohkb**, a simple local knowledge base for agents.
ohkb never calls models. You call ohkb tools; you decide what to store.

## Workflow

1. `index` or `ohkb index` — see categories and entries
2. `search` before `learn` — avoid duplicates
3. `get` exact paths from search results
4. Keep entries atomic (< 3000 chars). Provide 3–7 tags and useful aliases.
5. Use `meta` for frontmatter; never edit frontmatter with line `edit`
6. If `status.in_sync` is false → `reindex`
7. Optional: `source add` raw material → `extract` text → you classify → `learn`

## Tools (mental model)

| Intent | Tool |
|--------|------|
| Overview | index / tree / status |
| Find | search |
| Read | get |
| Create | learn |
| Patch body | edit |
| Tags/title/category | meta |
| Soft-delete | forget |
| Undo delete | restore |
| Raw intake | source add / source list |
| Text from local file | extract |
| Neighbors | related |
| Audit | log / lint |

## Data layout

```
$OHKB_DIR/
  wiki/       # truth — atomic Markdown entries
  sources/    # immutable raw intake (optional)
  archive/    # soft-deleted
  _meta.db    # FTS5 index
  log.md      # activity
```
"""


def init_ohkb(*, force: bool = False) -> dict:
    """Create standard directories and agent schema file.

    Returns a summary dict of created paths.
    """
    data = get_data_dir()
    wiki = get_wiki_dir()
    sources = get_sources_dir()
    archive = get_archive_dir()
    log_path = get_log_path()
    schema_path = get_agent_schema_path()

    created: list[str] = []

    for p in (data, wiki, sources, archive):
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(str(p))

    if not log_path.exists() or force:
        log_path.write_text("# ohkb activity log\n\n", encoding="utf-8")
        created.append(str(log_path))

    if not schema_path.exists() or force:
        schema_path.write_text(_AGENT_SCHEMA, encoding="utf-8")
        created.append(str(schema_path))

    refresh_index(wiki)
    append_log("init", str(data))

    return {
        "status": "ok",
        "data_dir": str(data),
        "wiki": str(wiki),
        "sources": str(sources),
        "archive": str(archive),
        "log": str(log_path),
        "agent_schema": str(schema_path),
        "created": created,
    }
