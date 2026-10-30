# Architecture

Korean: [ARCHITECTURE_kr.md](ARCHITECTURE_kr.md)

## Overview

ohkb uses a four-layer design. CLI and MCP call only `KnowledgeBase` — never skip layers.

```
┌─────────────────────────────────────────────────────────┐
│                    LLM agent                            │
│           Claude / GPT / Llama / Gemini / ...           │
└──────────────────┬──────────────────────────────────────┘
                   │ MCP (local stdio) or CLI
         ┌─────────┴─────────┐
         ▼                   ▼
┌──────────────┐    ┌──────────────────┐
│  CLI (cli.py)│    │ MCP Server       │
│  Click       │    │ (serve.py)       │
└──────┬───────┘    └────────┬─────────┘
       │                     │
       └──────────┬──────────┘
                  ▼
     ┌────────────────────────┐
     │  KnowledgeBase (kb.py) │  ← single service entry
     │  search / get / tree   │
     │  learn / edit / meta   │
     │  forget / restore      │
     │  reindex / status/lint │
     │  init / sources / log  │
     │  extract / related     │
     └────────┬───────────────┘
              │
    ┌─────────┴──────────┐
    ▼                    ▼
┌──────────┐    ┌────────────────┐
│ wiki.py  │    │  store.py      │
│ Markdown │    │  SQLite FTS5   │
│ FS ops   │    │  BM25 search   │
└──────────┘    └────────────────┘
    ▲                    ▲
    └─────────┬──────────┘
              ▼
  ┌───────────────────────┐
  │ models.py + config.py │
  │ Entry + OHKB_DIR      │
  └───────────────────────┘
```

## Layer roles

### 1. Presentation (`cli.py` / `serve.py`)

**Rule:** call only `KnowledgeBase`. Do not call `wiki.py` / `store.py` directly.

- CLI: catch errors → stderr + `SystemExit(1)`; support `--json`
- MCP: three modes; exceptions propagate as tool errors
- After mutations: refresh `_index.md` where applicable

### 2. Service (`kb.py`)

**Rule:** every mutation writes the filesystem first, then updates FTS5.

| Method | Description |
|--------|-------------|
| `search` | BM25 full-text search |
| `get` | Read with line numbers / char count |
| `tree` | Structure browse |
| `status` | Counts + `in_sync` |
| `lint` | Health + drift |
| `reindex` | Rebuild FTS from disk |
| `learn` / `edit` / `meta` | Create / line edit / metadata |
| `forget` / `restore` | Archive / restore |
| `init` | Scaffold data dir |
| `source_add` / `source_list` | Immutable raw intake |
| `log` | Activity log |
| `extract` | Local file text extract (no LLM, no network) |
| `related` | Shared-tag neighbors |

### 3. Data (`wiki.py` + `store.py`)

- **wiki:** save/read/edit/archive/restore/relocate, tree, sources helpers
- **store:** entries + search-token columns, FTS5 triggers, BM25, schema version + migrations

### 4. Foundation (`models.py` + `config.py`)

- `Entry` dataclass + Markdown (de)serialization
- Paths: `OHKB_DIR` → wiki, archive, sources, db, log

## Dual-write

```python
save_entry(entry, overwrite=...)  # filesystem first
self._store.upsert(entry)         # then FTS
```

## Search

```python
_BM25_WEIGHTS = (10.0, 5.0, 3.0, 1.0)  # title, tags, aliases, content
```

`search_tokens()` turns Hangul/Kana/Han runs into character bigrams and keeps other words
whole. The tokens live in `title_tokens`, `tags_tokens`, `aliases_tokens`, and `content_tokens`,
which `entries_fts` indexes. A query matches if any of its tokens matches (OR) and is ranked by
weighted `bm25()`.

Callers see a relative `score` in 0..1. Category filter uses prefix match.

## Nested categories

| Operation | Nested path support |
|-----------|---------------------|
| learn | `mkdir -p` |
| tree | `depth` |
| search -c | prefix LIKE |
| meta title/category | relocate + delete old path |
| read_entry / reindex | category from full parent path |

## Data layout

```
~/.ohkb/
  _meta.db
  wiki/
    _index.md
    <category>/<slug>.md
  sources/
  archive/
  log.md
  AGENTS.ohkb.md
```

## Index generation (`index.py`)

`_index.md` is regenerated after mutations (CLI/MCP). Agents should read `ohkb://index` or `ohkb index` first.
