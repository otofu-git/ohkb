"""Basic CLI integration tests for orag."""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from orag.cli import main


@pytest.fixture(autouse=True)
def tmp_orag_dir(tmp_path):
    """Use a temporary directory for all orag data."""
    os.environ["ORAG_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["ORAG_DIR"]


@pytest.fixture
def runner():
    return CliRunner()


def _learn(runner, content="Some fact.", title="Title", category="test",
           tags="tag1", aliases="alias1"):
    """Helper to create an entry."""
    return runner.invoke(main, [
        "learn", content, "-t", title, "-c", category,
        "--tags", tags, "--aliases", aliases,
    ])


class TestLearnAndSearch:
    def test_learn_creates_file(self, runner, tmp_orag_dir):
        result = _learn(runner, "Python is a programming language.",
                        title="Python Overview", category="python",
                        tags="python,programming", aliases="py,Python language")
        assert result.exit_code == 0
        assert "Learned:" in result.output
        assert "chars" in result.output

        md_file = tmp_orag_dir / "wiki" / "python" / "python-overview.md"
        assert md_file.exists()

    def test_learn_and_search(self, runner, tmp_orag_dir):
        _learn(runner, "SQLite is an embedded database.",
               title="SQLite Basics", category="databases",
               tags="sqlite,database,embedded", aliases="sqlite3,SQLite database")

        result = runner.invoke(main, ["search", "sqlite"])
        assert result.exit_code == 0
        assert "databases/sqlite-basics.md" in result.output

    def test_search_json(self, runner, tmp_orag_dir):
        _learn(runner, "Test content.", title="Test Entry", category="test",
               tags="test", aliases="testing")

        result = runner.invoke(main, ["search", "test", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0
        # New: check score field exists (was rank before)
        assert "score" in data[0]

    def test_search_no_results(self, runner, tmp_orag_dir):
        result = runner.invoke(main, ["search", "nonexistent"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_learn_duplicate_error(self, runner, tmp_orag_dir):
        _learn(runner, "First version.", title="Dupe", category="test")
        result = _learn(runner, "Second version.", title="Dupe", category="test")
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_learn_overwrite(self, runner, tmp_orag_dir):
        _learn(runner, "First version.", title="Overwrite Me", category="test")
        result = runner.invoke(main, [
            "learn", "Second version.", "-t", "Overwrite Me", "-c", "test",
            "--tags", "tag1", "--aliases", "alias1", "--overwrite",
        ])
        assert result.exit_code == 0


class TestGet:
    def test_get_with_header_and_line_numbers(self, runner, tmp_orag_dir):
        _learn(runner, "Line one.\nLine two.\nLine three.",
               title="Multi Line", category="test",
               tags="test", aliases="multi")

        result = runner.invoke(main, ["get", "test/multi-line.md"])
        assert result.exit_code == 0
        # New: header line with chars and lines
        assert "=== test/multi-line.md" in result.output
        assert "chars" in result.output
        assert "lines" in result.output
        # Still has numbered lines
        assert "   1:" in result.output

    def test_get_json_includes_chars(self, runner, tmp_orag_dir):
        _learn(runner, "Hello world.", title="Charcount", category="test",
               tags="test", aliases="cc")

        result = runner.invoke(main, ["get", "test/charcount.md", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "chars" in data
        assert "lines" in data
        assert isinstance(data["chars"], int)
        assert data["chars"] > 0

    def test_get_not_found(self, runner, tmp_orag_dir):
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

    def test_edit_line(self, runner, tmp_orag_dir):
        _learn(runner, "First fact.", title="Editable", category="test",
               tags="test", aliases="editable")

        line_num = self._find_content_line(runner, "test/editable.md", "First fact.")
        assert line_num is not None

        result = runner.invoke(main, [
            "edit", "test/editable.md",
            "--line", str(line_num), "Updated fact.",
        ])
        assert result.exit_code == 0
        assert "chars" in result.output

    def test_delete_line(self, runner, tmp_orag_dir):
        _learn(runner, "Line A\nLine B\nLine C",
               title="Deletable", category="test",
               tags="test", aliases="del")

        line_num = self._find_content_line(runner, "test/deletable.md", "Line B")
        assert line_num is not None

        result = runner.invoke(main, [
            "edit", "test/deletable.md",
            "--delete", str(line_num),
        ])
        assert result.exit_code == 0

    def test_edit_no_operation_error(self, runner, tmp_orag_dir):
        _learn(runner, "Content.", title="NoOp", category="test",
               tags="test", aliases="noop")
        result = runner.invoke(main, ["edit", "test/noop.md", "some text"])
        assert result.exit_code != 0


class TestMeta:
    def test_add_tags(self, runner, tmp_orag_dir):
        _learn(runner, "Some fact.", title="Meta Test", category="test",
               tags="original", aliases="meta")

        result = runner.invoke(main, [
            "meta", "test/meta-test.md", "--add-tags", "new-tag1,new-tag2",
        ])
        assert result.exit_code == 0
        assert "Updated:" in result.output

    def test_meta_json(self, runner, tmp_orag_dir):
        _learn(runner, "Fact.", title="MetaJson", category="test",
               tags="t", aliases="a")
        result = runner.invoke(main, [
            "meta", "test/metajson.md", "--add-tags", "x", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "updated"


class TestForget:
    def test_forget_archives(self, runner, tmp_orag_dir):
        _learn(runner, "Temporary fact.", title="Temporary", category="test",
               tags="temp", aliases="temporary")

        result = runner.invoke(main, ["forget", "test/temporary.md", "--reason", "obsolete"])
        assert result.exit_code == 0
        assert "Archived:" in result.output

        assert not (tmp_orag_dir / "wiki" / "test" / "temporary.md").exists()
        assert (tmp_orag_dir / "archive" / "test" / "temporary.md").exists()

    def test_forget_not_found(self, runner, tmp_orag_dir):
        result = runner.invoke(main, ["forget", "nonexistent/file.md"])
        assert result.exit_code != 0


class TestTreeAndStatus:
    def test_tree_empty(self, runner, tmp_orag_dir):
        result = runner.invoke(main, ["tree"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_tree_with_entries(self, runner, tmp_orag_dir):
        _learn(runner, "Fact.", title="T1", category="cat1")
        _learn(runner, "Fact.", title="T2", category="cat2")

        result = runner.invoke(main, ["tree"])
        assert result.exit_code == 0
        assert "cat1" in result.output
        assert "cat2" in result.output

    def test_tree_json(self, runner, tmp_orag_dir):
        _learn(runner, "Fact.", title="T1", category="mycat")
        result = runner.invoke(main, ["tree", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tree" in data
        assert "path" in data
        assert "depth" in data
        assert "mycat" in data["tree"]

    def test_status(self, runner, tmp_orag_dir):
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "Entries:" in result.output

    def test_status_json(self, runner, tmp_orag_dir):
        _learn(runner, "Fact.", title="S1", category="test")
        result = runner.invoke(main, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["indexed_entries"] >= 1


class TestLint:
    def test_lint_clean(self, runner, tmp_orag_dir):
        _learn(runner, "Good entry.", title="Clean", category="test",
               tags="tag1", aliases="alias1")

        result = runner.invoke(main, ["lint"])
        assert result.exit_code == 0
        assert "No issues" in result.output

    def test_lint_detects_missing_tags(self, runner, tmp_orag_dir):
        # Write a file directly without tags
        wiki_dir = tmp_orag_dir / "wiki" / "test"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        (wiki_dir / "bad.md").write_text(
            "---\ntitle: Bad\ncategory: test\ntags: []\naliases: []\n"
            "entity_type: concept\nsource: manual\n"
            "created: '2026-01-01T00:00:00Z'\nupdated: '2026-01-01T00:00:00Z'\n"
            "---\n\nContent.\n"
        )

        result = runner.invoke(main, ["lint"])
        assert result.exit_code == 0
        assert "missing_tags" in result.output or "WARNING" in result.output

    def test_lint_json(self, runner, tmp_orag_dir):
        _learn(runner, "Good entry.", title="Good", category="test",
               tags="t", aliases="a")
        result = runner.invoke(main, ["lint", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
