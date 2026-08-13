"""SQLite FTS5 store for search indexing and metadata."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from ohkb.config import get_db_path
from ohkb.models import Entry

# BM25 column weights for entries_fts(title, tags, aliases, content).
# Higher weight = matches in that column rank higher.
# title matches are the strongest signal; raw body content the weakest.
_BM25_WEIGHTS = (10.0, 5.0, 3.0, 1.0)

# Schema version — bump when migrations are added below.
SCHEMA_VERSION = 1

# Migrations keyed by *target* version (applied when upgrading from N-1 → N).
# Each callable receives an open sqlite3.Connection and must not commit.
_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    # Example:
    # 2: lambda conn: conn.execute("ALTER TABLE entries ADD COLUMN foo TEXT"),
}

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
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Create tables if needed and apply pending migrations."""
        self.conn.executescript(_CREATE_TABLES)
        row = self.conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            self.conn.commit()
            return

        current = int(row[0])
        if current > SCHEMA_VERSION:
            # Newer DB opened by older code — refuse to write silently.
            raise RuntimeError(
                f"Database schema version {current} is newer than this ohkb "
                f"supports ({SCHEMA_VERSION}). Upgrade ohkb to continue."
            )
        if current < SCHEMA_VERSION:
            self._migrate(current)

    def _migrate(self, from_version: int) -> None:
        """Apply migrations from from_version up to SCHEMA_VERSION."""
        for target in range(from_version + 1, SCHEMA_VERSION + 1):
            migrate_fn = _MIGRATIONS.get(target)
            if migrate_fn is not None:
                migrate_fn(self.conn)
            self.conn.execute("UPDATE schema_version SET version = ?", (target,))
        self.conn.commit()

    def upsert(self, entry: Entry) -> None:
        """Insert or replace an entry in the index at entry.filename."""
        self.upsert_at_path(entry, entry.filename)

    def upsert_at_path(self, entry: Entry, path: str) -> None:
        """Insert or replace an entry at an explicit index path.

        Used by reindex when the on-disk filename may not match the title slug.
        """
        self.conn.execute(
            """
            INSERT OR REPLACE INTO entries
                (path, title, category, tags, aliases, entity_type, source, created, updated,
                 content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path,
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

    def clear_all(self) -> None:
        """Remove every row from the index (used by reindex)."""
        self.conn.execute("DELETE FROM entries")
        self.conn.commit()

    def indexed_paths(self) -> set[str]:
        """Return the set of all paths currently in the index."""
        rows = self.conn.execute("SELECT path FROM entries").fetchall()
        return {row[0] for row in rows}

    @staticmethod
    def _fts5_escape(query: str) -> str:
        """Escape a raw query string for safe use in FTS5 MATCH.

        FTS5 parses its query syntax before SQLite parameter binding takes
        effect, so special characters like +, -, (, ), ", * cause parse errors
        even when passed as bound parameters.

        Each whitespace-separated token is wrapped in double-quotes (making it
        a safe literal term) and the tokens are joined with AND so that all
        words must appear somewhere in the document — but not necessarily
        adjacent or in order.  This matches user intent for multi-word queries
        like "뷰저블 요금 가격" or "free threaded python".

        A single-token query becomes a plain quoted term.

        Internal double-quote characters are escaped by doubling them per the
        FTS5 spec.

        Examples (input => fts5 query):
            pricing              =>  "pricing"*
            뷰저블 요금 가격        =>  "뷰저블"* AND "요금"* AND "가격"*
            C++                  =>  "C++"*
            free threaded python =>  "free"* AND "threaded"* AND "python"*

        The prefix wildcard (*) is important for CJK languages: SQLite's default
        unicode61 tokenizer does not split compound words, so "요금" alone would
        not match "요금제".  With prefix matching, "요금"* matches any token that
        starts with "요금", including "요금제", "요금표", etc.
        """
        tokens = query.split()
        if not tokens:
            return '""'
        # Each token is wrapped in double-quotes for safety, then given a
        # trailing * for prefix matching.  This handles languages like Korean
        # where the default unicode61 tokenizer does not split compound words
        # (e.g. "요금" prefix-matches "요금제", "요금표", etc.).
        escaped = ['"' + t.replace('"', '""') + '"*' for t in tokens]
        return " AND ".join(escaped)

    @staticmethod
    def _fts5_or(query: str) -> str:
        """Build an OR query: any token matches (used as fallback)."""
        tokens = query.split()
        if not tokens:
            return '""'
        escaped = ['"' + t.replace('"', '""') + '"*' for t in tokens]
        return " OR ".join(escaped)

    def search(self, query: str, category: str | None = None, limit: int = 20) -> list[dict]:
        """Full-text search using FTS5 BM25 ranking.

        First tries AND (all tokens must match). If no results, falls back to
        OR (any token matches) so broad queries like 'beusable pricing 가격'
        still find relevant entries even when no single document contains every word.
        """
        safe_query = self._fts5_escape(query)
        w = _BM25_WEIGHTS
        bm25_expr = f"bm25(entries_fts, {w[0]}, {w[1]}, {w[2]}, {w[3]})"

        def _run(fts_query: str) -> list:
            if category:
                category_prefix = (
                    category.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
                )
                return self.conn.execute(
                    f"""
                    SELECT e.path, e.title, e.category, e.tags, e.aliases,
                           e.entity_type, {bm25_expr} AS rank
                    FROM entries_fts fts
                    JOIN entries e ON e.rowid = fts.rowid
                    WHERE entries_fts MATCH ?
                      AND (e.category = ? OR e.category LIKE ? ESCAPE '\\')
                    ORDER BY {bm25_expr}
                    LIMIT ?
                    """,
                    (fts_query, category, category_prefix, limit),
                ).fetchall()
            else:
                return self.conn.execute(
                    f"""
                    SELECT e.path, e.title, e.category, e.tags, e.aliases,
                           e.entity_type, {bm25_expr} AS rank
                    FROM entries_fts fts
                    JOIN entries e ON e.rowid = fts.rowid
                    WHERE entries_fts MATCH ?
                    ORDER BY {bm25_expr}
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()

        rows = _run(safe_query)

        # AND returned nothing → fall back to OR so broad queries like
        # "beusable pricing 가격" still surface relevant entries even when
        # no single document contains every token.
        # Returns (rows, or_fallback) so callers can apply stricter filtering.
        if not rows and " AND " in safe_query:
            rows = _run(self._fts5_or(query))
            return [dict(row) for row in rows], True

        return [dict(row) for row in rows], False

    def get(self, path: str) -> dict | None:
        """Get a single entry by path."""
        row = self.conn.execute("SELECT * FROM entries WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        """List all entries."""
        rows = self.conn.execute(
            "SELECT path, title, category, tags, aliases, entity_type"
            " FROM entries ORDER BY category, title"
        ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict:
        """Return basic statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        categories = self.conn.execute(
            "SELECT DISTINCT category FROM entries ORDER BY category"
        ).fetchall()
        return {
            "total_entries": total,
            "categories": [row[0] for row in categories],
        }

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
