"""Tests for the KnowledgeBase service layer."""

from __future__ import annotations

import os

import pytest

from ohkb.kb import KnowledgeBase
from ohkb.store import Store


@pytest.fixture(autouse=True)
def tmp_ohkb_dir(tmp_path):
    """Use a temporary directory for all ohkb data."""
    os.environ["OHKB_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["OHKB_DIR"]


@pytest.fixture
def kb():
    """Create a fresh KnowledgeBase instance."""
    store = Store()
    k = KnowledgeBase(store)
    yield k
    k.close()


class TestSearch:
    def test_search_empty(self, kb):
        results = kb.search("anything")
        assert results == []

    def test_search_finds_entry(self, kb):
        kb.learn(
            "Python is great.", title="Python", category="lang", tags=["python"], aliases=["py"]
        )
        results = kb.search("python")
        assert len(results) >= 1
        assert results[0]["path"] == "lang/python.md"
        assert "score" in results[0]

    def test_search_with_category(self, kb):
        kb.learn("A fact.", title="A", category="cat1", tags=["test"], aliases=["a"])
        kb.learn("B fact.", title="B", category="cat2", tags=["test"], aliases=["b"])
        results = kb.search("test", category="cat1")
        assert all(r["category"] == "cat1" for r in results)

    def test_search_multi_word_query(self, kb):
        """Multi-word query ranks the entry matching more words first; unrelated entries miss."""
        kb.learn(
            "요금제 안내: 스타터는 무료, 프로는 유료.",
            title="서비스 요금제",
            category="test",
            tags=["요금제", "pricing"],
            aliases=["가격표"],
        )
        kb.learn(
            "스타터 키트 구성품 목록.",
            title="스타터 키트",
            category="test",
            tags=["kit"],
            aliases=["구성품"],
        )
        kb.learn(
            "완전히 다른 내용.",
            title="무관한 항목",
            category="test",
            tags=["other"],
            aliases=["unrelated"],
        )
        results = kb.search("요금제 스타터 가격")
        paths = [r["path"] for r in results]
        assert paths[0] == "test/서비스-요금제.md"
        assert "test/스타터-키트.md" in paths  # matches only "스타터": OR, not AND
        assert "test/무관한-항목.md" not in paths

    def test_search_matches_korean_compounds_and_particles(self, kb):
        """Bigram tokens: '요금' finds '요금제', and particles or spacing do not block a match."""
        kb.learn(
            "프로 요금제는 월 9000원입니다.",
            title="요금제 안내",
            category="test",
            tags=["요금제", "pricing"],
            aliases=["가격"],
        )
        kb.learn("중소기업 지원 사업 목록.", title="지원 사업", category="test", tags=["지원"])
        assert kb.search("요금")[0]["path"] == "test/요금제-안내.md"
        assert kb.search("요금제를 알려줘")[0]["path"] == "test/요금제-안내.md"
        assert kb.search("중소 기업은?")[0]["path"] == "test/지원-사업.md"

    def test_search_title_outranks_content(self, kb):
        kb.learn("Unrelated body.", title="Kubernetes", category="test", tags=["infra"])
        kb.learn("Notes that mention kubernetes once.", title="Notes", category="test", tags=["x"])
        assert [r["path"] for r in kb.search("kubernetes")] == [
            "test/kubernetes.md",
            "test/notes.md",
        ]

    def test_search_returns_more_than_five_partial_matches(self, kb):
        """0.1.0 capped OR-fallback results at 5; ranked OR results honor limit instead."""
        for i in range(8):
            kb.learn(f"word{i} shared", title=f"Entry {i}", category="test", tags=["t"])
        assert len(kb.search("shared nothing-else-matches", limit=20)) == 8
        assert len(kb.search("shared", limit=3)) == 3

    def test_search_special_chars_safe(self, kb):
        """Queries with FTS5 special characters (C++, parens) must not raise."""
        kb.learn(
            "C++ is a language.", title="Cpp", category="test", tags=["c++", "cpp"], aliases=["cpp"]
        )
        # Should not raise OperationalError
        results = kb.search("C++")
        assert any(r["path"] == "test/cpp.md" for r in results)
        for query in ['"', "a AND", "NOT x", "(a", "x*", "title:foo", "NEAR(a b)"]:
            kb.search(query)
        assert kb.search("!!!") == []


class TestGet:
    def test_get_returns_metadata(self, kb):
        kb.learn("Hello world.", title="Greet", category="test", tags=["hello"], aliases=["hi"])
        result = kb.get("test/greet.md")
        assert result["path"] == "test/greet.md"
        assert isinstance(result["chars"], int)
        assert result["chars"] > 0
        assert isinstance(result["lines"], int)
        assert result["lines"] > 0
        assert isinstance(result["content"], list)

    def test_get_not_found(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.get("nonexistent/file.md")


class TestLearn:
    def test_learn_creates_entry(self, kb, tmp_ohkb_dir):
        result = kb.learn(
            "Content.", title="New Entry", category="test", tags=["tag1"], aliases=["alias1"]
        )
        assert result["status"] == "created"
        assert result["path"] == "test/new-entry.md"
        assert result["chars"] > 0

        # File exists on disk
        assert (tmp_ohkb_dir / "wiki" / "test" / "new-entry.md").exists()

    def test_learn_duplicate_raises(self, kb):
        kb.learn("First.", title="Dupe", category="test", tags=["t"], aliases=["a"])
        with pytest.raises(FileExistsError):
            kb.learn("Second.", title="Dupe", category="test", tags=["t"], aliases=["a"])

    def test_learn_overwrite(self, kb):
        kb.learn("First.", title="Over", category="test", tags=["t"], aliases=["a"])
        result = kb.learn(
            "Second.", title="Over", category="test", tags=["t"], aliases=["a"], overwrite=True
        )
        assert result["status"] == "created"

    def test_learn_empty_content_raises(self, kb):
        with pytest.raises(ValueError, match="empty"):
            kb.learn("", title="Empty", category="test")

    def test_learn_warnings_for_missing_tags(self, kb):
        result = kb.learn("Content.", title="NoTags", category="test")
        assert "warnings" in result
        assert len(result["warnings"]) >= 1

    def test_learn_indexed_for_search(self, kb):
        kb.learn(
            "Unique searchable fact.",
            title="Indexed",
            category="test",
            tags=["unique123"],
            aliases=["indexed"],
        )
        results = kb.search("unique123")
        assert len(results) >= 1


class TestEditTimestamp:
    def test_edit_line_updates_timestamp(self, kb, tmp_ohkb_dir):
        """Line-level edits must update the `updated` timestamp in the frontmatter."""
        import time

        kb.learn("Line 1.\nLine 2.", title="TS", category="test", tags=["t"], aliases=["a"])
        path = tmp_ohkb_dir / "wiki" / "test" / "ts.md"

        def _extract_updated(text):
            for line in text.splitlines():
                if line.startswith("updated:"):
                    return line
            return None

        original_updated = _extract_updated(path.read_text())
        time.sleep(0.05)  # ensure clock advances

        # Find the line number of "Line 1." in the file
        info = kb.get("test/ts.md")
        line_num = next(i for i, line in enumerate(info["content"], 1) if "Line 1." in line)
        kb.edit("test/ts.md", line=line_num, content="Edited line 1.")

        new_updated = _extract_updated(path.read_text())
        assert original_updated != new_updated

    def test_edit_line_reindexes_content(self, kb):
        """After a line edit, the new content is searchable via FTS."""
        kb.learn("Original content.", title="Idx", category="test", tags=["t"], aliases=["a"])
        info = kb.get("test/idx.md")
        content_line = next(i for i, line in enumerate(info["content"], 1) if "Original" in line)
        kb.edit("test/idx.md", line=content_line, content="Replaced unique keyword xyzzy.")
        results = kb.search("xyzzy")
        assert any(r["path"] == "test/idx.md" for r in results)

    def test_edit_frontmatter_line_rejected(self, kb):
        """Line edits must not touch the YAML frontmatter block."""
        kb.learn("Body line.", title="FM", category="test", tags=["t"], aliases=["a"])
        with pytest.raises(ValueError, match="frontmatter"):
            kb.edit("test/fm.md", line=1, content="broken")


class TestEdit:
    def test_edit_single_line(self, kb):
        kb.learn("Line A.\nLine B.", title="Edit Me", category="test", tags=["t"], aliases=["a"])
        info = kb.get("test/edit-me.md")
        # Find a content line
        content_line = None
        for i, line in enumerate(info["content"], 1):
            if "Line A." in line:
                content_line = i
                break
        assert content_line is not None

        result = kb.edit("test/edit-me.md", line=content_line, content="Line A updated.")
        assert result["action"] == f"replaced line {content_line}"
        assert result["chars"] > 0
        assert result["lines"] > 0

    def test_edit_delete_line(self, kb):
        kb.learn("L1\nL2\nL3", title="Del", category="test", tags=["t"], aliases=["a"])
        info = kb.get("test/del.md")
        line_num = None
        for i, line in enumerate(info["content"], 1):
            if "L2" in line:
                line_num = i
                break
        assert line_num is not None

        result = kb.edit("test/del.md", delete=line_num)
        assert "deleted" in result["action"]

    def test_edit_no_op_raises(self, kb):
        kb.learn("Content.", title="NoOp", category="test", tags=["t"], aliases=["a"])
        with pytest.raises(ValueError, match="exactly one"):
            kb.edit("test/noop.md")

    def test_edit_multiple_ops_raises(self, kb):
        kb.learn("Content.", title="Multi", category="test", tags=["t"], aliases=["a"])
        with pytest.raises(ValueError, match="exactly one"):
            kb.edit("test/multi.md", line=1, delete=2)


class TestMeta:
    def test_add_and_remove_tags(self, kb):
        kb.learn("Fact.", title="Tags", category="test", tags=["original"], aliases=["a"])
        result = kb.meta("test/tags.md", add_tags=["new1", "new2"])
        assert result["status"] == "updated"

        # Verify tags were added
        info = kb.get("test/tags.md")
        content = "\n".join(info["content"])
        assert "new1" in content
        assert "new2" in content

    def test_move_category(self, kb, tmp_ohkb_dir):
        kb.learn("Fact.", title="Movable", category="old", tags=["t"], aliases=["a"])
        result = kb.meta("old/movable.md", category="new")
        assert result["path"] == "new/movable.md"

        # Old file gone, new file exists
        assert not (tmp_ohkb_dir / "wiki" / "old" / "movable.md").exists()
        assert (tmp_ohkb_dir / "wiki" / "new" / "movable.md").exists()

    def test_rename_title_removes_old_index_entry(self, kb, tmp_ohkb_dir):
        """Renaming a title changes the slug; old path must leave both index and disk."""
        kb.learn("Fact.", title="OldTitle", category="test", tags=["t"], aliases=["a"])
        # old path is test/oldtitle.md; new slug becomes test/newtitle.md
        result = kb.meta("test/oldtitle.md", title="NewTitle")
        assert result["path"] == "test/newtitle.md"

        # Old path must not remain in the search index
        old_results = kb.search("OldTitle")
        assert all(r["path"] != "test/oldtitle.md" for r in old_results)

        # New path is searchable
        new_results = kb.search("NewTitle")
        assert any(r["path"] == "test/newtitle.md" for r in new_results)

        # Disk: old file gone, new file present
        assert not (tmp_ohkb_dir / "wiki" / "test" / "oldtitle.md").exists()
        assert (tmp_ohkb_dir / "wiki" / "test" / "newtitle.md").exists()

    def test_rename_title_and_category_no_ghost(self, kb, tmp_ohkb_dir):
        """Changing both title and category leaves no ghost entry in SQLite or disk."""
        kb.learn("Fact.", title="Alpha", category="src", tags=["t"], aliases=["a"])
        kb.meta("src/alpha.md", title="Beta", category="dst")
        # The only searchable entry should be at the new path
        results = kb.search("Fact")
        paths = [r["path"] for r in results]
        assert "src/alpha.md" not in paths
        assert "dst/beta.md" in paths
        assert not (tmp_ohkb_dir / "wiki" / "src" / "alpha.md").exists()
        assert (tmp_ohkb_dir / "wiki" / "dst" / "beta.md").exists()

    def test_rename_title_collision_raises(self, kb):
        """Title rename must not overwrite an existing entry."""
        kb.learn("One.", title="First", category="test", tags=["t"], aliases=["a"])
        kb.learn("Two.", title="Second", category="test", tags=["t"], aliases=["a"])
        with pytest.raises(FileExistsError):
            kb.meta("test/first.md", title="Second")


class TestForget:
    def test_forget_archives(self, kb, tmp_ohkb_dir):
        kb.learn("Temporary.", title="Temp", category="test", tags=["t"], aliases=["a"])
        result = kb.forget("test/temp.md", reason="obsolete")
        assert result["status"] == "archived"
        assert result["path"] == "test/temp.md"

        # File moved to archive
        assert not (tmp_ohkb_dir / "wiki" / "test" / "temp.md").exists()
        assert (tmp_ohkb_dir / "archive" / "test" / "temp.md").exists()

        # Removed from search index
        results = kb.search("Temporary")
        assert len(results) == 0

    def test_forget_not_found(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.forget("nonexistent/file.md")

    def test_forget_twice_keeps_both_archives(self, kb, tmp_ohkb_dir):
        """Re-archiving the same path must not overwrite the previous archive."""
        kb.learn("V1.", title="Temp", category="test", tags=["t"], aliases=["a"])
        kb.forget("test/temp.md", reason="first")
        kb.learn("V2.", title="Temp", category="test", tags=["t"], aliases=["a"])
        kb.forget("test/temp.md", reason="second")

        archives = list((tmp_ohkb_dir / "archive" / "test").glob("temp*.md"))
        assert len(archives) == 2


class TestRestore:
    def test_restore_latest(self, kb, tmp_ohkb_dir):
        kb.learn("Remember me.", title="Keep", category="test", tags=["t"], aliases=["a"])
        kb.forget("test/keep.md", reason="oops")
        result = kb.restore("test/keep.md")
        assert result["status"] == "restored"
        assert result["path"] == "test/keep.md"
        assert (tmp_ohkb_dir / "wiki" / "test" / "keep.md").exists()
        results = kb.search("Remember")
        assert any(r["path"] == "test/keep.md" for r in results)

    def test_restore_not_found(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.restore("missing/file.md")

    def test_restore_collision_without_overwrite(self, kb):
        kb.learn("A.", title="Keep", category="test", tags=["t"], aliases=["a"])
        kb.forget("test/keep.md")
        kb.learn("B.", title="Keep", category="test", tags=["t"], aliases=["a"])
        with pytest.raises(FileExistsError):
            kb.restore("test/keep.md")

    def test_restore_overwrite(self, kb):
        kb.learn("A.", title="Keep", category="test", tags=["t"], aliases=["a"])
        kb.forget("test/keep.md")
        kb.learn("B.", title="Keep", category="test", tags=["t"], aliases=["a"])
        result = kb.restore("test/keep.md", overwrite=True)
        assert result["status"] == "restored"
        info = kb.get("test/keep.md")
        assert any("A." in line for line in info["content"])


class TestReindex:
    def test_reindex_picks_up_manual_file(self, kb, tmp_ohkb_dir):
        wiki = tmp_ohkb_dir / "wiki" / "manual"
        wiki.mkdir(parents=True)
        (wiki / "hand.md").write_text(
            "---\ntitle: Hand\ncategory: manual\ntags: [hand]\naliases: [h]\n"
            "entity_type: concept\nsource: manual\n"
            "created: '2026-01-01T00:00:00Z'\nupdated: '2026-01-01T00:00:00Z'\n"
            "---\n\nHand written unique word zqwx.\n",
            encoding="utf-8",
        )
        assert kb.search("zqwx") == []
        result = kb.reindex()
        assert result["indexed"] >= 1
        assert result["status"] == "ok"
        assert any(r["path"] == "manual/hand.md" for r in kb.search("zqwx"))

    def test_reindex_removes_stale_index(self, kb, tmp_ohkb_dir):
        kb.learn("Ghost.", title="Ghost", category="test", tags=["ghost"], aliases=["g"])
        # Delete file without going through forget
        (tmp_ohkb_dir / "wiki" / "test" / "ghost.md").unlink()
        kb.reindex()
        assert kb.search("Ghost") == []
        assert kb.status()["in_sync"] is True


class TestTreeAndStatus:
    def test_tree_empty(self, kb):
        result = kb.tree()
        assert result["tree"] == {}
        assert result["path"] == "/"
        assert result["depth"] == 2

    def test_tree_with_entries(self, kb):
        kb.learn("A.", title="A", category="cat1", tags=["t"], aliases=["a"])
        kb.learn("B.", title="B", category="cat2", tags=["t"], aliases=["a"])
        result = kb.tree()
        assert "cat1" in result["tree"]
        assert "cat2" in result["tree"]
        # files are nested under category nodes
        assert "a.md" in result["tree"]["cat1"]
        assert "b.md" in result["tree"]["cat2"]

    def test_tree_path(self, kb):
        kb.learn("A.", title="A", category="cat1", tags=["t"], aliases=["a"])
        result = kb.tree("cat1")
        assert result["path"] == "cat1"
        assert "a.md" in result["tree"]

    def test_tree_depth_truncation(self, kb):
        kb.learn("A.", title="A", category="cat1", tags=["t"], aliases=["a"])
        result = kb.tree(depth=1)
        # depth=1: only top-level dirs visible, files inside are not expanded
        assert "cat1" in result["tree"]
        assert result["tree"]["cat1"] == {"_truncated": True}

    def test_status(self, kb):
        kb.learn("Fact.", title="S1", category="test", tags=["t"], aliases=["a"])
        result = kb.status()
        assert result["indexed_entries"] >= 1
        assert result["files_on_disk"] >= 1
        assert "test" in result["categories"]


class TestLint:
    def test_lint_clean(self, kb):
        kb.learn("Good entry.", title="Clean", category="test", tags=["tag1"], aliases=["alias1"])
        issues = kb.lint()
        assert issues == []

    def test_lint_detects_oversized(self, kb):
        big_content = "x" * 3500
        kb.learn(big_content, title="Big", category="test", tags=["t"], aliases=["a"])
        issues = kb.lint()
        oversized = [i for i in issues if i["issue"] == "oversized"]
        assert len(oversized) >= 1

    def test_lint_detects_missing_tags(self, kb, tmp_ohkb_dir):
        # Create a file directly without tags, then reindex so only tag issues remain
        wiki_dir = tmp_ohkb_dir / "wiki" / "test"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        (wiki_dir / "notags.md").write_text(
            "---\ntitle: NoTags\ncategory: test\ntags: []\naliases: []\n"
            "entity_type: concept\nsource: manual\n"
            "created: '2026-01-01T00:00:00Z'\nupdated: '2026-01-01T00:00:00Z'\n"
            "---\n\nContent.\n"
        )
        kb.reindex()
        issues = kb.lint()
        tag_issues = [i for i in issues if i["issue"] == "missing_tags"]
        assert len(tag_issues) >= 1

    def test_lint_detects_unindexed(self, kb, tmp_ohkb_dir):
        wiki_dir = tmp_ohkb_dir / "wiki" / "test"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        (wiki_dir / "orphan.md").write_text(
            "---\ntitle: Orphan\ncategory: test\ntags: [t]\naliases: [a]\n"
            "entity_type: concept\nsource: manual\n"
            "created: '2026-01-01T00:00:00Z'\nupdated: '2026-01-01T00:00:00Z'\n"
            "---\n\nContent.\n",
            encoding="utf-8",
        )
        issues = kb.lint()
        assert any(i["issue"] == "unindexed" for i in issues)


class TestNestedCategory:
    def test_learn_nested_category_creates_file(self, kb, tmp_ohkb_dir):
        """learn with nested category creates the correct directory structure."""
        result = kb.learn(
            "CPython internals.",
            title="CPython",
            category="python/internals",
            tags=["cpython", "internals"],
            aliases=["cpy"],
        )
        assert result["status"] == "created"
        assert result["path"] == "python/internals/cpython.md"
        assert (tmp_ohkb_dir / "wiki" / "python" / "internals" / "cpython.md").exists()

    def test_search_parent_category_includes_nested(self, kb):
        """search with parent category returns entries from nested subcategories."""
        kb.learn(
            "CPython internals.",
            title="CPython",
            category="python/internals",
            tags=["cpython"],
            aliases=["cpy"],
        )
        # Searching with parent category "python" should find "python/internals" entries
        results = kb.search("cpython", category="python")
        assert len(results) >= 1
        assert results[0]["path"] == "python/internals/cpython.md"

    def test_search_exact_nested_category(self, kb):
        """search with full nested category path returns matching entries."""
        kb.learn(
            "CPython internals.",
            title="CPython",
            category="python/internals",
            tags=["cpython"],
            aliases=["cpy"],
        )
        results = kb.search("cpython", category="python/internals")
        assert len(results) >= 1

    def test_search_sibling_category_not_included(self, kb):
        """search scoped to one subcategory does not return sibling subcategory entries."""
        kb.learn(
            "CPython.",
            title="CPython",
            category="python/internals",
            tags=["cpython"],
            aliases=["cpy"],
        )
        kb.learn(
            "asyncio.",
            title="Asyncio",
            category="python/stdlib",
            tags=["asyncio"],
            aliases=["async"],
        )
        results = kb.search("asyncio", category="python/internals")
        assert all(r["category"] == "python/internals" for r in results)

    def test_read_entry_category_parsed_correctly(self, kb, tmp_ohkb_dir):
        """After learn, read_entry returns the full nested category path."""
        from ohkb.wiki import read_entry

        kb.learn(
            "CPython internals.",
            title="CPython",
            category="python/internals",
            tags=["cpython"],
            aliases=["cpy"],
        )
        entry = read_entry("python/internals/cpython.md")
        assert entry.category == "python/internals"

    def test_forget_removes_nested_empty_dirs(self, kb, tmp_ohkb_dir):
        """Forgetting the only entry in a nested category removes all empty parent dirs."""
        kb.learn(
            "CPython internals.",
            title="CPython",
            category="python/internals",
            tags=["cpython"],
            aliases=["cpy"],
        )
        kb.forget("python/internals/cpython.md")

        # Both the nested dir and its empty parent should be gone
        assert not (tmp_ohkb_dir / "wiki" / "python" / "internals").exists()
        assert not (tmp_ohkb_dir / "wiki" / "python").exists()

    def test_meta_move_nested_category(self, kb, tmp_ohkb_dir):
        """meta can move an entry from a nested category to another nested category."""
        kb.learn(
            "CPython internals.",
            title="CPython",
            category="python/internals",
            tags=["cpython"],
            aliases=["cpy"],
        )
        result = kb.meta("python/internals/cpython.md", category="python/cpython")
        assert result["path"] == "python/cpython/cpython.md"
        assert (tmp_ohkb_dir / "wiki" / "python" / "cpython" / "cpython.md").exists()
        assert not (tmp_ohkb_dir / "wiki" / "python" / "internals" / "cpython.md").exists()

    def test_tree_shows_nested_structure(self, kb):
        """tree with depth>=3 shows nested subdirectory entries."""
        kb.learn(
            "CPython.",
            title="CPython",
            category="python/internals",
            tags=["cpython"],
            aliases=["cpy"],
        )
        result = kb.tree(depth=3)
        assert "python" in result["tree"]
        assert "internals" in result["tree"]["python"]
        assert "cpython.md" in result["tree"]["python"]["internals"]
