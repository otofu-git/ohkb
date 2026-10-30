"""MCP server for ohkb -- exposes the knowledge base as tools, resources, and prompts.

Three modes control which tools are available:

    readonly    -- search, get, tree, status, lint, reindex (CS bot)
    managed     -- adds learn, edit, meta, forget, restore with confirmation (CS admin)
    autonomous  -- full access, no confirmation needed (personal assistant)

Usage:
    ohkb serve                          # autonomous mode, local stdio transport
    ohkb serve --mode readonly          # read-only
    ohkb serve --mode managed           # write with confirmation prompts

The server intentionally exposes no HTTP transport.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from ohkb.index import read_index, refresh_index
from ohkb.kb import KnowledgeBase
from ohkb.store import Store

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
        "ohkb",
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


def _build_instructions(mode: Mode, index_content: str = "") -> str:
    """Build server-level instructions that describe the KB and the mode."""
    base = (
        "ohkb is a knowledge base for LLM agents. "
        "Knowledge is stored as atomic Markdown files with YAML frontmatter. "
        "Search uses SQLite FTS5 with BM25 ranking (title > tags > aliases > content weight). "
        "No embeddings — tags and aliases drive search quality.\n\n"
        "## MANDATORY WORKFLOW\n\n"
        "STEP 1 — ALWAYS call 'index' at the start of every conversation.\n"
        "         This shows what categories and entries exist in the KB.\n"
        "         Do NOT skip this step even if you think you know the KB.\n\n"
        "STEP 2 — Call 'search' with keywords from the user's question.\n"
        "         Any query word can match; entries matching more of it rank higher.\n\n"
        "STEP 3 — Call 'get' with the exact path from search results to read full content.\n"
        "         'get' takes a path like 'category/file.md', NOT a search query.\n\n"
    )

    if mode == "readonly":
        return base + (
            "MODE: Read-only. Tools: index, search, get, tree, status, lint, reindex, "
            "log, related, extract, source_list.\n"
            "Use index → search → get to answer questions."
        )
    elif mode == "managed":
        return base + (
            "MODE: Managed. Tools: index, search, get, tree, status, lint, reindex, "
            "log, related, extract, source_list, learn, edit, meta, forget, restore, "
            "source_add.\n\n"
            "Before ANY write (learn, edit, meta, forget, restore, source_add):\n"
            "1. Call 'search' to check for duplicates.\n"
            "2. Describe the proposed change to the user.\n"
            "3. Wait for explicit user confirmation.\n"
            "4. After writing, call 'index' to confirm the change."
        )
    else:  # autonomous
        return base + (
            "MODE: Autonomous. Full tools including learn, edit, meta, forget, restore, "
            "source_add.\n\n"
            "Before learn: call 'search' to avoid duplicates.\n"
            "After any write: call 'index' to confirm the change.\n"
            "Keep entries atomic (one concept, < 3000 chars).\n"
            "Provide 3-7 tags and key synonyms as aliases.\n"
            "Raw material: source_add → extract → you classify → learn."
        )


# ── Resources ───────────────────────────────────────────────────────────────


def _register_resources(mcp: FastMCP) -> None:
    """Register MCP resources (read-only data endpoints)."""

    @mcp.resource("ohkb://index")
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
        limit: int = 20,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Search the knowledge base using full-text search (BM25 ranked).

        PREREQUISITE: If you have not called 'index' yet in this conversation,
        call 'index' FIRST to understand the KB structure, then come back to search.

        Searches titles, tags, aliases, and content.
        Returns a list of matching entries with path, title, tags, and score.

        NEXT STEP: Use 'get' with the returned path to read the full content.
        Example: search("pricing") → result has path "beusable/geo/pricing/geo-요금제.md"
                 → call get(path="beusable/geo/pricing/geo-요금제.md") to read it.

        If no results: retry with different keywords (synonyms, official names).
        Any query word can match; entries that match more of the query, especially in
        title/tags/aliases, rank higher. Korean is matched by character bigrams, so
        particles and spacing ('요금제를', '중소 기업') do not prevent a match.
        Category filter uses prefix matching: 'python' also returns 'python/internals' entries.

        Args:
            query: The question or keywords. Words are OR-matched and ranked by BM25.
            category: Optional category prefix to narrow results.
            limit: Maximum number of results (default 20).
        """
        kb = _kb(ctx)
        cat = category if category else None
        lim = limit if limit >= 1 else 20
        results = await asyncio.to_thread(kb.search, query, category=cat, limit=lim)
        if not results:
            return "No results found."
        return _fmt(results)

    @mcp.tool()
    async def get(
        path: str,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Read the full content of a knowledge entry by its exact path.

        Use this after 'search' to read the detailed content of a specific entry.
        Returns the file with line numbers and character count.

        IMPORTANT: 'path' must be the exact path from search results,
        e.g. 'beusable/geo/pricing/geo-요금제.md'. Do NOT pass a search query here.

        Args:
            path: Exact relative path from search results, e.g. 'category/file.md'.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.get, path)

        # Format as numbered lines with header
        header = f"=== {result['path']} ({result['chars']} chars, {result['lines']} lines) ==="
        numbered = [f"{i:>4}: {line}" for i, line in enumerate(result["content"], 1)]
        return header + "\n" + "\n".join(numbered)

    @mcp.tool()
    async def index(
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Read the knowledge base index. ALWAYS call this before search or any other tool.

        Required first step for every conversation. Shows all available categories,
        entries, tags, and file sizes so you know what to search for.
        Without this, you cannot know what knowledge exists in the knowledge base.

        Call this before: search, get, learn, edit, meta, forget.
        Keywords: knowledge base overview, what's available, list all, explore, browse,
                  index, categories, entries, search preparation, knowledge base search.
        """
        return read_index()

    @mcp.tool()
    async def tree(
        path: str = "",
        depth: int = 2,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Browse the knowledge base structure (categories and file list).

        Use this to understand what topics exist before searching.
        Returns category names and entry filenames — use 'get' with a path to read content.

        Args:
            path: Optional category path to zoom into (e.g. 'python' or 'python/internals').
                  Empty string = wiki root.
            depth: How many directory levels to expand (default 2). Directories deeper
                   than this appear as truncated; call again with a deeper path.
        """
        kb = _kb(ctx)
        d = depth if depth >= 1 else 2
        result = await asyncio.to_thread(kb.tree, path, depth=d)
        return _fmt(result)

    @mcp.tool()
    async def status(
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Show knowledge base statistics.

        Returns entry counts, file counts, in_sync flag, category list, and data directory path.
        If in_sync is false, run 'reindex'.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.status)
        return _fmt(result)

    @mcp.tool()
    async def lint(
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Check knowledge base health.

        Reports issues: index/disk drift, oversized files (> 3000 chars), missing
        tags/aliases, invalid frontmatter, category mismatches, and empty categories.
        """
        kb = _kb(ctx)
        issues = await asyncio.to_thread(kb.lint)
        if not issues:
            return "No issues found."
        return _fmt(issues)

    @mcp.tool()
    async def reindex(
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Rebuild the search index from wiki files on disk.

        Files are the source of truth. Use when status reports in_sync=false,
        or after manual file edits outside ohkb.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.reindex)
        await asyncio.to_thread(refresh_index)
        return _fmt(result)

    @mcp.tool()
    async def log(
        limit: int = 50,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Read recent activity log lines (newest first)."""
        kb = _kb(ctx)
        lines = await asyncio.to_thread(kb.activity_log, limit)
        if not lines:
            return "Log is empty."
        return _fmt(lines)

    @mcp.tool()
    async def related(
        path: str,
        limit: int = 10,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """List entries that share tags with the given path (no embeddings)."""
        kb = _kb(ctx)
        items = await asyncio.to_thread(kb.related, path, limit=limit)
        if not items:
            return "No related entries."
        return _fmt(items)

    @mcp.tool()
    async def extract(
        target: str,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Extract plain text from a local file. Does not call an LLM.

        Use the returned text to decide category/tags, then call learn.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.extract, target)
        return _fmt(result)

    @mcp.tool()
    async def source_list(
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """List immutable raw files under sources/."""
        kb = _kb(ctx)
        items = await asyncio.to_thread(kb.source_list)
        if not items:
            return "No sources."
        return _fmt(items)


# ── Write Tools ─────────────────────────────────────────────────────────────


def _register_write_tools(mcp: FastMCP, managed: bool = False) -> None:
    """Register write tools (managed or autonomous mode).

    In managed mode, tool descriptions include confirmation guidance.
    In autonomous mode, tools execute without additional prompts.
    """

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
        """Store a new knowledge entry in the knowledge base.

        WORKFLOW: Always call 'search' first to check for duplicates before storing.

        Creates an atomic Markdown file with YAML frontmatter and indexes it for search.
        Keep content under 3000 characters (one fact per entry).
        Tags and aliases are critical — they drive search quality without embeddings.
        Provide 3-7 tags and key synonyms as aliases (comma-separated strings).
        Category supports nested paths (e.g. 'python/internals').

        Args:
            content: The knowledge content (plain text, under 3000 chars).
            title: Short descriptive title.
            category: Category path, e.g. 'python' or 'python/internals'.
            tags: Comma-separated tags, e.g. 'pricing,요금제,enterprise'.
            aliases: Comma-separated synonyms, e.g. 'GEO 가격,geo pricing'.
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
        """Edit a knowledge entry at the line level.

        Use 'get' first to see the file with line numbers, then specify the edit.
        Exactly one edit operation must be specified per call.

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
        """Update metadata of a knowledge entry without changing the content body.

        Use this to add/remove tags, aliases, change the title, move to a new category,
        or change entity type. Multiple operations can be done in a single call.

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
        """Archive a knowledge entry (soft delete).

        Moves the file to the archive directory and removes it from the search index.
        If the same path was archived before, a timestamped copy is kept.
        Use 'restore' to bring an entry back.

        Args:
            path: Relative path like 'category/file.md'.
            reason: Optional reason for archiving.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.forget, path, reason=reason)

        # Refresh index after mutation
        await asyncio.to_thread(refresh_index)

        return _fmt(result)

    @mcp.tool()
    async def restore(
        path: str = "",
        archive_path: str = "",
        overwrite: bool = False,
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Restore an archived knowledge entry back into the wiki.

        Provide either path (original wiki path — restores the latest archive)
        or archive_path (specific file under archive/).

        Args:
            path: Original wiki path, e.g. 'category/file.md'.
            archive_path: Specific archive-relative path if selecting a version.
            overwrite: Replace an existing wiki entry if present.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(
            kb.restore,
            path or None,
            archive_path=archive_path or None,
            overwrite=overwrite,
        )
        await asyncio.to_thread(refresh_index)
        return _fmt(result)

    @mcp.tool()
    async def source_add(
        target: str,
        name: str = "",
        ctx: Context[ServerSession, AppContext] = None,  # type: ignore[assignment]
    ) -> str:
        """Copy an immutable local file under sources/.

        Does not create wiki entries. Use extract + learn after intake.
        """
        kb = _kb(ctx)
        result = await asyncio.to_thread(kb.source_add, target, name=name or None)
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
            f"Research the topic '{topic}' in the ohkb knowledge base.\n\n"
            "Steps:\n"
            "1. Read ohkb://index to understand the KB structure.\n"
            "2. Search with relevant keywords; if no results, retry with synonyms or tags.\n"
            "3. Use get to read the full content of the most relevant entries.\n"
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
            "knowledge entry in ohkb.\n\n"
            "Rules:\n"
            "- Search first to avoid duplicates.\n"
            "- One fact = one entry (keep under 3000 chars).\n"
            "- Provide 3-7 tags and key synonyms as aliases.\n"
            "- Reuse existing categories from the index; use nested paths for sub-topics.\n"
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
            f"Review and organize {scope} in ohkb.\n\n"
            "Steps:\n"
            "1. Run lint to find issues.\n"
            "2. Fix missing tags or aliases (aim for 3-7 tags, key synonyms as aliases).\n"
            "3. Split oversized entries (> 3000 chars) into atomic facts.\n"
            "4. Check for duplicate or near-duplicate entries.\n"
            "5. Consider nesting flat categories (e.g. many 'python' entries → 'python/stdlib').\n"
            "6. Report a summary of changes made."
        )
