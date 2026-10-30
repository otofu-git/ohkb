# MCP Tools Reference

Korean: [MCP_TOOLS_kr.md](MCP_TOOLS_kr.md)

Full tool/resource/prompt surface of `ohkb serve`. Implementation: `src/ohkb/serve.py`.

## Modes

```
ohkb serve                    # autonomous (default)
ohkb serve --mode readonly
ohkb serve --mode managed
ohkb serve --mode autonomous
```

| Mode | Read tools | Write tools |
|------|------------|-------------|
| `readonly` | yes | no (except reindex / extract as non-mutating*) |
| `managed` | yes | yes (prompt asks for confirmation) |
| `autonomous` | yes | yes (immediate) |

\* `reindex`, `extract`, `log`, `related`, `source_list` are available in readonly.
`source_add` is a write.

## Resource

### `ohkb://index`

KB structure summary (Markdown). Read this first. Auto-refreshed after writes.

## Read tools

### `search`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | yes | Question or keywords; any word can match, ranked by BM25 |
| `category` | string | no | Category prefix filter |
| `limit` | int | no | Max results (default 20) |

Returns JSON array with `path`, `title`, `tags`, `score` (relative 0..1), etc.

### `get`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | e.g. `category/file.md` |

Returns numbered lines + char/line counts.

### `index`

No params. Returns `_index.md` body. **Call first each session.**

### `tree`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | no | Zoom into category |
| `depth` | int | no | Expand depth (default 2) |

### `status`

Counts, `in_sync`, categories, data dir. If `in_sync` is false → `reindex`.

### `lint`

Issues: unindexed, missing_file, oversized, missing_tags/aliases, invalid_frontmatter, category_mismatch, slug_mismatch, empty_category.

### `reindex`

Rebuild FTS from disk. Files are source of truth.

### `log`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `limit` | int | no | Recent lines (default 50) |

### `related`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Entry path |
| `limit` | int | no | Max neighbors |

Shared-tag related entries (no embeddings).

### `extract`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `target` | string | yes | Local file path |

Returns plain text for the agent to classify and `learn`. **Does not call an LLM or access the network.**

### `source_list`

List immutable raw sources under `sources/`.

## Write tools (managed / autonomous)

### `learn`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | yes | Body (&lt; 3000 chars recommended) |
| `title` | string | yes | Title |
| `category` | string | yes | Nested path OK |
| `tags` / `aliases` | string | no | Comma-separated |
| `entity_type` / `source` | string | no | Defaults: concept / manual |
| `overwrite` | bool | no | Default false |

Always `search` first for duplicates.

### `edit`

Exactly one of: `line`, `line_start`+`line_end`, `after`, `delete`.
Frontmatter lines cannot be edited — use `meta`.

### `meta`

Tags/aliases/title/category/entity_type. Title/category may relocate the file.

### `forget`

Soft-delete to `archive/` (versioned on collision). Use `restore` to bring back.

### `restore`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | no | Original wiki path (latest archive) |
| `archive_path` | string | no | Specific archive file |
| `overwrite` | bool | no | Default false |

### `source_add`

Copy a local file into immutable `sources/`.

## Prompts

- **research(topic)** — index → search → get → synthesize
- **learn_from_text(text)** — extract atomic facts → search → learn
- **organize(category?)** — lint → fix tags → split oversized → report
