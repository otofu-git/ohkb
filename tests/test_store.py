"""Tests for search tokens, the FTS5 index, and schema migrations."""

from __future__ import annotations

import sqlite3
import unicodedata

import pytest

from ohkb.models import Entry
from ohkb.store import SCHEMA_VERSION, Store, search_tokens

# Schema 1 exactly as ohkb 0.1.0 created it.
_V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    path        TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '',
    aliases     TEXT NOT NULL DEFAULT '',
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
"""

_V1_INSERT = """
INSERT OR REPLACE INTO entries
    (path, title, category, tags, aliases, entity_type, source, created, updated, content)
VALUES (?, ?, ?, ?, ?, 'concept', 'manual', '2026-01-01T00:00:00+00:00',
        '2026-01-01T00:00:00+00:00', ?)
"""


def _make_v1_db(path, *, versioned: bool = True) -> None:
    """Create a 0.1.0 database, including the stale index rows 0.1.0 left on updates."""
    conn = sqlite3.connect(path)
    conn.executescript(_V1_SCHEMA)
    old = ("pricing/요금제.md", "요금제 안내", "pricing", "요금제,가격", "pricing", "구버전 본문")
    rows = [
        old,
        (*old[:5], "프로는 월 9000원"),
        ("lang/python.md", "Python", "lang", "python", "py", "Python is great."),
    ]
    for row in rows:
        conn.execute(_V1_INSERT, row)
    if versioned:
        conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
    conn.commit()
    conn.close()


def _indexed_rows(store: Store) -> int:
    return store.conn.execute("SELECT COUNT(*) FROM entries_fts_docsize").fetchone()[0]


def _integrity_check(store: Store) -> None:
    store.conn.execute("INSERT INTO entries_fts(entries_fts) VALUES('integrity-check')")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "_meta.db")
    yield s
    s.close()


class TestSearchTokens:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("중소기업", ["중소", "소기", "기업"]),
            ("시 지원", ["시", "지원"]),
            ("AI바우처", ["ai", "바우", "우처"]),
            ("3.5억 1,000원", ["3.5", "억", "1,000", "원"]),
            ("중소ㆍ벤처", ["중소", "벤처"]),
            ("ㅇ 신청자격 ① Ⅱ 대상", ["신청", "청자", "자격", "대상"]),
            ("Café TÜV", ["café", "tüv"]),
            ("東京都 カタカナ", ["東京", "京都", "カタ", "タカ", "カナ"]),
            ("snake_case C++", ["snake", "case", "c"]),
            ("", []),
            ("!!! ... ·", []),
        ],
    )
    def test_tokens(self, text, expected):
        assert search_tokens(text) == expected

    def test_decomposed_text_matches_composed(self):
        composed = "한국어 café"
        assert search_tokens(unicodedata.normalize("NFD", composed)) == search_tokens(composed)


class TestIndex:
    def test_token_columns_hold_search_tokens(self, store):
        store.upsert(
            Entry(title="요금제 안내", category="c", content="프로 9,000원", tags=["가격표"])
        )
        row = store.conn.execute(
            "SELECT title_tokens, tags_tokens, content_tokens FROM entries"
        ).fetchone()
        assert tuple(row) == ("요금 금제 안내", "가격 격표", "프로 9,000 원")

    def test_replacing_an_entry_leaves_no_stale_index_rows(self, store):
        for word in ("alpha", "beta", "gamma"):
            store.upsert(Entry(title="Same", category="c", content=f"{word} body", tags=["t"]))
        assert _indexed_rows(store) == 1
        assert store.search("alpha") == []
        assert [r["path"] for r in store.search("gamma")] == ["c/same.md"]
        _integrity_check(store)

    def test_delete_and_clear_all_empty_the_index(self, store):
        store.upsert(Entry(title="One", category="c", content="first"))
        store.upsert(Entry(title="Two", category="c", content="second"))
        store.delete("c/one.md")
        assert _indexed_rows(store) == 1
        store.clear_all()
        assert _indexed_rows(store) == 0
        assert store.search("second") == []
        _integrity_check(store)

    def test_get_omits_token_columns(self, store):
        store.upsert(Entry(title="One", category="c", content="first"))
        row = store.get("c/one.md")
        assert row["content"] == "first"
        assert not any(key.endswith("_tokens") for key in row)

    def test_query_without_tokens_returns_nothing(self, store):
        store.upsert(Entry(title="One", category="c", content="first"))
        assert store.search("!!! ...") == []

    def test_long_query_is_accepted(self, store):
        store.upsert(Entry(title="One", category="c", content="needle"))
        query = " ".join(f"word{i}" for i in range(2000)) + " needle"
        assert [r["path"] for r in store.search(query)] == ["c/one.md"]


class TestSchema:
    def _version_rows(self, store: Store) -> list[int]:
        return [r[0] for r in store.conn.execute("SELECT version FROM schema_version")]

    def test_new_database_uses_current_schema(self, store):
        assert self._version_rows(store) == [SCHEMA_VERSION]

    def test_reopening_keeps_a_single_version_row(self, tmp_path):
        for _ in range(2):
            s = Store(tmp_path / "_meta.db")
            assert self._version_rows(s) == [SCHEMA_VERSION]
            s.close()

    @pytest.mark.parametrize("versioned", [True, False])
    def test_migrates_v1_database(self, tmp_path, versioned):
        db = tmp_path / "_meta.db"
        _make_v1_db(db, versioned=versioned)

        store = Store(db)
        try:
            assert self._version_rows(store) == [SCHEMA_VERSION]
            assert _indexed_rows(store) == 2  # the stale 0.1.0 row is gone
            _integrity_check(store)
            # Korean particles and AND-free matching work on migrated rows.
            assert store.search("요금제를 알려줘")[0]["path"] == "pricing/요금제.md"
            assert store.search("구버전") == []
            assert [r["path"] for r in store.search("python")] == ["lang/python.md"]
            # Updates after the migration keep the index in sync.
            store.upsert(Entry(title="Python", category="lang", content="Now with GIL notes."))
            assert [r["path"] for r in store.search("gil")] == ["lang/python.md"]
            assert _indexed_rows(store) == 2
            _integrity_check(store)
        finally:
            store.close()

    def test_newer_schema_is_refused(self, tmp_path):
        db = tmp_path / "_meta.db"
        s = Store(db)
        s.conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 1,))
        s.conn.commit()
        s.close()
        with pytest.raises(RuntimeError, match="newer than this ohkb"):
            _ = Store(db).conn
        s = Store(db)
        for _ in range(2):  # a retry must not reuse the unchecked connection
            with pytest.raises(RuntimeError, match="newer than this ohkb"):
                _ = s.conn

    def test_v1_code_leaves_migrated_database_untouched(self, tmp_path):
        """0.1.0 runs its CREATE ... IF NOT EXISTS script before refusing schema 2."""
        db = tmp_path / "_meta.db"
        s = Store(db)
        s.upsert(Entry(title="One", category="c", content="첫 번째 항목"))
        s.close()

        conn = sqlite3.connect(db)
        conn.executescript(_V1_SCHEMA)
        conn.close()

        s = Store(db)
        try:
            s.upsert(Entry(title="Two", category="c", content="두 번째 항목"))
            assert _indexed_rows(s) == 2
            _integrity_check(s)
            assert {r["path"] for r in s.search("항목")} == {"c/one.md", "c/two.md"}
        finally:
            s.close()
