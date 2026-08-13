# ohkb — Development Guide for Coding Agents

Korean: [AGENTS_kr.md](AGENTS_kr.md)

> **ohkb** — simple local knowledge base for agents.
> No embeddings. No vector DB. **ohkb never calls models.**
> Markdown files + SQLite FTS5. Version **0.1.0**.

This file is the source of truth for agents working **in this repository**.

---

## Product position

| ohkb is | ohkb is not |
|---------|-------------|
| Agent-native memory **tools** (CLI + MCP) | An embedding / vector RAG stack |
| Any model, any agent host | Tied to one IDE or one chat product |
| Dual-write FS + FTS substrate | A system that invokes LLMs |
| Atomic facts with tags/aliases | A general note-taking app |

**One-liner for users:** tools an agent uses to *remember* — not a model that writes a wiki for you.

**Design principle:** files under `wiki/` are source of truth. SQLite is a rebuildable index (`ohkb reindex`).

---

## Stack & layout

| Item | Value |
|------|--------|
| Python | 3.10+ |
| CLI | Click |
| Search | SQLite FTS5 + `bm25()` |
| MCP (optional) | `ohkb[serve]` |
| Build | hatchling, `src/ohkb/` |
| Lint | ruff (line length 100) |
| Tests | pytest, real FS + SQLite, no mocks |

```
src/ohkb/
  cli.py          # Click presentation
  serve.py        # MCP presentation
  kb.py           # KnowledgeBase — only dual-write coordinator
  wiki.py         # Markdown filesystem
  store.py        # SQLite FTS5 + schema migrations
  models.py       # Entry dataclass
  config.py       # OHKB_DIR / paths
  index.py        # Auto _index.md
tests/
  test_kb.py test_basic.py test_index.py test_lifecycle.py test_serve.py
```

---

## Build, test, lint

```bash
uv sync --extra dev
uv run ohkb --version          # 0.1.0
pytest
ruff check src/ tests/
ruff format src/ tests/
```

```bash
pip install -e ".[dev]"
```

Test rules: `OHKB_DIR` via autouse `tmp_path`; no mocking FS/SQLite; classes by feature (`TestLearn`, …).

---

## Architecture (do not skip layers)

```
cli.py / serve.py     Presentation
        ↓
      kb.py           Service — dual-write orchestration
        ↓
wiki.py + store.py    Data
        ↓
models.py + config.py Foundation
```

1. Filesystem write first (`wiki.py`)
2. Then FTS update (`store.py`)
3. Presentation may `refresh_index()` for `_index.md`

Never call `wiki`/`store` from presentation without `KnowledgeBase`.

---

## CLI (0.1.0)

| Command | Role |
|---------|------|
| `search` | BM25 (`-c`, `--limit`, `--json`) |
| `get` | Read + line numbers |
| `tree` | Structure (`path`, `--depth`) |
| `status` | Counts + `in_sync` |
| `lint` | Health / drift / quality |
| `index` / `reindex` | Summary / rebuild FTS from disk |
| `learn` / `edit` / `meta` | Create / line edit / metadata |
| `forget` / `restore` | Archive (versioned) / restore |
| `init` | Scaffold data dir + agent schema |
| `source add/list` | Immutable local-file intake |
| `extract` | Local file text extract (no LLM, no network) |
| `log` / `related` | Activity log / shared-tag neighbors |
| `serve` | MCP server (local stdio only) |

Exit `0` on success; `--json` stdout is always valid JSON.

---

## MCP (0.1.0)

| Mode | Tools |
|------|--------|
| `readonly` | index, search, get, tree, status, lint, reindex, log, related, extract, source_list |
| `managed` | + learn, edit, meta, forget, restore, source_add (confirm first) |
| `autonomous` | write immediately |

Resource: `ohkb://index`. Prompts: `research`, `learn_from_text`, `organize`.
`search(limit)`, `tree(path, depth)` match CLI.

---

## Search

```python
_BM25_WEIGHTS = (10.0, 5.0, 3.0, 1.0)  # title, tags, aliases, content
```

- Tokens FTS5-escaped, AND + prefix `*`; OR fallback if empty (capped).
- Relative `score` in 0..1.
- Category filter is **prefix** (`python` ⊇ `python/internals`).
- Prefer 3–7 tags and real aliases on every `learn`.

---

## Categories & invariants

Nested categories are first-class (`python/internals/gil.md`).

| Invariant | Behavior |
|-----------|----------|
| Title/category change | Relocates file; deletes old path; no orphans |
| Rename collision | `FileExistsError` |
| `edit` | Cannot touch frontmatter lines → use `meta` |
| Re-forget same path | Timestamped archive version |
| Disk ≠ index | `status.in_sync == false` → `reindex` |
| `lint` | unindexed, missing_file, category_mismatch, slug_mismatch, … |

---

## Data directory

```
~/.ohkb/                 # OHKB_DIR
  _meta.db
  wiki/   _index.md , <category>/<slug>.md
  sources/               # optional immutable raw intake
  archive/
  log.md
  AGENTS.ohkb.md         # from ohkb init
```

`SCHEMA_VERSION` + `_MIGRATIONS` in `store.py`. Newer DB on older ohkb → `RuntimeError`.

---

## Code style

1. `from __future__ import annotations` first in every module.
2. Imports: future → stdlib → third-party → `ohkb.*`.
3. `str | None`, `list[str]`, `*` for kw-only; line length 100; double quotes.
4. No custom exception types — stdlib only.
5. Service raises; CLI → stderr + `SystemExit(1)`; MCP propagates.

---

## When changing code

**Do**

- Business logic in `kb.py`; thin `cli`/`serve`.
- Mutation = FS → index → (optional) `_index.md` refresh.
- Tests in `test_kb` + CLI coverage in `test_basic`.
- Keep MCP params aligned with CLI.

**Do not**

- Call models from ohkb.
- Add embeddings to the core path without an explicit product decision.
- Leave orphan files after path-changing ops.
- Expand into roadmap features without a request.

**Out of scope for 0.1.0 core**

- Structured `ohkb db` tables
- Document/URL ingest pipelines that own compilation
- Auto-merge / split / staleness agents
- Web UI as the primary contract

Web is documentation-only; no Web/HTTP runtime ships. See `docs/WEB_UI.md`.

See `docs/ROADMAP.md`.

---

## Agent usage (product)

```bash
ohkb init
ohkb search "keyword" --json
ohkb learn "fact" -t "Title" -c cat --tags "t1,t2" --aliases "a1"
ohkb get "cat/title.md" --json
ohkb edit "cat/title.md" --line N "body"
ohkb meta "cat/title.md" --add-tags "verified"
ohkb related "cat/title.md"
ohkb source add ./raw.txt
ohkb extract ./raw.txt
ohkb status --json
ohkb reindex
ohkb log
ohkb forget "cat/title.md" --reason "..."
ohkb restore "cat/title.md"
```

MCP: call `index` first each session → `search` → `get`.
Raw intake: `source_add` → `extract` → you classify → `learn`.
