# Roadmap

Korean: [ROADMAP_kr.md](ROADMAP_kr.md)

ohkb versioning starts at **0.1.0**.

**Positioning:** simple local knowledge base for agents.
ohkb does not call models. Files are truth; FTS5 is a rebuildable index.

---

## 0.2.1 — Index overview (current)

| Area | Contents |
|------|----------|
| Index | MCP `index` / `ohkb://index`: full listing up to 12,000 characters, otherwise categories with entry counts and common tags; `index(category)`, `ohkb index -c` |
| Speed | `_index.md` built from SQLite; not rebuilt at server start or after each write (deleted, rebuilt on read) |
| Agent guidance | No mandatory `index` call: search → get the entries you rely on → answer; say when entries disagree and prefer the most recently updated |

## 0.2.0 — Search tokens

| Area | Contents |
|------|----------|
| Search | Hangul/Kana/Han character bigrams + whole words; OR query ranked by weighted BM25 (no AND, prefix, or 5-result fallback cap) |
| Index | Search-token columns (schema 2); 0.1.0 databases migrate on first open; updates no longer leave stale index rows |

## 0.1.0 — Core

| Area | Contents |
|------|----------|
| CLI | learn, search, get, edit, meta, forget, restore, tree, status, lint, reindex, index, serve |
| Lifecycle | init, source add/list, log, extract, related |
| Search | FTS5 BM25, category prefix, limit |
| Integrity | dual-write, relocate, archive versioning, reindex, lint drift |
| MCP | readonly / managed / autonomous |
| Contract | no embeddings, no model calls, local-first |

### Deferred

- Structured multi-table `ohkb db`
- Heavy compile pipelines
- Automated merge/split/staleness
- Web UI as primary product surface

---

## Backlog

### 1. `ohkb db` — structured tables

Agent-owned SQLite tables (block system tables).

### 2. Knowledge hygiene signals

Near-duplicate hints, stale-by-`updated`, richer related graph (still no model calls).

### 3. Human-facing interface concept

Documentation-only exploration. No Web or HTTP runtime is shipped. Any implementation requires a separate product and security decision; see [WEB_UI.md](WEB_UI.md).

---

## Versioning

| Line | Meaning |
|------|---------|
| **0.1.x** | Core KB + MCP + lifecycle helpers |
| **0.2.x** | Search tokens (schema 2) |
| **0.3.x** | First major additive (likely `db`) |
| **1.0** | Stable CLI/MCP contract |

Keep `pyproject.toml` version and `ohkb.__version__` identical.
