"""Basic CLI integration tests for ohkb."""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from ohkb.cli import main


@pytest.fixture(autouse=True)
def tmp_ohkb_dir(tmp_path):
    """Use a temporary directory for all ohkb data."""
    os.environ["OHKB_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["OHKB_DIR"]


@pytest.fixture
def runner():
    return CliRunner()


def _learn(
    runner, content="Some fact.", title="Title", category="test", tags="tag1", aliases="alias1"
):
    """Helper to create an entry."""
    return runner.invoke(
        main,
        [
            "learn",
            content,
            "-t",
            title,
            "-c",
            category,
            "--tags",
            tags,
            "--aliases",
            aliases,
        ],
    )


class TestLearnAndSearch:
    def test_learn_creates_file(self, runner, tmp_ohkb_dir):
        result = _learn(
            runner,
            "Python is a programming language.",
            title="Python Overview",
            category="python",
            tags="python,programming",
            aliases="py,Python language",
        )
        assert result.exit_code == 0
        assert "Learned:" in result.output
        assert "chars" in result.output

        md_file = tmp_ohkb_dir / "wiki" / "python" / "python-overview.md"
        assert md_file.exists()

    def test_learn_and_search(self, runner, tmp_ohkb_dir):
        _learn(
            runner,
            "SQLite is an embedded database.",
            title="SQLite Basics",
            category="databases",
            tags="sqlite,database,embedded",
            aliases="sqlite3,SQLite database",
        )

        result = runner.invoke(main, ["search", "sqlite"])
        assert result.exit_code == 0
        assert "databases/sqlite-basics.md" in result.output

    def test_search_json(self, runner, tmp_ohkb_dir):
        _learn(
            runner,
            "Test content.",
            title="Test Entry",
            category="test",
            tags="test",
            aliases="testing",
        )

        result = runner.invoke(main, ["search", "test", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "score" in data[0]

    def test_search_limit(self, runner, tmp_ohkb_dir):
        for i in range(3):
            _learn(
                runner,
                f"shared token alpha {i}.",
                title=f"Lim{i}",
                category="test",
                tags="alpha",
                aliases=f"a{i}",
            )
        result = runner.invoke(main, ["search", "alpha", "--limit", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1

    def test_search_no_results(self, runner, tmp_ohkb_dir):
        result = runner.invoke(main, ["search", "nonexistent"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_learn_duplicate_error(self, runner, tmp_ohkb_dir):
        _learn(runner, "First version.", title="Dupe", category="test")
        result = _learn(runner, "Second version.", title="Dupe", category="test")
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_learn_overwrite(self, runner, tmp_ohkb_dir):
        _learn(runner, "First version.", title="Overwrite Me", category="test")
        result = runner.invoke(
            main,
            [
                "learn",
                "Second version.",
                "-t",
                "Overwrite Me",
                "-c",
                "test",
                "--tags",
                "tag1",
                "--aliases",
                "alias1",
                "--overwrite",
            ],
        )
        assert result.exit_code == 0

    def test_learn_nested_category(self, runner, tmp_ohkb_dir):
        """CLI learn creates file in nested category directory."""
        result = runner.invoke(
            main,
            [
                "learn",
                "Nested content.",
                "-t",
                "Nested Entry",
                "-c",
                "parent/child",
                "--tags",
                "nested",
                "--aliases",
                "nested-alias",
            ],
        )
        assert result.exit_code == 0
        assert (tmp_ohkb_dir / "wiki" / "parent" / "child" / "nested-entry.md").exists()

    def test_search_parent_category_finds_nested(self, runner, tmp_ohkb_dir):
        """CLI search with parent category finds entries in nested subcategories."""
        runner.invoke(
            main,
            [
                "learn",
                "Nested content.",
                "-t",
                "Nested Entry",
                "-c",
                "parent/child",
                "--tags",
                "nested",
                "--aliases",
                "nested-alias",
            ],
        )
        result = runner.invoke(main, ["search", "nested", "-c", "parent"])
        assert result.exit_code == 0
        assert "parent/child/nested-entry.md" in result.output


class TestGet:
    def test_get_with_header_and_line_numbers(self, runner, tmp_ohkb_dir):
        _learn(
            runner,
            "Line one.\nLine two.\nLine three.",
            title="Multi Line",
            category="test",
            tags="test",
            aliases="multi",
        )

        result = runner.invoke(main, ["get", "test/multi-line.md"])
        assert result.exit_code == 0
        # New: header line with chars and lines
        assert "=== test/multi-line.md" in result.output
        assert "chars" in result.output
        assert "lines" in result.output
        # Still has numbered lines
        assert "   1:" in result.output

    def test_get_json_includes_chars(self, runner, tmp_ohkb_dir):
        _learn(
            runner, "Hello world.", title="Charcount", category="test", tags="test", aliases="cc"
        )

        result = runner.invoke(main, ["get", "test/charcount.md", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "chars" in data
        assert "lines" in data
        assert isinstance(data["chars"], int)
        assert data["chars"] > 0

    def test_get_not_found(self, runner, tmp_ohkb_dir):
        result = runner.invoke(main, ["get", "nonexistent/file.md"])
        assert result.exit_code != 0


class TestEdit:
    def _find_content_line(self, runner, path, needle):
        """Find the line number containing `needle` in the get output."""
        result = runner.invoke(main, ["get", path])
        for line in result.output.strip().split("\n"):
            if needle in line and ":" in line:
                # Parse "  12: Line B" -> 12
                num_str = line.split(":")[0].strip()
                if num_str.isdigit():
                    return int(num_str)
        return None

    def test_edit_line(self, runner, tmp_ohkb_dir):
        _learn(
            runner,
            "First fact.",
            title="Editable",
            category="test",
            tags="test",
            aliases="editable",
        )

        line_num = self._find_content_line(runner, "test/editable.md", "First fact.")
        assert line_num is not None

        result = runner.invoke(
            main,
            [
                "edit",
                "test/editable.md",
                "--line",
                str(line_num),
                "Updated fact.",
            ],
        )
        assert result.exit_code == 0
        assert "chars" in result.output

    def test_delete_line(self, runner, tmp_ohkb_dir):
        _learn(
            runner,
            "Line A\nLine B\nLine C",
            title="Deletable",
            category="test",
            tags="test",
            aliases="del",
        )

        line_num = self._find_content_line(runner, "test/deletable.md", "Line B")
        assert line_num is not None

        result = runner.invoke(
            main,
            [
                "edit",
                "test/deletable.md",
                "--delete",
                str(line_num),
            ],
        )
        assert result.exit_code == 0

    def test_edit_no_operation_error(self, runner, tmp_ohkb_dir):
        _learn(runner, "Content.", title="NoOp", category="test", tags="test", aliases="noop")
        result = runner.invoke(main, ["edit", "test/noop.md", "some text"])
        assert result.exit_code != 0


class TestMeta:
    def test_add_tags(self, runner, tmp_ohkb_dir):
        _learn(
            runner,
            "Some fact.",
            title="Meta Test",
            category="test",
            tags="original",
            aliases="meta",
        )

        result = runner.invoke(
            main,
            [
                "meta",
                "test/meta-test.md",
                "--add-tags",
                "new-tag1,new-tag2",
            ],
        )
        assert result.exit_code == 0
        assert "Updated:" in result.output

    def test_meta_json(self, runner, tmp_ohkb_dir):
        _learn(runner, "Fact.", title="MetaJson", category="test", tags="t", aliases="a")
        result = runner.invoke(
            main,
            [
                "meta",
                "test/metajson.md",
                "--add-tags",
                "x",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "updated"

    def test_meta_title_relocates_file(self, runner, tmp_ohkb_dir):
        _learn(runner, "Fact.", title="OldName", category="test", tags="t", aliases="a")
        result = runner.invoke(
            main,
            [
                "meta",
                "test/oldname.md",
                "--title",
                "NewName",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["path"] == "test/newname.md"
        assert not (tmp_ohkb_dir / "wiki" / "test" / "oldname.md").exists()
        assert (tmp_ohkb_dir / "wiki" / "test" / "newname.md").exists()


class TestForget:
    def test_forget_archives(self, runner, tmp_ohkb_dir):
        _learn(
            runner,
            "Temporary fact.",
            title="Temporary",
            category="test",
            tags="temp",
            aliases="temporary",
        )

        result = runner.invoke(main, ["forget", "test/temporary.md", "--reason", "obsolete"])
        assert result.exit_code == 0
        assert "Archived:" in result.output

        assert not (tmp_ohkb_dir / "wiki" / "test" / "temporary.md").exists()
        assert (tmp_ohkb_dir / "archive" / "test" / "temporary.md").exists()

    def test_forget_not_found(self, runner, tmp_ohkb_dir):
        result = runner.invoke(main, ["forget", "nonexistent/file.md"])
        assert result.exit_code != 0


class TestRestore:
    def test_restore_after_forget(self, runner, tmp_ohkb_dir):
        _learn(runner, "Keep this.", title="Keep", category="test", tags="t", aliases="a")
        runner.invoke(main, ["forget", "test/keep.md"])
        result = runner.invoke(main, ["restore", "test/keep.md", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "restored"
        assert (tmp_ohkb_dir / "wiki" / "test" / "keep.md").exists()

    def test_restore_list(self, runner, tmp_ohkb_dir):
        _learn(runner, "X.", title="Listed", category="test", tags="t", aliases="a")
        runner.invoke(main, ["forget", "test/listed.md"])
        result = runner.invoke(main, ["restore", "--list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(item["original"] == "test/listed.md" for item in data)


class TestReindex:
    def test_reindex_json(self, runner, tmp_ohkb_dir):
        _learn(runner, "Fact.", title="R1", category="test", tags="t", aliases="a")
        result = runner.invoke(main, ["reindex", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["indexed"] >= 1

    def test_reindex_manual_file(self, runner, tmp_ohkb_dir):
        wiki = tmp_ohkb_dir / "wiki" / "manual"
        wiki.mkdir(parents=True)
        (wiki / "hand.md").write_text(
            "---\ntitle: Hand\ncategory: manual\ntags: [hand]\naliases: [h]\n"
            "entity_type: concept\nsource: manual\n"
            "created: '2026-01-01T00:00:00Z'\nupdated: '2026-01-01T00:00:00Z'\n"
            "---\n\nUnique token zqwxmanual.\n",
            encoding="utf-8",
        )
        assert "No results" in runner.invoke(main, ["search", "zqwxmanual"]).output
        re = runner.invoke(main, ["reindex"])
        assert re.exit_code == 0
        result = runner.invoke(main, ["search", "zqwxmanual"])
        assert result.exit_code == 0
        assert "manual/hand.md" in result.output


class TestTreeAndStatus:
    def test_tree_empty(self, runner, tmp_ohkb_dir):
        result = runner.invoke(main, ["tree"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_tree_with_entries(self, runner, tmp_ohkb_dir):
        _learn(runner, "Fact.", title="T1", category="cat1")
        _learn(runner, "Fact.", title="T2", category="cat2")

        result = runner.invoke(main, ["tree"])
        assert result.exit_code == 0
        assert "cat1" in result.output
        assert "cat2" in result.output

    def test_tree_json(self, runner, tmp_ohkb_dir):
        _learn(runner, "Fact.", title="T1", category="mycat")
        result = runner.invoke(main, ["tree", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tree" in data
        assert "path" in data
        assert "depth" in data
        assert "mycat" in data["tree"]

    def test_status(self, runner, tmp_ohkb_dir):
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "Entries:" in result.output

    def test_status_json(self, runner, tmp_ohkb_dir):
        _learn(runner, "Fact.", title="S1", category="test")
        result = runner.invoke(main, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["indexed_entries"] >= 1
        assert data["in_sync"] is True


class TestLint:
    def test_lint_clean(self, runner, tmp_ohkb_dir):
        _learn(runner, "Good entry.", title="Clean", category="test", tags="tag1", aliases="alias1")

        result = runner.invoke(main, ["lint"])
        assert result.exit_code == 0
        assert "No issues" in result.output

    def test_lint_detects_missing_tags(self, runner, tmp_ohkb_dir):
        # Write a file directly without tags, then reindex so only quality issues remain
        wiki_dir = tmp_ohkb_dir / "wiki" / "test"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        (wiki_dir / "bad.md").write_text(
            "---\ntitle: Bad\ncategory: test\ntags: []\naliases: []\n"
            "entity_type: concept\nsource: manual\n"
            "created: '2026-01-01T00:00:00Z'\nupdated: '2026-01-01T00:00:00Z'\n"
            "---\n\nContent.\n"
        )
        runner.invoke(main, ["reindex"])

        result = runner.invoke(main, ["lint"])
        assert result.exit_code == 0
        assert "missing_tags" in result.output or "WARNING" in result.output

    def test_lint_json(self, runner, tmp_ohkb_dir):
        _learn(runner, "Good entry.", title="Good", category="test", tags="t", aliases="a")
        result = runner.invoke(main, ["lint", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


class TestIndexCommand:
    def test_index_writes_file_and_writes_drop_it(self, runner, tmp_ohkb_dir):
        index_path = tmp_ohkb_dir / "wiki" / "_index.md"
        _learn(runner, "Fact.", title="First", category="test", tags="t", aliases="a")
        assert not index_path.exists()  # writes no longer rebuild _index.md

        result = runner.invoke(main, ["index"])
        assert result.exit_code == 0
        assert "First" in result.output
        assert index_path.exists()

        _learn(runner, "Fact.", title="Second", category="test", tags="t", aliases="a")
        assert not index_path.exists()  # invalidated, never stale
        assert "Second" in runner.invoke(main, ["index"]).output

    def test_index_category(self, runner, tmp_ohkb_dir):
        _learn(runner, "A.", title="Alpha", category="a", tags="t", aliases="x")
        _learn(runner, "B.", title="Beta", category="b", tags="t", aliases="y")
        result = runner.invoke(main, ["index", "-c", "a"])
        assert result.exit_code == 0
        assert "Alpha" in result.output
        assert "Beta" not in result.output


class TestVersion:
    def test_version_is_021(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.2.1" in result.output
