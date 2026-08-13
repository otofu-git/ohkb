"""Security regression tests for local filesystem boundaries."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from ohkb.cli import main
from ohkb.config import get_archive_dir, get_wiki_dir
from ohkb.extract import MAX_EXTRACT_BYTES, extract_file
from ohkb.index import refresh_index
from ohkb.kb import KnowledgeBase
from ohkb.logutil import append_log, read_log
from ohkb.models import Entry
from ohkb.pathutil import confined_path
from ohkb.store import Store


@pytest.fixture(autouse=True)
def tmp_ohkb_dir(tmp_path):
    os.environ["OHKB_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["OHKB_DIR"]


@pytest.fixture
def kb():
    instance = KnowledgeBase(Store())
    yield instance
    instance.close()


class TestPathConfinement:
    def test_read_edit_forget_and_tree_cannot_escape_wiki(self, kb, tmp_ohkb_dir):
        outside = tmp_ohkb_dir / "outside.md"
        outside.write_text("outside secret", encoding="utf-8")

        with pytest.raises(ValueError):
            kb.get("../outside.md")
        with pytest.raises(ValueError):
            kb.edit("../outside.md", line=1, content="changed")
        with pytest.raises(ValueError):
            kb.forget("../outside.md")
        with pytest.raises(ValueError):
            kb.tree("..")

        assert outside.read_text(encoding="utf-8") == "outside secret"

    @pytest.mark.parametrize(
        "category",
        ["", ".", "..", "../escape", "safe/../../escape", "/absolute", "safe//nested"],
    )
    def test_learn_rejects_noncanonical_or_escaping_category(self, kb, category):
        with pytest.raises(ValueError):
            kb.learn("body", title="Escape", category=category, tags=["security"])

    def test_absolute_and_windows_style_paths_are_rejected(self, tmp_ohkb_dir):
        base = tmp_ohkb_dir / "wiki"
        base.mkdir()
        for value in ("/tmp/secret", "C:\\Users\\secret", "../secret", "a/./secret"):
            with pytest.raises(ValueError):
                confined_path(base, value)

    def test_restore_rejects_archive_path_traversal(self, kb, tmp_ohkb_dir):
        outside = tmp_ohkb_dir / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        with pytest.raises(ValueError):
            kb.restore(archive_path="../outside.md")
        assert outside.exists()

    def test_restore_rejects_traversal_from_archive_footer(self, kb, tmp_ohkb_dir):
        archive = get_archive_dir() / "safe.md"
        entry = Entry(title="Safe", category="safe", content="body")
        archive.write_text(
            entry.to_markdown()
            + "\n<!-- archived: 2026-01-01T00:00:00Z reason: x original: ../escaped.md -->\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError):
            kb.restore(archive_path="safe.md")
        assert archive.exists()
        assert not (tmp_ohkb_dir / "escaped.md").exists()

    def test_archive_reason_cannot_override_original_path(self, kb, tmp_ohkb_dir):
        kb.learn("body", title="Real", category="safe", tags=["security"])
        result = kb.forget("safe/real.md", reason="original: other/target.md")
        archive_rel = Path(result["archived_to"]).relative_to(get_archive_dir()).as_posix()

        restored = kb.restore(archive_path=archive_rel)
        assert restored["path"] == "safe/real.md"
        assert (tmp_ohkb_dir / "wiki" / "safe" / "real.md").exists()
        assert not (tmp_ohkb_dir / "wiki" / "other" / "target.md").exists()

    def test_category_filter_treats_like_wildcards_literally(self, kb):
        kb.learn("needle", title="Nested", category="safe/nested", tags=["needle"])
        assert kb.search("needle", category="%") == []
        assert kb.search("needle", category="_") == []

    def test_cli_reports_path_rejection_without_traceback(self, tmp_ohkb_dir):
        outside = tmp_ohkb_dir / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        result = CliRunner().invoke(main, ["get", "../outside.md"])
        assert result.exit_code == 1
        assert "Error:" in result.output
        assert "Traceback" not in result.output


class TestSymlinkConfinement:
    @staticmethod
    def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlinks unavailable: {exc}")

    def test_wiki_symlink_cannot_expose_external_file(self, kb, tmp_ohkb_dir):
        outside_dir = tmp_ohkb_dir / "outside"
        outside_dir.mkdir()
        (outside_dir / "secret.md").write_text("secret", encoding="utf-8")
        link = get_wiki_dir() / "escape"
        self._symlink_or_skip(link, outside_dir, directory=True)

        with pytest.raises(ValueError):
            kb.get("escape/secret.md")
        assert "escape" not in kb.tree()["tree"]

    def test_data_subdirectory_symlink_cannot_escape_ohkb_dir(self, tmp_ohkb_dir):
        external = tmp_ohkb_dir.parent / f"{tmp_ohkb_dir.name}-external"
        external.mkdir()
        link = tmp_ohkb_dir / "wiki"
        self._symlink_or_skip(link, external, directory=True)
        try:
            with pytest.raises(ValueError):
                get_wiki_dir()
        finally:
            link.unlink(missing_ok=True)
            external.rmdir()

    def test_index_symlink_cannot_overwrite_outside_wiki(self, tmp_ohkb_dir):
        wiki = get_wiki_dir()
        outside = tmp_ohkb_dir / "outside-index.md"
        outside.write_text("sentinel", encoding="utf-8")
        self._symlink_or_skip(wiki / "_index.md", outside)

        with pytest.raises(ValueError):
            refresh_index()
        assert outside.read_text(encoding="utf-8") == "sentinel"

    def test_internal_file_symlink_is_rejected(self, kb):
        kb.learn("body", title="Real", category="safe", tags=["security"])
        wiki = get_wiki_dir()
        self._symlink_or_skip(wiki / "safe" / "alias.md", wiki / "safe" / "real.md")

        with pytest.raises(ValueError, match="Symbolic links"):
            kb.get("safe/alias.md")


class TestInputHardening:
    def test_source_parent_name_is_sanitized(self, kb, tmp_ohkb_dir):
        source = tmp_ohkb_dir / "input.txt"
        source.write_text("body", encoding="utf-8")
        result = kb.source_add(str(source), name="..")
        assert result["path"] == "source"
        assert (tmp_ohkb_dir / "sources" / "source").exists()

    def test_log_control_characters_do_not_create_fake_entries(self):
        append_log("learn\n## [fake] injected", "entry\r\n## [fake] detail")
        lines = read_log()
        assert len(lines) == 1
        assert "injected" in lines[0]
        assert "\n" not in lines[0]

    def test_frontmatter_rejects_non_string_list_items(self):
        text = "---\ntitle: Bad\ncategory: test\ntags:\n  key: value\n---\nbody\n"
        with pytest.raises(ValueError, match="tags"):
            Entry.from_markdown(text)

    def test_extract_rejects_oversized_file_before_reading(self, tmp_ohkb_dir):
        large = tmp_ohkb_dir / "large.txt"
        with large.open("wb") as file:
            file.seek(MAX_EXTRACT_BYTES)
            file.write(b"x")
        with pytest.raises(ValueError, match="extraction limit"):
            extract_file(large)

    def test_search_and_tree_resource_limits(self, kb):
        assert kb.search("   ") == []
        with pytest.raises(ValueError, match="Limit"):
            kb.search("x", limit=101)
        with pytest.raises(ValueError, match="Depth"):
            kb.tree(depth=21)
