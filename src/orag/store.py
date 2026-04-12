"""SQLite FTS5 store for search indexing and metadata."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from orag.config import get_db_path
from orag.models import Entry

# BM25 column weights for entries_fts(title, tags, aliases, content).
# Higher weight = matches in that column rank higher.
# title matches are the strongest signal; raw body content the weakest.
_BM25_WEIGHTS = (10.0, 5.0, 3.0, 1.0)

# Schema version for future migrations
SCHEMA_VERSION = 1

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS entries (
    path        TEXT PRIMARY KEY,   -- category/slug.md
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '',  -- comma-separated
    aliases     TEXT NOT NULL DEFAULT '',  -- comma-separated
    entity_type TEXT NOT NULL DEFAULT 'concept',
    source      TEXT NOT NULL DEFAULT 'manual',
    created     TEXT NOT NULL,
    updated     TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title, tags, aliases, content,
    content=entries,
    content_rowid=rowid
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, title, tags, aliases, content)
    VALUES (new.rowid, new.title, new.tags, new.aliases, new.content);
END;

CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, tags, aliases, content)
    VALUES ('delete', old.rowid, old.title, old.tags, old.aliases, old.content);
END;

CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, tags, aliases, content)
    VALUES ('delete', old.rowid, old.title, old.tags, old.aliases, old.content);
    INSERT INTO entries_fts(rowid, title, tags, aliases, content)
    VALUES (new.rowid, new.title, new.tags, new.aliases, new.content);
END;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""


class Store:
    """SQLite-backed store with FTS5 search."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_db_path()
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        self.conn.executescript(_CREATE_TABLES)
        # Set schema version if not set
        row = self.conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            self.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            self.conn.commit()

    def upsert(self, entry: Entry) -> None:
        """Insert or replace an entry in the index."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO entries
                (path, title, category, tags, aliases, entity_type, source, created, updated, content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.filename,
                entry.title,
                entry.category,
                ",".join(entry.tags),
                ",".join(entry.aliases),
                entry.entity_type,
                entry.source,
                entry.created.isoformat(),
                entry.updated.isoformat(),
                entry.content,
            ),
        )
        self.conn.commit()

    def delete(self, path: str) -> None:
        """Remove an entry from the index."""
        self.conn.execute("DELETE FROM entries WHERE path = ?", (path,))
        self.conn.commit()

    @staticmethod
    def _fts5_escape(query: str) -> str:
        """Escape a raw query string for safe use in FTS5 MATCH.

        FTS5 parses its query syntax before SQLite parameter binding takes
        effect, so special characters like +, -, (, ), ", * cause parse errors
        even when passed as bound parameters.  Wrapping the whole query in
        double-quotes turns it into a phrase search and neutralises all
        special characters.  Internal double-quote characters are escaped by
        doubling them per the FTS5 spec.

        Examples (input => fts5 query):
            C++          =>  "C++"
            (test)       =>  "(test)"
            python*      =>  "python*"   (loses prefix semantics, gains safety)
        """
        return '"' + query.replace('"', '""') + '"'

    def search(self, query: str, category: str | None = None, limit: int = 20) -> list[dict]:
        """Full-text search using FTS5 BM25 ranking.

        The query is automatically escaped so special characters (C++, (test),
        quotes, etc.) never cause a parse error.
        """
        safe_query = self._fts5_escape(query)
        w = _BM25_WEIGHTS
        bm25_expr = f"bm25(entries_fts, {w[0]}, {w[1]}, {w[2]}, {w[3]})"
        if category:
            rows = self.conn.execute(
                f"""
                SELECT e.path, e.title, e.category, e.tags, e.aliases,
                       e.entity_type, {bm25_expr} AS rank
                FROM entries_fts fts
                JOIN entries e ON e.rowid = fts.rowid
                WHERE entries_fts MATCH ? AND e.category = ?
                ORDER BY {bm25_expr}
                LIMIT ?
                """,
                (safe_query, category, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"""
                SELECT e.path, e.title, e.category, e.tags, e.aliases,
                       e.entity_type, {bm25_expr} AS rank
                FROM entries_fts fts
                JOIN entries e ON e.rowid = fts.rowid
                WHERE entries_fts MATCH ?
                ORDER BY {bm25_expr}
                LIMIT ?
                """,
                (safe_query, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def get(self, path: str) -> dict | None:
        """Get a single entry by path."""
        row = self.conn.execute("SELECT * FROM entries WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        """List all entries."""
        rows = self.conn.execute(
            "SELECT path, title, category, tags, aliases, entity_type FROM entries ORDER BY category, title"
        ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict:
        """Return basic statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        categories = self.conn.execute("SELECT DISTINCT category FROM entries ORDER BY category").fetchall()
        return {
            "total_entries": total,
            "categories": [row[0] for row in categories],
        }

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
