"""SQLite FTS5 store for search indexing and metadata."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path

from ohkb.config import get_db_path
from ohkb.models import Entry

# BM25 column weights for entries_fts(title, tags, aliases, content).
# Higher weight = matches in that column rank higher.
# title matches are the strongest signal; raw body content the weakest.
_BM25_WEIGHTS = (10.0, 5.0, 3.0, 1.0)

# ── Search tokens ───────────────────────────────────────────────────────────
#
# SQLite's unicode61 tokenizer keeps a Korean word together with its particles
# and endings ("요금제를", "요금제는"), so a query word rarely equals an indexed
# token.  ohkb therefore indexes its own tokens:
#
#   - Hangul, Kana and Han runs become overlapping character bigrams
#     ("중소기업" → 중소 소기 기업); a one-character run stays a unigram.
#   - Numbers stay whole, including inner "." and "," ("1,000", "3.5").
#   - Other letters (Latin, Cyrillic, Greek, ...) form lowercased whole words.
#
# Everything else separates tokens, including Hangul jamo used as bullets or
# separators (ㅇ, ㆍ) and number-like symbols (①, Ⅱ, ²).  The tokens are stored
# space-separated in the *_tokens columns, and FTS5 indexes those columns with
# its default unicode61 tokenizer.

_HANGUL = "\uac00-\ud7a3"  # Hangul syllables 가-힣
_CJK = (
    "\u3041-\u3096\u309d-\u309f"  # Hiragana
    "\u30a1-\u30fa\u30fc-\u30ff\u31f0-\u31ff\uff66-\uff9d"  # Katakana (full and half width)
    "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f"  # Han ideographs
)
_NOT_WORD = (
    "\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\ud7b0-\ud7ff\uffa0-\uffdc"  # Hangul jamo
    "\u3040-\u30ff\u31f0-\u31ff\uff65-\uff9f"  # rest of the Kana blocks
    "\u00b2\u00b3\u00b9\u00bc-\u00be\u2070-\u209f\u2150-\u218f"  # super/subscripts, Roman numerals
    "\u2460-\u24ff\u2776-\u2793\u3220-\u325f\u3280-\u32bf"  # circled and parenthesized numbers
)
_TOKEN_RE = re.compile(
    rf"(?P<bigram>[{_HANGUL}]+|[{_CJK}]+)"
    r"|(?P<number>\d+(?:[.,]\d+)*)"
    rf"|(?P<word>[^\W\d_{_HANGUL}{_CJK}{_NOT_WORD}]+)"
)


def search_tokens(text: str) -> list[str]:
    """Split text into the tokens that ohkb indexes and matches queries against.

    Examples:
        "중소기업 지원"   → ["중소", "소기", "기업", "지원"]
        "AI 바우처 3.5억" → ["ai", "바우", "우처", "3.5", "억"]
    """
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(unicodedata.normalize("NFC", text)):
        run = match.group()
        if match.lastgroup == "bigram":
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        else:
            tokens.append(run.lower())
    return tokens


def _token_text(parts: Iterable[str]) -> str:
    """Search tokens of several strings, space-separated for the FTS5 column."""
    return " ".join(token for part in parts for token in search_tokens(part))


def _index_columns(
    title: str, tags: Iterable[str], aliases: Iterable[str], content: str
) -> tuple[str, str, str, str]:
    """Values for (title_tokens, tags_tokens, aliases_tokens, content_tokens)."""
    return _token_text([title]), _token_text(tags), _token_text(aliases), _token_text([content])


# ── Schema ──────────────────────────────────────────────────────────────────

# Schema version — bump when migrations are added below.
SCHEMA_VERSION = 2

_CREATE_ENTRIES = """
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
    content     TEXT NOT NULL DEFAULT '',
    -- search_tokens() of the fields above; entries_fts indexes these columns
    title_tokens   TEXT NOT NULL DEFAULT '',
    tags_tokens    TEXT NOT NULL DEFAULT '',
    aliases_tokens TEXT NOT NULL DEFAULT '',
    content_tokens TEXT NOT NULL DEFAULT ''
)
"""

_TOKEN_COLUMNS = ("title_tokens", "tags_tokens", "aliases_tokens", "content_tokens")

# The trigger names match 0.1.0's, so 0.1.0's CREATE TRIGGER IF NOT EXISTS is a
# no-op on a migrated database before it refuses the newer schema version.
_CREATE_FTS = (
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
        title_tokens, tags_tokens, aliases_tokens, content_tokens,
        content=entries,
        content_rowid=rowid
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
        INSERT INTO entries_fts(rowid, title_tokens, tags_tokens, aliases_tokens, content_tokens)
        VALUES (new.rowid, new.title_tokens, new.tags_tokens, new.aliases_tokens,
                new.content_tokens);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
        INSERT INTO entries_fts(entries_fts, rowid, title_tokens, tags_tokens, aliases_tokens,
                                content_tokens)
        VALUES ('delete', old.rowid, old.title_tokens, old.tags_tokens, old.aliases_tokens,
                old.content_tokens);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
        INSERT INTO entries_fts(entries_fts, rowid, title_tokens, tags_tokens, aliases_tokens,
                                content_tokens)
        VALUES ('delete', old.rowid, old.title_tokens, old.tags_tokens, old.aliases_tokens,
                old.content_tokens);
        INSERT INTO entries_fts(rowid, title_tokens, tags_tokens, aliases_tokens, content_tokens)
        VALUES (new.rowid, new.title_tokens, new.tags_tokens, new.aliases_tokens,
                new.content_tokens);
    END
    """,
)

_CREATE_SCHEMA_VERSION = "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"


def _migrate_to_search_tokens(conn: sqlite3.Connection) -> None:
    """Schema 2: index search_tokens() columns instead of raw text.

    Schema 1 indexed the raw fields with unicode61 and matched AND-ed prefix
    queries.  The index is rebuilt from the entries table, which also drops
    rows that schema 1 left behind when INSERT OR REPLACE skipped its delete
    trigger.
    """
    for trigger in ("entries_ai", "entries_ad", "entries_au"):
        conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    conn.execute("DROP TABLE IF EXISTS entries_fts")
    existing = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
    for column in _TOKEN_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE entries ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    rows = conn.execute("SELECT rowid, title, tags, aliases, content FROM entries").fetchall()
    conn.executemany(
        "UPDATE entries SET title_tokens = ?, tags_tokens = ?, aliases_tokens = ?,"
        " content_tokens = ? WHERE rowid = ?",
        [
            (*_index_columns(title, tags.split(","), aliases.split(","), content), rowid)
            for rowid, title, tags, aliases, content in rows
        ],
    )
    for statement in _CREATE_FTS:
        conn.execute(statement)
    conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")


# Migrations keyed by *target* version (applied when upgrading from N-1 → N).
# Each callable receives an open sqlite3.Connection and must not commit.
_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_to_search_tokens,
}


class Store:
    """SQLite-backed store with FTS5 search."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_db_path()
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._conn = conn
            try:
                self._init_schema()
            except BaseException:
                # Do not keep a connection whose schema was not checked or migrated.
                self._conn = None
                conn.close()
                raise
        return self._conn

    def _schema_version(self) -> int | None:
        """Stored schema version; None for a database without one."""
        try:
            row = self.conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                return None
            raise
        return int(row[0]) if row else None

    @staticmethod
    def _check_not_newer(version: int | None) -> None:
        if version is not None and version > SCHEMA_VERSION:
            # Newer DB opened by older code — refuse to write silently.
            raise RuntimeError(
                f"Database schema version {version} is newer than this ohkb "
                f"supports ({SCHEMA_VERSION}). Upgrade ohkb to continue."
            )

    def _init_schema(self) -> None:
        """Create tables if needed and apply pending migrations.

        Schema changes run in one IMMEDIATE transaction. Processes that open
        the same database at the same time wait for the first one and then
        find the work done.
        """
        version = self._schema_version()
        self._check_not_newer(version)
        if version == SCHEMA_VERSION:
            return
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            version = self._schema_version()
            self._check_not_newer(version)
            if version is None:
                has_entries = self.conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'entries'"
                ).fetchone()
                # A database that has entries but no version predates versioning: schema 1.
                version = 1 if has_entries else 0
            if version == 0:
                for statement in (_CREATE_ENTRIES, *_CREATE_FTS, _CREATE_SCHEMA_VERSION):
                    self.conn.execute(statement)
            elif version < SCHEMA_VERSION:
                self.conn.execute(_CREATE_SCHEMA_VERSION)
                self._migrate(version)
            self.conn.execute("DELETE FROM schema_version")
            self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    def _migrate(self, from_version: int) -> None:
        """Apply migrations from from_version up to SCHEMA_VERSION (caller commits)."""
        for target in range(from_version + 1, SCHEMA_VERSION + 1):
            migrate_fn = _MIGRATIONS.get(target)
            if migrate_fn is not None:
                migrate_fn(self.conn)

    def upsert(self, entry: Entry) -> None:
        """Insert or replace an entry in the index at entry.filename."""
        self.upsert_at_path(entry, entry.filename)

    def upsert_at_path(self, entry: Entry, path: str) -> None:
        """Insert or replace an entry at an explicit index path.

        Used by reindex when the on-disk filename may not match the title slug.
        Replacing is DELETE + INSERT so the delete trigger removes the old
        index row (INSERT OR REPLACE does not fire delete triggers).
        """
        with self.conn:
            self.conn.execute("DELETE FROM entries WHERE path = ?", (path,))
            self.conn.execute(
                """
                INSERT INTO entries
                    (path, title, category, tags, aliases, entity_type, source, created,
                     updated, content, title_tokens, tags_tokens, aliases_tokens,
                     content_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    *_index_columns(entry.title, entry.tags, entry.aliases, entry.content),
                ),
            )

    def delete(self, path: str) -> None:
        """Remove an entry from the index."""
        self.conn.execute("DELETE FROM entries WHERE path = ?", (path,))
        self.conn.commit()

    def clear_all(self) -> None:
        """Remove every row from the index (used by reindex)."""
        with self.conn:
            self.conn.execute("DELETE FROM entries")
            # Also drop index rows that no longer have an entries row.
            self.conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('delete-all')")

    def indexed_paths(self) -> set[str]:
        """Return the set of all paths currently in the index."""
        rows = self.conn.execute("SELECT path FROM entries").fetchall()
        return {row[0] for row in rows}

    @staticmethod
    def _fts5_query(query: str) -> str | None:
        """Build an FTS5 MATCH expression from a raw query; None if it has no tokens.

        Each distinct search token becomes a quoted literal, and the literals are
        joined with OR.  Quoting keeps FTS5 syntax characters (+ - ( ) " * :)
        and keywords (AND, NOT, NEAR) literal.

        Examples (input => fts5 query):
            요금제 가격      =>  "요금" OR "금제" OR "가격"
            C++ basics      =>  "c" OR "basics"
        """
        tokens = dict.fromkeys(search_tokens(query))
        if not tokens:
            return None
        return " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)

    def search(self, query: str, category: str | None = None, limit: int = 20) -> list[dict]:
        """Full-text search ranked by weighted BM25.

        Any query token may match. Entries that match more of the query, and
        match it in heavier fields (title > tags > aliases > content), rank
        higher.  Each row has a ``rank`` key with the raw bm25() value
        (negative; lower is better).
        """
        fts_query = self._fts5_query(query)
        if fts_query is None:
            return []
        w = _BM25_WEIGHTS
        bm25_expr = f"bm25(entries_fts, {w[0]}, {w[1]}, {w[2]}, {w[3]})"
        params: tuple = (fts_query, limit)
        category_clause = ""
        if category:
            category_prefix = (
                category.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
            )
            category_clause = "AND (e.category = ? OR e.category LIKE ? ESCAPE '\\')"
            params = (fts_query, category, category_prefix, limit)
        rows = self.conn.execute(
            f"""
            SELECT e.path, e.title, e.category, e.tags, e.aliases,
                   e.entity_type, {bm25_expr} AS rank
            FROM entries_fts fts
            JOIN entries e ON e.rowid = fts.rowid
            WHERE entries_fts MATCH ?
              {category_clause}
            ORDER BY {bm25_expr}
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, path: str) -> dict | None:
        """Get a single entry by path."""
        row = self.conn.execute(
            "SELECT path, title, category, tags, aliases, entity_type, source, created,"
            " updated, content FROM entries WHERE path = ?",
            (path,),
        ).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        """List all entries."""
        rows = self.conn.execute(
            "SELECT path, title, category, tags, aliases, entity_type"
            " FROM entries ORDER BY category, title"
        ).fetchall()
        return [dict(row) for row in rows]

    def catalog(self) -> list[dict]:
        """Rows for the knowledge base index: path, title, category, tags, body length."""
        rows = self.conn.execute(
            "SELECT path, title, category, tags, length(content) AS chars"
            " FROM entries ORDER BY category, path"
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
