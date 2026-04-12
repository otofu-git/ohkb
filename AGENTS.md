# orag — Development Guide for Coding Agents

## Project Overview

orag is a knowledge base for LLM agents. No embeddings, no vector DB — just
Markdown files + SQLite FTS5. Distributed as a Python CLI via `uv`/`pip`.

**Stack**: Python 3.10+, Click (CLI), PyYAML, SQLite FTS5, MCP SDK (optional).
**Layout**: src-layout (`src/orag/`), hatchling build system.

## Build & Run

```bash
pip install -e ".[dev]"       # Install with dev dependencies
pip install -e ".[serve]"     # Install with MCP server support
orag --version                # Verify installation
```

## Test Commands

```bash
pytest                        # Run all tests (56 tests)
pytest tests/test_kb.py       # Run one file
pytest tests/test_kb.py::TestLearn                        # Run one class
pytest tests/test_kb.py::TestLearn::test_learn_creates_entry  # Run one test
pytest -v                     # Verbose output
pytest -x                     # Stop on first failure
```

All tests use real filesystem (tmp_path) and real SQLite. No mocking.

## Lint

```bash
ruff check src/ tests/        # Lint
ruff check --fix src/ tests/  # Lint with auto-fix
ruff format src/ tests/       # Format (100 char line length)
```

Rules enabled: `E` (pycodestyle), `F` (pyflakes), `I` (isort), `UP` (pyupgrade),
`B` (bugbear), `SIM` (simplify). Config in `pyproject.toml`.

## Architecture

Layered design — never skip a layer:

```
cli.py / serve.py     Presentation (Click CLI / MCP server)
       ↓
     kb.py             Service layer (KnowledgeBase — orchestrates dual writes)
       ↓
wiki.py + store.py     Data layer (filesystem + SQLite FTS5)
       ↓
models.py + config.py  Foundation (Entry dataclass + path config)
```

**Dual-write rule**: Every mutation writes filesystem first (wiki.py), then
updates FTS5 index (store.py). `KnowledgeBase` in kb.py is the single coordinator.
CLI and MCP server both call into kb.py — never call wiki.py + store.py directly
from presentation layer.

## Code Style

### Imports

Every file starts with `from __future__ import annotations`. No exceptions.

Order (enforced by ruff isort):
1. `__future__`
2. Standard library (alphabetized)
3. Third-party (alphabetized)
4. Local `orag.*` (alphabetized)

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import click

from orag.kb import KnowledgeBase
from orag.models import Entry
from orag.store import Store
```

Long imports use parenthesized multi-line style:
```python
from orag.wiki import (
    archive_entry,
    build_tree,
    edit_line,
    save_entry,
)
```

Optional dependencies use lazy import with `ImportError` guard in cli.py.

### Type Annotations & Formatting

All function parameters and return types annotated. Use `str | None` (not
`Optional`), lowercase generics (`list[str]`, `dict[str, Any]`), `*` separator
for keyword-only args. Line length 100, double quotes, f-strings only, trailing
commas in multi-line constructs. Section dividers: `# ── Name ────────` style.

```python
def search(self, query: str, category: str | None = None, limit: int = 20) -> list[dict]:
def edit(self, path: str, *, line: int | None = None, delete: int | None = None) -> dict:
```

### Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Modules | short lowercase | `kb.py`, `wiki.py`, `serve.py` |
| Classes | PascalCase | `KnowledgeBase`, `Store`, `Entry` |
| Functions | snake_case | `save_entry`, `build_tree` |
| Private | `_` prefix | `_parse_dt`, `_init_schema`, `self._conn` |
| Constants | UPPER_SNAKE | `MAX_ENTRY_CHARS`, `SCHEMA_VERSION` |
| Type aliases | Simple assign | `Mode = str` |

### Docstrings

Module-level docstring required in every file. Imperative mood.

```python
"""Store a new knowledge entry.

Writes the Markdown file, then indexes it in FTS5.

Returns:
    {"path": "category/slug.md", "status": "created", "chars": 123}

Raises:
    FileExistsError: if entry exists and overwrite is False.
    ValueError: if content is empty.
"""
```

### Error Handling

**No custom exception classes.** Use only stdlib exceptions:
- `ValueError` — bad input, invalid args
- `FileExistsError` — duplicate entry
- `FileNotFoundError` — missing file
- `IndexError` — line number out of range

**Service layer** (kb.py, wiki.py): raise exceptions, let them propagate.
**CLI layer** (cli.py): catch, print to stderr, exit with code 1:
```python
except FileExistsError as e:
    click.echo(f"Error: {e}", err=True)
    raise SystemExit(1)
```
**MCP layer** (serve.py): let exceptions propagate — the SDK returns `isError=True`.

## Test Patterns

Fixture: every test file uses `autouse=True` tmp dir via `ORAG_DIR` env var:
```python
@pytest.fixture(autouse=True)
def tmp_orag_dir(tmp_path):
    os.environ["ORAG_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["ORAG_DIR"]
```

Tests grouped in classes by feature: `TestLearn`, `TestSearch`, `TestEdit`, etc.
Test names: `test_<action>_<expected_behavior>`.
Use `pytest.raises` for expected exceptions.
No mocking — real filesystem and real SQLite for every test.

## Key Files

| File | Purpose |
|------|---------|
| `src/orag/kb.py` | KnowledgeBase class — all business logic lives here |
| `src/orag/serve.py` | MCP server — 3 modes (readonly/managed/autonomous) |
| `src/orag/cli.py` | Click CLI — thin wrapper around KnowledgeBase |
| `src/orag/wiki.py` | Filesystem ops — read/write/edit Markdown files |
| `src/orag/store.py` | SQLite FTS5 — search index with BM25 ranking |
| `src/orag/models.py` | Entry dataclass with Markdown serialization |
| `src/orag/index.py` | Auto-generated _index.md (KB summary) |
| `src/orag/config.py` | Path resolution (ORAG_DIR env var override) |

## Data Directory

```
~/.orag/                    # Default (override with ORAG_DIR)
  _meta.db                  # SQLite: FTS5 index + metadata
  wiki/
    _index.md               # Auto-generated KB summary
    python/
      free-threaded-python.md
    _tables/                # (future) auto-generated DB table docs
  archive/                  # Forgotten (archived) files
```
