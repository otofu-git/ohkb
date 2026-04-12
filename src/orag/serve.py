"""MCP server for orag -- exposes the knowledge base as tools, resources, and prompts.

Three modes control which tools are available:

    readonly    -- search, get, tree, status, lint only (CS bot)
    managed     -- adds learn, edit, meta, forget with confirmation guidance (CS admin)
    autonomous  -- full access, no confirmation needed (personal assistant)

Usage:
    orag serve                          # autonomous mode, stdio transport
    orag serve --mode readonly          # read-only
    orag serve --mode managed           # write with confirmation prompts
    orag serve --transport streamable-http --port 9000
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from orag.index import read_index, refresh_index
from orag.kb import KnowledgeBase
from orag.store import Store

# ── Types ───────────────────────────────────────────────────────────────────

MODES = ("readonly", "managed", "autonomous")
Mode = str  # one of MODES


@dataclass
class AppContext:
    """Shared state available to all MCP tool handlers via ctx.request_context.lifespan_context."""

    kb: KnowledgeBase
    mode: Mode


# ── Lifespan ────────────────────────────────────────────────────────────────


def _make_lifespan(mode: Mode):
    """Create a lifespan context manager that initializes the KnowledgeBase."""

    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
        store = Store()
        kb = KnowledgeBase(store)

        # Generate/refresh _index.md at startup
        await asyncio.to_thread(refresh_index)

        try:
            yield AppContext(kb=kb, mode=mode)
        finally:
            store.close()

    return app_lifespan


# ── Helpers ─────────────────────────────────────────────────────────────────


def _kb(ctx: Context[ServerSession, AppContext]) -> KnowledgeBase:
    """Extract the KnowledgeBase from the MCP context."""
    return ctx.request_context.lifespan_context.kb


def _mode(ctx: Context[ServerSession, AppContext]) -> Mode:
    """Extract the current mode from the MCP context."""
    return ctx.request_context.lifespan_context.mode


def _fmt(data: dict | list) -> str:
    """Serialize to compact JSON for tool responses."""
    return json.dumps(data, ensure_ascii=False, indent=2)


# ── Server Factory ──────────────────────────────────────────────────────────


def create_server(mode: Mode = "autonomous") -> FastMCP:
    """Create and configure the MCP server with tools based on the given mode.

    Args:
        mode: One of 'readonly', 'managed', 'autonomous'.

    Returns:
        A configured FastMCP instance ready to run.
    """
    if mode not in MODES:
        raise ValueError(f"Invalid mode: {mode!r}. Must be one of {MODES}")

    instructions = _build_instructions(mode)
    mcp = FastMCP(
        "orag",
        instructions=instructions,
        lifespan=_make_lifespan(mode),
    )

    # Always register read tools and resources
    _register_resources(mcp)
    _register_read_tools(mcp)
    _register_prompts(mcp)

    # Register write tools for managed and autonomous modes
    if mode in ("managed", "autonomous"):
        managed = mode == "managed"
        _register_write_tools(mcp, managed=managed)

    return mcp


def _build_instructions(mode: Mode) -> str:
    """Build server-level instructions that describe the KB and the mode."""
    base = (
        "orag is a knowledge base for LLM agents. "
        "Knowledge is stored as atomic Markdown files with YAML frontmatter. "
        "Search uses SQLite FTS5 (BM25 ranking) over titles, tags, aliases, and content. "
        "No embeddings or vector database is used.\n\n"
        "WORKFLOW: Always start by reading the orag://index resource to understand "
        "the knowledge base structure. Then use the search tool to find relevant entries, "
        "and the get tool to read full content.\n\n"
    )

    if mode == "readonly":
        return base + (
            "MODE: Read-only. You can search and read knowledge but cannot modify it. "
            "Use search and get to find and retrieve information to answer questions."
        )
    elif mode == "managed":
        return base + (
            "MODE: Managed. You can read and write knowledge. "
            "Before making any changes (learn, edit, meta, forget), you MUST:\n"
            "1. Search for related/duplicate entries first.\n"
            "2. Describe the proposed change to the user.\n"
            "3. Wait for explicit user confirmation before executing.\n"
            "4. After changes, check if the _index needs refreshing.\n"
            "5. Look for related entries that might also need updates."
        )
    else:  # autonomous
        return base + (
            "MODE: Autonomous. You have full read/write access. "
            "You can search, read, create, edit, and archive knowledge freely. "
            "Search for duplicates before creating new entries. "
            "Keep entries atomic (< 3000 chars). Always provide good tags and aliases. "
            "After mutations, related entries may need updates too."
        )


# ── Resources ───────────────────────────────────────────────────────────────


def _register_resources(mcp: FastMCP) -> None:
    """Register MCP resources (read-only data endpoints)."""

    @mcp.resource("orag://index")
    def index_resource() -> str:
        """Knowledge base index -- read this first to understand what knowledge is available.

        Returns a structured summary of all categories, entries, tags, and file sizes.
        Use this to orient yourself before searching or reading specific entries.
        """
        return read_index()


# ── Read Tools ──────────────────────────────────────────────────────────────


def _register_read_tools(mcp: FastMCP) -> None:
    """Register read-only tools (available in all modes)."""

    @mcp.tool()
    async def search(
        query: str,
        category: str = "",
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Search the knowledge base using full-text search.

        Uses SQLite FTS5 with BM25 ranking. Searches across titles, tags, aliases, and content.
        Returns matching entries with paths, titles, tags, and relevance scores.

        Args:
            query: Search query text. Queries are phrase-matched for safety;
                special FTS5 operators (AND, OR, NOT, prefix*) are not supported.
            category: Optional category filter to narrow results.
        """
        kb = _kb(ctx)
        cat = category if category else None
        results = await asyncio.to_thread(kb.search, query, category=cat)
        if not results:
            return "No results found."
        return _fmt(results)

    @mcp.tool()
    async def get(
        path: str,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Read a knowledge entry with line numbers, character count, and line count.

        Returns the full file content with metadata about size. Use this after
        search to read the detailed content of a specific entry.

        The char count helps you gauge document size (recommended max: 3000 chars).

        Args:
            path: Relative path like 'category/file.md'.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.get, path)

        # Format as numbered lines with header
        header = f"=== {result['path']} ({result['chars']} chars, {result['lines']} lines) ==="
        numbered = [f"{i:>4}: {line}" for i, line in enumerate(result["content"], 1)]
        return header + "\n" + "\n".join(numbered)

    @mcp.tool()
    async def tree(
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Browse the knowledge base structure.

        Returns all categories and their entries. Use this to understand
        the organization of the knowledge base.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.tree)
        return _fmt(result)

    @mcp.tool()
    async def status(
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Show knowledge base statistics.

        Returns entry counts, file counts, category list, and data directory path.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.status)
        return _fmt(result)

    @mcp.tool()
    async def lint(
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Check knowledge base health.

        Reports issues: oversized files (> 3000 chars), missing tags/aliases,
        invalid frontmatter, and empty categories.
        """
        kb = _kb(ctx)
        issues = await asyncio.to_thread(kb.lint)
        if not issues:
            return "No issues found."
        return _fmt(issues)


# ── Write Tools ─────────────────────────────────────────────────────────────


def _register_write_tools(mcp: FastMCP, managed: bool = False) -> None:
    """Register write tools (managed or autonomous mode).

    In managed mode, tool descriptions include confirmation guidance.
    In autonomous mode, tools execute without additional prompts.
    """

    confirm_note = (
        "\n\nIMPORTANT (managed mode): Before executing, describe the proposed "
        "change to the user and wait for confirmation. Also search for related "
        "entries that might need updates."
        if managed
        else ""
    )

    @mcp.tool()
    async def learn(
        content: str,
        title: str,
        category: str,
        tags: str = "",
        aliases: str = "",
        entity_type: str = "concept",
        source: str = "manual",
        overwrite: bool = False,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        f"""Store a new knowledge entry in the knowledge base.

        Creates an atomic Markdown file with YAML frontmatter and indexes it for search.
        Always search first to avoid duplicates. Keep content under 3000 characters.
        Tags and aliases are critical for search quality -- always provide them.{confirm_note}

        Args:
            content: The knowledge content (plain text or Markdown).
            title: Entry title (used for filename generation).
            category: Category directory name.
            tags: Comma-separated keywords for search.
            aliases: Comma-separated synonyms/alternative phrasings.
            entity_type: Type: concept, person, event, product, etc.
            source: Origin: manual, document, url.
            overwrite: If true, replace existing entry with same title/category.
        """
        kb = _kb(ctx)
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []

        result = await asyncio.to_thread(
            kb.learn,
            content=content,
            title=title,
            category=category,
            tags=tag_list,
            aliases=alias_list,
            entity_type=entity_type,
            source=source,
            overwrite=overwrite,
        )

        # Refresh index after mutation
        await asyncio.to_thread(refresh_index)

        return _fmt(result)

    @mcp.tool()
    async def edit(
        path: str,
        content: str = "",
        line: int | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        after: int | None = None,
        delete: int | None = None,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        f"""Edit a knowledge entry at the line level.

        Use 'get' first to see the file with line numbers, then specify the edit.
        Exactly one edit operation must be specified per call.{confirm_note}

        Args:
            path: Relative path like 'category/file.md'.
            content: New content for replace/insert operations.
            line: Replace this single line number (1-indexed).
            line_start: Start of line range to replace (use with line_end).
            line_end: End of line range to replace, inclusive (use with line_start).
            after: Insert content after this line number.
            delete: Delete this line number.
        """
        kb = _kb(ctx)
        lines_tuple: tuple[int, int] | None = None
        if line_start is not None and line_end is not None:
            lines_tuple = (line_start, line_end)

        result = await asyncio.to_thread(
            kb.edit,
            path,
            line=line,
            lines=lines_tuple,
            after=after,
            delete=delete,
            content=content,
        )

        # Refresh index after mutation
        await asyncio.to_thread(refresh_index)

        return _fmt(result)

    @mcp.tool()
    async def meta(
        path: str,
        add_tags: str = "",
        remove_tags: str = "",
        add_aliases: str = "",
        remove_aliases: str = "",
        title: str = "",
        category: str = "",
        entity_type: str = "",
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        f"""Update metadata of a knowledge entry without changing the content body.

        Use this to add/remove tags, aliases, change the title, move to a new category,
        or change entity type. Multiple operations can be done in a single call.{confirm_note}

        Args:
            path: Relative path like 'category/file.md'.
            add_tags: Comma-separated tags to add.
            remove_tags: Comma-separated tags to remove.
            add_aliases: Comma-separated aliases to add.
            remove_aliases: Comma-separated aliases to remove.
            title: New title (empty string = no change).
            category: New category to move to (empty string = no change).
            entity_type: New entity type (empty string = no change).
        """
        kb = _kb(ctx)

        def _csv(s: str) -> list[str] | None:
            items = [v.strip() for v in s.split(",") if v.strip()] if s else []
            return items or None

        result = await asyncio.to_thread(
            kb.meta,
            path,
            add_tags=_csv(add_tags),
            remove_tags=_csv(remove_tags),
            add_aliases=_csv(add_aliases),
            remove_aliases=_csv(remove_aliases),
            title=title or None,
            category=category or None,
            entity_type=entity_type or None,
        )

        # Refresh index after mutation
        await asyncio.to_thread(refresh_index)

        return _fmt(result)

    @mcp.tool()
    async def forget(
        path: str,
        reason: str = "",
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        f"""Archive a knowledge entry (soft delete).

        Moves the file to the archive directory and removes it from the search index.
        The file is preserved in the archive and can be recovered manually if needed.{confirm_note}

        Args:
            path: Relative path like 'category/file.md'.
            reason: Optional reason for archiving.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.forget, path, reason=reason)

        # Refresh index after mutation
        await asyncio.to_thread(refresh_index)

        return _fmt(result)


# ── Prompts ─────────────────────────────────────────────────────────────────


def _register_prompts(mcp: FastMCP) -> None:
    """Register reusable prompt templates."""

    @mcp.prompt()
    def research(topic: str) -> str:
        """Research a topic using the knowledge base.

        Guides the LLM through a systematic search-and-read workflow.
        """
        return (
            f"Research the topic '{topic}' in the orag knowledge base.\n\n"
            "Steps:\n"
            "1. Read the orag://index resource to understand the KB structure.\n"
            "2. Use the search tool with relevant keywords to find matching entries.\n"
            "3. Use the get tool to read the full content of the most relevant entries.\n"
            "4. Synthesize a comprehensive answer citing specific entries.\n"
            "5. If information is incomplete, note what is missing."
        )

    @mcp.prompt()
    def learn_from_text(text: str) -> str:
        """Extract and store knowledge from a block of text.

        Guides the LLM to decompose text into atomic facts and store each one.
        """
        return (
            "Extract key facts from the following text and store each as a separate "
            "knowledge entry in orag.\n\n"
            "Rules:\n"
            "- Search first to avoid duplicates.\n"
            "- One fact = one entry (keep under 3000 chars).\n"
            "- Provide descriptive tags and aliases for each entry.\n"
            "- Choose an appropriate category.\n"
            "- Group related facts under the same category.\n\n"
            f"Text to process:\n\n{text}"
        )

    @mcp.prompt()
    def organize(category: str = "") -> str:
        """Review and organize the knowledge base.

        Guides the LLM through a lint-fix-improve workflow.
        """
        scope = f"category '{category}'" if category else "the entire knowledge base"
        return (
            f"Review and organize {scope} in orag.\n\n"
            "Steps:\n"
            "1. Run lint to find issues.\n"
            "2. Fix any missing tags or aliases.\n"
            "3. Split oversized entries (> 3000 chars) into atomic facts.\n"
            "4. Check for duplicate or near-duplicate entries.\n"
            "5. Ensure categories are logically organized.\n"
            "6. Report a summary of changes made."
        )
