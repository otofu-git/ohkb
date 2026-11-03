"""Tests for automatic _index.md generation."""

from __future__ import annotations

import os

import pytest

from ohkb.index import (
    INDEX_FILENAME,
    generate_index_content,
    generate_overview,
    invalidate_index,
    read_index,
    refresh_index,
)
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


def _fill(kb, categories: int, per_category: int) -> None:
    for c in range(categories):
        for n in range(per_category):
            kb.learn(
                f"Body {c}-{n}.",
                title=f"Entry {c}-{n} with a fairly long descriptive title for the listing",
                category=f"group{c}",
                tags=[f"tag{c}", "shared"],
                aliases=[],
            )


class TestOverview:
    def test_small_kb_returns_full_listing(self, kb):
        kb.learn("Python fact.", title="Python Basics", category="python", tags=["python"])
        overview = generate_overview(kb=kb)
        assert overview.startswith("# Knowledge Base Index")
        assert "Python Basics" in overview
        assert "Last updated" not in overview  # stable text for agents

    def test_large_kb_returns_bounded_category_summary(self, kb):
        _fill(kb, categories=8, per_category=6)
        overview = generate_overview(kb=kb, max_chars=600)
        assert len(overview) <= 600
        assert overview.startswith("# Knowledge Base Overview")
        assert "Total: 48 entries across 8 categories." in overview
        assert "fairly long descriptive title" not in overview
        assert "— 6 —" in overview

    def test_too_many_categories_are_counted_not_listed(self, kb):
        _fill(kb, categories=40, per_category=2)
        overview = generate_overview(kb=kb, max_chars=600)
        assert len(overview) <= 600
        assert "Total: 80 entries across 40 categories." in overview
        assert "more categories" in overview

    def test_summary_shows_common_tags_and_every_category_when_it_fits(self, kb):
        _fill(kb, categories=3, per_category=10)
        overview = generate_overview(kb=kb, max_chars=1500)
        assert overview.startswith("# Knowledge Base Overview")
        for c in range(3):
            assert f"- group{c} — 10 — " in overview
        assert "shared" in overview
        assert "more categories" not in overview

    def test_category_lists_its_entries_including_nested(self, kb):
        kb.learn("A.", title="Top", category="python", tags=["t"])
        kb.learn("B.", title="Inner", category="python/internals", tags=["t"])
        kb.learn("C.", title="Other", category="rust", tags=["t"])
        overview = generate_overview(kb=kb, category="python")
        assert "Top" in overview and "Inner" in overview
        assert "Other" not in overview

    def test_large_category_is_truncated(self, kb):
        _fill(kb, categories=1, per_category=30)
        overview = generate_overview(kb=kb, category="group0", max_chars=800)
        assert len(overview) <= 800
        assert "more entries" in overview

    def test_unknown_category(self, kb):
        assert "No entries in category 'nope'" in generate_overview(kb=kb, category="nope")


class TestBuiltFromSearchIndex:
    def test_listing_reads_the_index_not_the_files(self, kb, tmp_ohkb_dir):
        kb.learn("Indexed.", title="Indexed", category="cat", tags=["t"])
        stray = tmp_ohkb_dir / "wiki" / "cat" / "stray.md"
        stray.write_text("---\ntitle: Stray\ncategory: cat\n---\n\nNot indexed yet.\n", "utf-8")
        assert "Stray" not in generate_index_content()
        kb.reindex()
        assert "Stray" in generate_index_content()

    def test_category_filter(self, kb):
        kb.learn("A.", title="Alpha", category="a", tags=["t"])
        kb.learn("B.", title="Beta", category="b", tags=["t"])
        content = generate_index_content(category="a")
        assert "Alpha" in content and "Beta" not in content
        assert "Category: a" in content


class TestInvalidateIndex:
    def test_removes_file_and_read_rebuilds_it(self, kb, tmp_ohkb_dir):
        refresh_index()
        index_path = tmp_ohkb_dir / "wiki" / INDEX_FILENAME
        assert index_path.exists()
        invalidate_index()
        assert not index_path.exists()
        kb.learn("New.", title="New", category="test", tags=["t"])
        assert "New" in read_index()
        assert index_path.exists()

    def test_missing_file_is_fine(self, tmp_ohkb_dir):
        invalidate_index()
        assert not (tmp_ohkb_dir / "wiki" / INDEX_FILENAME).exists()
