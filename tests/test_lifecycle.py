"""Tests for init, sources, log, extract, related."""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from ohkb.cli import main
from ohkb.kb import KnowledgeBase
from ohkb.store import Store


@pytest.fixture(autouse=True)
def tmp_ohkb_dir(tmp_path):
    os.environ["OHKB_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["OHKB_DIR"]


@pytest.fixture
def kb():
    k = KnowledgeBase(Store())
    yield k
    k.close()


@pytest.fixture
def runner():
    return CliRunner()


class TestInit:
    def test_init_creates_layout(self, kb, tmp_ohkb_dir):
        result = kb.init()
        assert result["status"] == "ok"
        assert (tmp_ohkb_dir / "wiki").is_dir()
        assert (tmp_ohkb_dir / "sources").is_dir()
        assert (tmp_ohkb_dir / "archive").is_dir()
        assert (tmp_ohkb_dir / "log.md").exists()
        assert (tmp_ohkb_dir / "AGENTS.ohkb.md").exists()

    def test_init_cli(self, runner, tmp_ohkb_dir):
        result = runner.invoke(main, ["init", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"


class TestSources:
    def test_source_add_file(self, kb, tmp_ohkb_dir):
        raw = tmp_ohkb_dir / "note.txt"
        raw.write_text("raw source body", encoding="utf-8")
        result = kb.source_add(str(raw))
        assert result["status"] == "created"
        assert (tmp_ohkb_dir / "sources" / "note.txt").exists()
        assert any(s["path"] == "note.txt" for s in kb.source_list())

    def test_source_add_cli(self, runner, tmp_ohkb_dir):
        raw = tmp_ohkb_dir / "a.txt"
        raw.write_text("hello", encoding="utf-8")
        result = runner.invoke(main, ["source", "add", str(raw), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["path"] == "a.txt"


class TestExtract:
    def test_extract_file(self, kb, tmp_ohkb_dir):
        f = tmp_ohkb_dir / "doc.txt"
        f.write_text("Extract me unique token zzzyx.", encoding="utf-8")
        result = kb.extract(str(f))
        assert "zzzyx" in result["text"]
        assert result["chars"] > 0

    def test_extract_html_file(self, kb, tmp_ohkb_dir):
        f = tmp_ohkb_dir / "page.html"
        f.write_text(
            "<html><body><p>Hello <b>world</b></p><script>x()</script></body></html>",
            encoding="utf-8",
        )
        result = kb.extract(str(f))
        assert "Hello" in result["text"]
        assert "world" in result["text"]
        assert "x()" not in result["text"]

    def test_extract_cli(self, runner, tmp_ohkb_dir):
        f = tmp_ohkb_dir / "t.txt"
        f.write_text("cli extract body", encoding="utf-8")
        result = runner.invoke(main, ["extract", str(f)])
        assert result.exit_code == 0
        assert "cli extract body" in result.output

    def test_http_and_web_cli_surfaces_are_absent(self, runner):
        main_help = runner.invoke(main, ["--help"])
        assert main_help.exit_code == 0
        assert "  web " not in main_help.output

        serve_help = runner.invoke(main, ["serve", "--help"])
        assert serve_help.exit_code == 0
        assert "--transport" not in serve_help.output
        assert "--host" not in serve_help.output
        assert "--port" not in serve_help.output

        source_help = runner.invoke(main, ["source", "add", "--help"])
        assert source_help.exit_code == 0
        assert "--kind" not in source_help.output


class TestLog:
    def test_log_records_learn(self, kb):
        kb.learn("Fact.", title="L", category="test", tags=["t"], aliases=["a"])
        lines = kb.activity_log(limit=10)
        assert any("learn" in line for line in lines)

    def test_log_cli(self, runner):
        runner.invoke(
            main,
            ["learn", "x", "-t", "T", "-c", "c", "--tags", "t", "--aliases", "a"],
        )
        result = runner.invoke(main, ["log", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any("learn" in line for line in data)


class TestRelated:
    def test_related_by_shared_tags(self, kb):
        kb.learn("A.", title="A", category="test", tags=["shared", "x"], aliases=["a"])
        kb.learn("B.", title="B", category="test", tags=["shared", "y"], aliases=["b"])
        kb.learn("C.", title="C", category="test", tags=["other"], aliases=["c"])
        items = kb.related("test/a.md")
        paths = [i["path"] for i in items]
        assert "test/b.md" in paths
        assert "test/c.md" not in paths
        assert "test/a.md" not in paths
