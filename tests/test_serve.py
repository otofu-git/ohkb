"""Tests for the MCP server registration (no live transport required)."""

from __future__ import annotations

import asyncio
import os

import pytest

from ohkb.kb import KnowledgeBase
from ohkb.serve import MODES, _build_instructions, _make_lifespan, create_server


@pytest.fixture(autouse=True)
def tmp_ohkb_dir(tmp_path):
    os.environ["OHKB_DIR"] = str(tmp_path)
    yield tmp_path
    del os.environ["OHKB_DIR"]


def _tool_names(server) -> set[str]:
    """Collect registered tool names from a FastMCP server."""
    # FastMCP stores tools on the tool manager; support a few attribute layouts.
    tm = getattr(server, "_tool_manager", None) or getattr(server, "tool_manager", None)
    if tm is None:
        # Fall back to list_tools if available (async) — use internal dict.
        tools = getattr(server, "_tools", None)
        if tools is not None:
            return set(tools.keys())
        raise RuntimeError("Cannot introspect FastMCP tools")

    tools = getattr(tm, "_tools", None) or getattr(tm, "tools", None)
    if tools is None:
        raise RuntimeError("Cannot introspect FastMCP tool manager")
    return set(tools.keys())


class TestCreateServer:
    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            create_server(mode="bogus")

    def test_readonly_tools(self):
        server = create_server(mode="readonly")
        names = _tool_names(server)
        assert "search" in names
        assert "get" in names
        assert "tree" in names
        assert "status" in names
        assert "lint" in names
        assert "reindex" in names
        assert "index" in names
        assert "log" in names
        assert "related" in names
        assert "extract" in names
        assert "source_list" in names
        assert "learn" not in names
        assert "forget" not in names
        assert "restore" not in names
        assert "source_add" not in names

    def test_autonomous_has_write_tools(self):
        server = create_server(mode="autonomous")
        names = _tool_names(server)
        for expected in (
            "search",
            "get",
            "tree",
            "learn",
            "edit",
            "meta",
            "forget",
            "restore",
            "reindex",
            "log",
            "related",
            "extract",
            "source_list",
            "source_add",
        ):
            assert expected in names

    def test_managed_has_write_tools(self):
        server = create_server(mode="managed")
        names = _tool_names(server)
        assert "learn" in names
        assert "restore" in names
        assert "source_add" in names

    def test_all_modes_construct(self):
        for mode in MODES:
            server = create_server(mode=mode)
            assert server is not None


def _tool(server, name: str):
    tm = getattr(server, "_tool_manager", None) or getattr(server, "tool_manager", None)
    tools = getattr(tm, "_tools", None) or getattr(tm, "tools", None)
    return tools[name]


class TestSearchFirstWorkflow:
    def test_instructions_do_not_require_index(self):
        for mode in MODES:
            text = _build_instructions(mode)
            assert "MANDATORY" not in text
            assert "ALWAYS call 'index'" not in text
            assert "read it in full" in text
            assert "prefer the" in text and "most recently updated" in text
            assert "call 'index' to confirm" not in text

    def test_tool_descriptions(self):
        server = create_server(mode="readonly")
        assert "PREREQUISITE" not in _tool(server, "search").description
        index_tool = _tool(server, "index")
        assert "ALWAYS" not in index_tool.description
        assert "category" in index_tool.parameters["properties"]

    def test_startup_does_not_write_index_file(self, tmp_ohkb_dir):
        kb = KnowledgeBase()
        kb.learn("Fact.", title="Startup", category="test", tags=["t"])
        kb.close()

        async def start_and_stop():
            server = create_server(mode="readonly")
            async with _make_lifespan("readonly")(server):
                pass

        asyncio.run(start_and_stop())
        assert not (tmp_ohkb_dir / "wiki" / "_index.md").exists()
