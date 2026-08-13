# Roadmap

Korean: [ROADMAP_kr.md](ROADMAP_kr.md)

ohkb versioning starts at **0.1.0**.

**Positioning:** simple local knowledge base for agents.
ohkb does not call models. Files are truth; FTS5 is a rebuildable index.

---

## 0.1.0 — Core (current)

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
| **0.2.x** | First major additive (likely `db`) |
| **1.0** | Stable CLI/MCP contract |

Keep `pyproject.toml` version and `ohkb.__version__` identical.
