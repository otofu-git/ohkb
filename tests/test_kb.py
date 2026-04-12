"""Tests for the KnowledgeBase service layer."""

from __future__ import annotations

import os

import pytest

from orag.kb import KnowledgeBase
from orag.store import Store


@pytest.fixture(autouse=True)
def tmp_orag_dir(tmp_path):
    """Use a temporary directory for all orag data."""
    os.environ["ORAG_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["ORAG_DIR"]


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
        kb.learn("Python is great.", title="Python", category="lang",
                 tags=["python"], aliases=["py"])
        results = kb.search("python")
        assert len(results) >= 1
        assert results[0]["path"] == "lang/python.md"
        assert "score" in results[0]

    def test_search_with_category(self, kb):
        kb.learn("A fact.", title="A", category="cat1", tags=["test"], aliases=["a"])
        kb.learn("B fact.", title="B", category="cat2", tags=["test"], aliases=["b"])
        results = kb.search("test", category="cat1")
        assert all(r["category"] == "cat1" for r in results)


class TestGet:
    def test_get_returns_metadata(self, kb):
        kb.learn("Hello world.", title="Greet", category="test",
                 tags=["hello"], aliases=["hi"])
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
    def test_learn_creates_entry(self, kb, tmp_orag_dir):
        result = kb.learn("Content.", title="New Entry", category="test",
                          tags=["tag1"], aliases=["alias1"])
        assert result["status"] == "created"
        assert result["path"] == "test/new-entry.md"
        assert result["chars"] > 0

        # File exists on disk
        assert (tmp_orag_dir / "wiki" / "test" / "new-entry.md").exists()

    def test_learn_duplicate_raises(self, kb):
        kb.learn("First.", title="Dupe", category="test",
                 tags=["t"], aliases=["a"])
        with pytest.raises(FileExistsError):
            kb.learn("Second.", title="Dupe", category="test",
                     tags=["t"], aliases=["a"])

    def test_learn_overwrite(self, kb):
        kb.learn("First.", title="Over", category="test",
                 tags=["t"], aliases=["a"])
        result = kb.learn("Second.", title="Over", category="test",
                          tags=["t"], aliases=["a"], overwrite=True)
        assert result["status"] == "created"

    def test_learn_empty_content_raises(self, kb):
        with pytest.raises(ValueError, match="empty"):
            kb.learn("", title="Empty", category="test")

    def test_learn_warnings_for_missing_tags(self, kb):
        result = kb.learn("Content.", title="NoTags", category="test")
        assert "warnings" in result
        assert len(result["warnings"]) >= 1

    def test_learn_indexed_for_search(self, kb):
        kb.learn("Unique searchable fact.", title="Indexed", category="test",
                 tags=["unique123"], aliases=["indexed"])
        results = kb.search("unique123")
        assert len(results) >= 1


class TestEdit:
    def test_edit_single_line(self, kb):
        kb.learn("Line A.\nLine B.", title="Edit Me", category="test",
                 tags=["t"], aliases=["a"])
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
        kb.learn("L1\nL2\nL3", title="Del", category="test",
                 tags=["t"], aliases=["a"])
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
        kb.learn("Content.", title="NoOp", category="test",
                 tags=["t"], aliases=["a"])
        with pytest.raises(ValueError, match="exactly one"):
            kb.edit("test/noop.md")

    def test_edit_multiple_ops_raises(self, kb):
        kb.learn("Content.", title="Multi", category="test",
                 tags=["t"], aliases=["a"])
        with pytest.raises(ValueError, match="exactly one"):
            kb.edit("test/multi.md", line=1, delete=2)


class TestMeta:
    def test_add_and_remove_tags(self, kb):
        kb.learn("Fact.", title="Tags", category="test",
                 tags=["original"], aliases=["a"])
        result = kb.meta("test/tags.md", add_tags=["new1", "new2"])
        assert result["status"] == "updated"

        # Verify tags were added
        info = kb.get("test/tags.md")
        content = "\n".join(info["content"])
        assert "new1" in content
        assert "new2" in content

    def test_move_category(self, kb, tmp_orag_dir):
        kb.learn("Fact.", title="Movable", category="old",
                 tags=["t"], aliases=["a"])
        result = kb.meta("old/movable.md", category="new")
        assert result["path"] == "new/movable.md"

        # Old file gone, new file exists
        assert not (tmp_orag_dir / "wiki" / "old" / "movable.md").exists()
        assert (tmp_orag_dir / "wiki" / "new" / "movable.md").exists()


class TestForget:
    def test_forget_archives(self, kb, tmp_orag_dir):
        kb.learn("Temporary.", title="Temp", category="test",
                 tags=["t"], aliases=["a"])
        result = kb.forget("test/temp.md", reason="obsolete")
        assert result["status"] == "archived"
        assert result["path"] == "test/temp.md"

        # File moved to archive
        assert not (tmp_orag_dir / "wiki" / "test" / "temp.md").exists()
        assert (tmp_orag_dir / "archive" / "test" / "temp.md").exists()

        # Removed from search index
        results = kb.search("Temporary")
        assert len(results) == 0

    def test_forget_not_found(self, kb):
        with pytest.raises(FileNotFoundError):
            kb.forget("nonexistent/file.md")


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
        kb.learn("Good entry.", title="Clean", category="test",
                 tags=["tag1"], aliases=["alias1"])
        issues = kb.lint()
        assert issues == []

    def test_lint_detects_oversized(self, kb):
        big_content = "x" * 3500
        kb.learn(big_content, title="Big", category="test",
                 tags=["t"], aliases=["a"])
        issues = kb.lint()
        oversized = [i for i in issues if i["issue"] == "oversized"]
        assert len(oversized) >= 1

    def test_lint_detects_missing_tags(self, kb, tmp_orag_dir):
        # Create a file directly without tags
        wiki_dir = tmp_orag_dir / "wiki" / "test"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        (wiki_dir / "notags.md").write_text(
            "---\ntitle: NoTags\ncategory: test\ntags: []\naliases: []\n"
            "entity_type: concept\nsource: manual\n"
            "created: '2026-01-01T00:00:00Z'\nupdated: '2026-01-01T00:00:00Z'\n"
            "---\n\nContent.\n"
        )
        issues = kb.lint()
        tag_issues = [i for i in issues if i["issue"] == "missing_tags"]
        assert len(tag_issues) >= 1
