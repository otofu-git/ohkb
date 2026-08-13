"""Tests for automatic _index.md generation."""

from __future__ import annotations

import os

import pytest

from ohkb.index import INDEX_FILENAME, generate_index_content, read_index, refresh_index
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
    store = Store()
    k = KnowledgeBase(store)
    yield k
    k.close()


class TestGenerateIndex:
    def test_empty_kb(self, tmp_ohkb_dir):
        content = generate_index_content()
        assert "Knowledge Base Index" in content
        assert "0 entries" in content
        assert "empty" in content.lower()

    def test_with_entries(self, kb, tmp_ohkb_dir):
        kb.learn(
            "Python fact.",
            title="Python Basics",
            category="python",
            tags=["python", "basics"],
            aliases=["py"],
        )
        kb.learn(
            "Rust fact.",
            title="Rust Ownership",
            category="rust",
            tags=["rust", "ownership"],
            aliases=["borrow checker"],
        )

        content = generate_index_content()
        assert "2 entries" in content
        assert "2 categories" in content
        assert "### python" in content
        assert "### rust" in content
        assert "Python Basics" in content
        assert "Rust Ownership" in content
        assert "python, basics" in content  # tags
        assert "chars" in content

    def test_includes_char_count(self, kb, tmp_ohkb_dir):
        kb.learn("Short content.", title="Small", category="test", tags=["t"], aliases=["a"])
        content = generate_index_content()
        assert "chars" in content


class TestRefreshIndex:
    def test_creates_file(self, tmp_ohkb_dir):
        path = refresh_index()
        assert path.exists()
        assert path.name == INDEX_FILENAME
        assert path.parent == tmp_ohkb_dir / "wiki"

    def test_updates_on_refresh(self, kb, tmp_ohkb_dir):
        refresh_index()
        content1 = read_index()
        assert "0 entries" in content1

        kb.learn("New fact.", title="New", category="test", tags=["t"], aliases=["a"])
        refresh_index()
        content2 = read_index()
        assert "1 entries" in content2
        assert content2 != content1


class TestReadIndex:
    def test_auto_creates_if_missing(self, tmp_ohkb_dir):
        index_path = tmp_ohkb_dir / "wiki" / INDEX_FILENAME
        assert not index_path.exists()

        content = read_index()
        assert "Knowledge Base Index" in content
        assert index_path.exists()

    def test_reads_existing(self, tmp_ohkb_dir):
        refresh_index()
        content = read_index()
        assert "Knowledge Base Index" in content
