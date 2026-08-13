# ohkb

**A simple, local knowledge base for agents.**

ohkb gives an agent a stable set of tools for storing, finding, updating, and retiring knowledge across sessions. Entries are ordinary Markdown files. Search is provided by a local SQLite FTS5 index that can be rebuilt at any time.

ohkb does not call language models, create embeddings, or require a vector database. The agent decides what is worth keeping; ohkb keeps it organized and searchable.

[한국어](README_kr.md) · [Architecture](docs/ARCHITECTURE.md) · [MCP reference](docs/MCP_TOOLS.md) · [Roadmap](docs/ROADMAP.md)

## At a glance

| | |
|---|---|
| **Storage** | Markdown files with YAML frontmatter |
| **Search** | SQLite FTS5 with BM25 ranking |
| **Interfaces** | CLI and local MCP server |
| **Model usage** | None |
| **Network access** | None in core commands |
| **Data location** | `~/.ohkb`, configurable with `OHKB_DIR` |
| **Python** | 3.10+ |

## Why ohkb

Agents often need a small amount of durable, curated knowledge: project conventions, decisions, facts discovered during research, or details that should survive beyond one conversation.

A general note-taking application does not provide a predictable tool contract for agents. A full RAG stack may add ingestion pipelines, chunking, embeddings, and external services when all that is needed is reliable local memory. ohkb stays between those two extremes:

- the agent chooses what to learn and how to classify it;
- each entry remains readable and editable without ohkb;
- tags and aliases provide explicit search signals;
- the search database is an index, not the source of truth;
- the same operations are available through the CLI and MCP.

The result is intentionally small: tools an agent can use to remember, rather than a system that decides or writes knowledge on the agent's behalf.

## Installation

Install the CLI with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install ohkb
```

Or with pip:

```bash
pip install ohkb
```

The MCP server is an optional extra:

```bash
uv tool install "ohkb[serve]"
# or
pip install "ohkb[serve]"
```

Check the installation:

```bash
ohkb --version
```

## Quick start

Initialize the data directory:

```bash
ohkb init
```

Store an entry:

```bash
ohkb learn "Python 3.13 can be built without the GIL using --disable-gil." \
  --title "Free-threaded Python" \
  --category python \
  --tags "GIL,CPython,free-threading,PEP-703" \
  --aliases "nogil,no-GIL Python,GIL removal"
```

Search and read it:

```bash
ohkb search "GIL"
ohkb get "python/free-threaded-python.md"
```

Browse the knowledge base and check its state:

```bash
ohkb tree
ohkb status
ohkb lint
```

Most commands support `--json`, which is the recommended output format when an agent or script is calling the CLI:

```bash
ohkb search "GIL" --json
ohkb get "python/free-threaded-python.md" --json
ohkb status --json
```

## Recommended agent workflow

A reliable session usually follows the same sequence:

1. Run `ohkb index` to see the current structure.
2. Search before creating anything.
3. Read exact paths returned by search.
4. Add or update one focused fact at a time.
5. Use `ohkb status` or `ohkb lint` to detect drift.

```bash
ohkb index
ohkb search "deployment rollback" --json
ohkb get "operations/deployment-rollback.md" --json
ohkb learn "..." -t "..." -c operations --tags "..." --aliases "..." --json
```

`search` before `learn` is important. It keeps the knowledge base compact and avoids creating several entries for the same fact.

## Knowledge entries

Each entry is stored under `wiki/<category>/<slug>.md`. A title such as `Free-threaded Python` in category `python` becomes:

```text
wiki/python/free-threaded-python.md
```

The file is standard Markdown with YAML frontmatter:

```markdown
---
title: Free-threaded Python
category: python
tags:
- GIL
- CPython
- free-threading
- PEP-703
aliases:
- nogil
- no-GIL Python
entity_type: concept
source: manual
created: '2026-08-13T04:00:00+00:00'
updated: '2026-08-13T04:00:00+00:00'
---

Python 3.13 can be built without the GIL using --disable-gil.
```

One focused fact per file works best. Entries shorter than roughly 3,000 characters are recommended; `ohkb lint` reports oversized entries.

### Categories

Categories may be nested:

```bash
ohkb learn "..." \
  --title "CPython garbage collection" \
  --category "python/internals" \
  --tags "CPython,GC,memory"
```

This creates `python/internals/cpython-garbage-collection.md`. Filtering by a parent category includes its descendants:

```bash
ohkb search "garbage collection" --category python
```

### Tags and aliases

Tags and aliases are part of the retrieval model, not decorative metadata.

- **Tags** connect entries that share concepts and power `ohkb related`.
- **Aliases** capture alternate names, abbreviations, and terms users are likely to search for.

Three to seven useful tags and a few genuine aliases are usually enough. Avoid adding broad terms that do not help distinguish the entry.

## Search

Search uses SQLite FTS5 and BM25. Fields are weighted in this order:

```text
title > tags > aliases > content
```

Search terms use prefix matching and are combined strictly first, with a bounded broader fallback when necessary. Results include a relative score from `0` to `1`; the score is meaningful within that result set rather than as a global relevance value.

```bash
ohkb search "python gil"
ohkb search "gil" --category python --limit 5
ohkb search "free threading" --json
```

No embeddings are generated. Search quality comes from concise entries, descriptive titles, and metadata selected when the entry is written.

## Reading and editing

`get` returns the entry with line numbers so an agent can make a precise edit:

```bash
ohkb get "python/free-threaded-python.md"
```

Use one edit operation at a time:

```bash
# Replace one body line
ohkb edit "python/free-threaded-python.md" --line <line-number> "New text"

# Replace a range
ohkb edit "python/free-threaded-python.md" --lines 20-22 "Replacement text"

# Insert or delete
ohkb edit "python/free-threaded-python.md" --after 20 "Additional detail"
ohkb edit "python/free-threaded-python.md" --delete 21
```

Frontmatter cannot be changed with `edit`. Use `meta` instead:

```bash
ohkb meta "python/free-threaded-python.md" --add-tags "verified,python-3.13"
ohkb meta "python/free-threaded-python.md" --add-aliases "free-threaded CPython"
ohkb meta "python/free-threaded-python.md" --title "Free-threaded CPython"
ohkb meta "python/free-threaded-cpython.md" --category "python/runtime"
```

Changing the title or category relocates the file and removes the previous path. A conflicting destination is rejected rather than overwritten.

## Archiving and restoring

`forget` is a reversible archive operation:

```bash
ohkb forget "python/free-threaded-python.md" --reason "Superseded by a newer entry"
```

Restore the most recent archive for that path:

```bash
ohkb restore "python/free-threaded-python.md"
```

List available archives or restore a specific version:

```bash
ohkb restore --list
ohkb restore "python/free-threaded-python.md" --list
ohkb restore --archive "python/free-threaded-python__20260813T120000000000Z.md"
```

If the same path is archived more than once, ohkb keeps timestamped versions instead of replacing the previous archive.

## Working with local source files

The optional `sources/` directory keeps copies of raw local material separately from curated knowledge:

```bash
ohkb source add ./research-notes.txt
ohkb source list
```

`extract` returns text from a local text or HTML file so an agent can review, classify, and store useful facts:

```bash
ohkb extract ./research-notes.txt --json
```

A typical intake flow is:

```text
source add → extract → review and classify → search for duplicates → learn
```

Extraction is local and deterministic. It does not summarize content, call a model, or fetch URLs. Binary formats such as PDF, DOCX, images, and ZIP files must be converted to text first. Individual extraction targets are limited to 10 MiB; copied source files are limited to 100 MiB.

## Files are the source of truth

ohkb writes the Markdown file first and then updates SQLite. The database can always be reconstructed from `wiki/`:

```bash
ohkb reindex
```

This matters when entries are edited with another tool or restored from version control. `status` reports whether the files and index agree:

```bash
ohkb status --json
```

If `in_sync` is `false`, run `ohkb reindex`. `lint` provides a more detailed health check and can report:

- files missing from the index;
- indexed paths with no file on disk;
- invalid frontmatter;
- missing tags or aliases;
- category and filename mismatches;
- oversized entries.

## MCP server

Install the `serve` extra, then configure an MCP client to start ohkb over stdio:

```json
{
  "mcpServers": {
    "ohkb": {
      "command": "ohkb",
      "args": ["serve", "--mode", "managed"]
    }
  }
}
```

The executable must be available in the MCP client's environment. The server is local stdio only; ohkb does not expose an HTTP transport.

### Access modes

| Mode | Behavior |
|------|----------|
| `readonly` | Read, search, inspect, extract, and rebuild the local index |
| `managed` | Adds write tools and asks the client for confirmation before changes |
| `autonomous` | Makes write tools available without confirmation prompts |

```bash
ohkb serve --mode readonly
ohkb serve --mode managed
ohkb serve --mode autonomous
```

Available MCP features include:

- resource: `ohkb://index`;
- prompts: `research`, `learn_from_text`, and `organize`;
- read tools: `index`, `search`, `get`, `tree`, `status`, `lint`, `reindex`, `log`, `related`, `extract`, `source_list`;
- write tools: `learn`, `edit`, `meta`, `forget`, `restore`, `source_add`.

See [docs/MCP_TOOLS.md](docs/MCP_TOOLS.md) for parameters and return values.

## Data directory

By default, all state is stored under `~/.ohkb`:

```text
~/.ohkb/
├── _meta.db           # SQLite metadata and FTS5 index
├── wiki/
│   ├── _index.md      # generated summary
│   └── <category>/
│       └── <slug>.md  # knowledge entries
├── sources/           # optional raw local files
├── archive/           # versioned forgotten entries
├── log.md             # append-only activity log
└── AGENTS.ohkb.md     # generated agent workflow guide
```

Use `OHKB_DIR` to keep separate knowledge bases or place the data elsewhere:

```bash
export OHKB_DIR="$PWD/.ohkb"
ohkb init
```

The directory is portable. It can be backed up, searched with standard tools, or placed under version control according to your own data policy. `_meta.db` does not need to be preserved if the Markdown files are available.

## CLI reference

| Command | Purpose |
|---------|---------|
| `ohkb index` | Show the generated knowledge summary |
| `ohkb search QUERY` | Search with optional category and result limit |
| `ohkb get PATH` | Read an entry with line numbers |
| `ohkb tree [PATH]` | Browse categories to a chosen depth |
| `ohkb status` | Show counts, categories, and index sync state |
| `ohkb lint` | Check metadata quality and file/index integrity |
| `ohkb related PATH` | Find entries that share tags |
| `ohkb log` | Show recent activity |
| `ohkb learn [CONTENT]` | Create an entry; content may also come from `--file` |
| `ohkb edit PATH` | Replace, insert, or delete body lines |
| `ohkb meta PATH` | Update tags, aliases, title, category, or entity type |
| `ohkb forget PATH` | Move an entry to the versioned archive |
| `ohkb restore [PATH]` | List or restore archived entries |
| `ohkb reindex` | Rebuild SQLite from Markdown files |
| `ohkb source add/list` | Manage optional raw local sources |
| `ohkb extract TARGET` | Extract text from a local text or HTML file |
| `ohkb init` | Create the standard data layout and agent guide |
| `ohkb serve` | Start the optional local MCP server |

Run `ohkb COMMAND --help` for complete options. Successful commands exit with status `0`; errors are written to stderr. Commands that offer `--json` keep stdout machine-readable.

## Scope

ohkb is deliberately limited. The core project does not include:

- model invocation or autonomous knowledge generation;
- embeddings or vector search;
- URL crawling and document ingestion pipelines;
- automatic merging, splitting, or staleness decisions;
- a web or HTTP runtime.

Those boundaries keep the storage format understandable and the tool contract predictable. Planned work is tracked in the [roadmap](docs/ROADMAP.md).

## Development

Clone the repository and install the development environment:

```bash
git clone https://github.com/otofu-git/ohkb.git
cd ohkb
uv sync --extra dev
```

Run the checks:

```bash
uv run pytest
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv build
```

The test suite uses real temporary filesystems and SQLite databases rather than mocks. See [AGENTS.md](AGENTS.md) for the architecture, invariants, and contribution guidelines used in this repository.

## Version

Current release: **0.1.0**

See [docs/ROADMAP.md](docs/ROADMAP.md) for planned work and compatibility milestones.

## License

[MIT](LICENSE)
