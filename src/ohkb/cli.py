"""ohkb CLI -- knowledge base for LLM agents."""

from __future__ import annotations

import json
import sys

import click

from ohkb import __version__
from ohkb.kb import KnowledgeBase


def _json_out(data: dict | list) -> None:
    """Print JSON to stdout."""
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


def _get_kb() -> KnowledgeBase:
    return KnowledgeBase()


def _refresh_index() -> None:
    """Regenerate _index.md after a mutating CLI command."""
    from ohkb.index import refresh_index

    refresh_index()


def _split_csv(val: str | None) -> list[str] | None:
    """Split a comma-separated string into a list, or return None."""
    if val is None:
        return None
    return [v.strip() for v in val.split(",") if v.strip()]


# ── Main group ──────────────────────────────────────────────────────────────


@click.group()
@click.version_option(__version__, prog_name="ohkb")
def main() -> None:
    """ohkb — simple knowledge base for agents."""


# ── search ──────────────────────────────────────────────────────────────────


@main.command()
@click.argument("query")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("-c", "--category", default=None, help="Filter by category.")
@click.option(
    "--limit",
    type=int,
    default=20,
    show_default=True,
    help="Maximum number of results.",
)
def search(query: str, as_json: bool, category: str | None, limit: int) -> None:
    """Search the knowledge base."""
    if limit < 1:
        click.echo("Error: --limit must be >= 1.", err=True)
        raise SystemExit(1)

    kb = _get_kb()
    results = kb.search(query, category=category, limit=limit)

    if as_json:
        _json_out(results)
        return

    if not results:
        click.echo("No results found.")
        return

    for r in results:
        click.echo(f"  {r['path']:<40} score={r['score']:.1f}")
        tags = r.get("tags", "")
        if tags:
            click.echo(f"    tags: {tags}")
        aliases = r.get("aliases", "")
        if aliases:
            click.echo(f"    aliases: {aliases}")
        click.echo()


# ── learn ───────────────────────────────────────────────────────────────────


@main.command()
@click.argument("content", default="")
@click.option("-t", "--title", required=True, help="Entry title.")
@click.option("-c", "--category", required=True, help="Category name.")
@click.option("--tags", default="", help="Comma-separated tags.")
@click.option("--aliases", default="", help="Comma-separated aliases.")
@click.option("--entity-type", default="concept", help="Entity type.")
@click.option("--source", default="manual", help="Source: manual, document, url.")
@click.option("--overwrite", is_flag=True, help="Overwrite if exists.")
@click.option(
    "-f", "--file", "from_file", type=click.Path(exists=True), help="Read content from file."
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def learn(
    content: str,
    title: str,
    category: str,
    tags: str,
    aliases: str,
    entity_type: str,
    source: str,
    overwrite: bool,
    from_file: str | None,
    as_json: bool,
) -> None:
    """Store a new knowledge entry."""
    # Read content from file if specified
    if from_file:
        with open(from_file, encoding="utf-8") as f:
            content = f.read()

    # Read from stdin if no content and not a terminal
    if not content and not sys.stdin.isatty():
        content = sys.stdin.read()

    if not content.strip():
        click.echo("Error: No content provided.", err=True)
        raise SystemExit(1)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []

    kb = _get_kb()
    try:
        result = kb.learn(
            content=content,
            title=title,
            category=category,
            tags=tag_list,
            aliases=alias_list,
            entity_type=entity_type,
            source=source,
            overwrite=overwrite,
        )
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    # Print warnings to stderr
    for w in result.get("warnings", []):
        click.echo(f"Warning: {w}", err=True)

    _refresh_index()

    if as_json:
        _json_out(result)
    else:
        click.echo(f"Learned: {result['path']} ({result['chars']} chars)")


# ── get ─────────────────────────────────────────────────────────────────────


@main.command()
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def get(path: str, as_json: bool) -> None:
    """Read a knowledge entry with line numbers and char count."""
    kb = _get_kb()
    try:
        result = kb.get(path)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    if as_json:
        _json_out(result)
        return

    click.echo(f"=== {result['path']} ({result['chars']} chars, {result['lines']} lines) ===")
    for i, line in enumerate(result["content"], 1):
        click.echo(f"{i:>4}: {line}")


# ── edit ────────────────────────────────────────────────────────────────────


@main.command()
@click.argument("path")
@click.argument("content", default="")
@click.option("--line", type=int, help="Replace a single line (1-indexed).")
@click.option("--lines", help="Replace a range of lines, e.g. 10-12.")
@click.option("--after", type=int, help="Insert after this line number.")
@click.option("--delete", "delete_line_num", type=int, help="Delete this line.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def edit(
    path: str,
    content: str,
    line: int | None,
    lines: str | None,
    after: int | None,
    delete_line_num: int | None,
    as_json: bool,
) -> None:
    """Edit a knowledge entry at the line level."""
    # Parse --lines "10-12" into a tuple
    lines_tuple: tuple[int, int] | None = None
    if lines is not None:
        parts = lines.split("-")
        if len(parts) != 2:
            click.echo("Error: --lines format must be START-END, e.g. 10-12", err=True)
            raise SystemExit(1)
        try:
            lines_tuple = (int(parts[0]), int(parts[1]))
        except ValueError:
            click.echo("Error: --lines values must be integers.", err=True)
            raise SystemExit(1) from None

    kb = _get_kb()
    try:
        result = kb.edit(
            path,
            line=line,
            lines=lines_tuple,
            after=after,
            delete=delete_line_num,
            content=content,
        )
    except (FileNotFoundError, IndexError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    _refresh_index()

    if as_json:
        _json_out(result)
    else:
        click.echo(f"Edited: {result['path']} ({result['action']}, {result['chars']} chars)")


# ── meta ────────────────────────────────────────────────────────────────────


@main.command()
@click.argument("path")
@click.option("--add-tags", default=None, help="Comma-separated tags to add.")
@click.option("--remove-tags", default=None, help="Comma-separated tags to remove.")
@click.option("--add-aliases", default=None, help="Comma-separated aliases to add.")
@click.option("--remove-aliases", default=None, help="Comma-separated aliases to remove.")
@click.option("--title", default=None, help="New title.")
@click.option("--category", default=None, help="Move to new category.")
@click.option("--entity-type", default=None, help="New entity type.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def meta(
    path: str,
    add_tags: str | None,
    remove_tags: str | None,
    add_aliases: str | None,
    remove_aliases: str | None,
    title: str | None,
    category: str | None,
    entity_type: str | None,
    as_json: bool,
) -> None:
    """Update metadata of a knowledge entry."""
    kb = _get_kb()
    try:
        result = kb.meta(
            path,
            add_tags=_split_csv(add_tags),
            remove_tags=_split_csv(remove_tags),
            add_aliases=_split_csv(add_aliases),
            remove_aliases=_split_csv(remove_aliases),
            title=title,
            category=category,
            entity_type=entity_type,
        )
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    _refresh_index()

    if as_json:
        _json_out(result)
    else:
        click.echo(f"Updated: {result['path']}")


# ── forget ──────────────────────────────────────────────────────────────────


@main.command()
@click.argument("path")
@click.option("--reason", default="", help="Reason for archiving.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def forget(path: str, reason: str, as_json: bool) -> None:
    """Archive a knowledge entry."""
    kb = _get_kb()
    try:
        result = kb.forget(path, reason=reason)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    _refresh_index()

    if as_json:
        _json_out(result)
    else:
        click.echo(f"Archived: {result['path']}")


# ── restore ─────────────────────────────────────────────────────────────────


@main.command()
@click.argument("path", required=False, default=None)
@click.option(
    "--archive",
    "archive_path",
    default=None,
    help="Specific archive-relative path to restore.",
)
@click.option("--overwrite", is_flag=True, help="Overwrite if the wiki entry exists.")
@click.option("--list", "list_only", is_flag=True, help="List archives instead of restoring.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def restore(
    path: str | None,
    archive_path: str | None,
    overwrite: bool,
    list_only: bool,
    as_json: bool,
) -> None:
    """Restore an archived knowledge entry.

    Examples:

      ohkb restore test/temp.md           # latest archive for that path
      ohkb restore --archive test/temp.md # specific archive file
      ohkb restore --list                 # list all archives
      ohkb restore test/temp.md --list    # list archives for one path
    """
    kb = _get_kb()

    if list_only:
        items = kb.list_archives(path)
        if as_json:
            _json_out(items)
            return
        if not items:
            click.echo("No archives found.")
            return
        for item in items:
            click.echo(f"  {item['path']:<50} original={item['original']}")
        return

    if not path and not archive_path:
        click.echo(
            "Error: specify PATH (original wiki path) or --archive.",
            err=True,
        )
        raise SystemExit(1)

    try:
        result = kb.restore(
            path,
            archive_path=archive_path,
            overwrite=overwrite,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    _refresh_index()

    if as_json:
        _json_out(result)
    else:
        click.echo(f"Restored: {result['path']} (from {result['restored_from']})")


# ── tree ────────────────────────────────────────────────────────────────────


def _render_tree(node: dict, indent: int, path_prefix: str, depth: int) -> None:
    """Recursively render a tree node to stdout."""
    prefix = "  " * indent
    for name, child in sorted(node.items()):
        if child is None:
            # File leaf
            click.echo(f"{prefix}  {name}")
        elif isinstance(child, dict) and child.get("_truncated"):
            # Directory truncated by depth limit
            full_path = f"{path_prefix}/{name}".lstrip("/")
            click.echo(f"{prefix}  {name}/  ...  (run: ohkb tree {full_path} --depth {depth})")
        else:
            # Expanded directory
            click.echo(f"{prefix}  {name}/")
            _render_tree(child, indent + 1, f"{path_prefix}/{name}", depth)


@main.command()
@click.argument("path", default="")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--depth", default=2, show_default=True, help="How many levels deep to expand.")
def tree(path: str, as_json: bool, depth: int) -> None:
    """Browse the knowledge structure.

    Expands up to DEPTH levels. Directories deeper than that are shown as
    '...' with a hint to drill down using 'ohkb tree <path>'.

    Examples:

      ohkb tree                  # root, 2 levels deep
      ohkb tree python           # zoom into python category
      ohkb tree python --depth 3 # expand deeper
    """
    kb = _get_kb()
    try:
        result = kb.tree(path, depth=depth)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    if as_json:
        _json_out(result)
        return

    nodes = result["tree"]
    if not nodes:
        click.echo("Knowledge base is empty." if not path else f"No entries found under '{path}'.")
        return

    root_label = result["path"]
    click.echo(f"{root_label}  (depth={depth})")
    _render_tree(nodes, indent=0, path_prefix=path, depth=depth)


# ── status ──────────────────────────────────────────────────────────────────


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def status(as_json: bool) -> None:
    """Show knowledge base statistics."""
    kb = _get_kb()
    info = kb.status()

    if as_json:
        _json_out(info)
        return

    click.echo(f"Entries:    {info['indexed_entries']}")
    click.echo(f"Files:      {info['files_on_disk']}")
    sync = "yes" if info.get("in_sync", True) else "NO — run: ohkb reindex"
    click.echo(f"In sync:    {sync}")
    click.echo(f"Categories: {', '.join(info['categories']) if info['categories'] else '(none)'}")
    click.echo(f"Data dir:   {info['data_dir']}")


# ── lint ────────────────────────────────────────────────────────────────────


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def lint(as_json: bool) -> None:
    """Check knowledge base health."""
    kb = _get_kb()
    issues = kb.lint()

    if as_json:
        _json_out(issues)
        return

    if not issues:
        click.echo("No issues found.")
        return

    for issue in issues:
        level = issue["level"].upper()
        click.echo(f"  [{level}] {issue['path']}: {issue['detail']}")

    click.echo(f"\n{len(issues)} issue(s) found.")


# ── reindex ─────────────────────────────────────────────────────────────────


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def reindex(as_json: bool) -> None:
    """Rebuild the search index from wiki files on disk.

    Files are the source of truth. Use after manual edits or when status
    reports the index is out of sync.
    """
    kb = _get_kb()
    result = kb.reindex()
    _refresh_index()

    if as_json:
        _json_out(result)
        return

    click.echo(f"Reindexed {result['indexed']} entries.")
    for err in result.get("errors", []):
        click.echo(f"  Error {err['path']}: {err['error']}", err=True)
    if result["status"] != "ok":
        raise SystemExit(1)


# ── index ───────────────────────────────────────────────────────────────────


@main.command("index")
def index_cmd() -> None:
    """Show the auto-generated knowledge base index (_index.md)."""
    from ohkb.index import read_index

    click.echo(read_index())


# ── init ────────────────────────────────────────────────────────────────────


@main.command("init")
@click.option("--force", is_flag=True, help="Overwrite log header and agent schema.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def init_cmd(force: bool, as_json: bool) -> None:
    """Scaffold the data directory, sources/, log, and agent schema."""
    kb = _get_kb()
    result = kb.init(force=force)
    if as_json:
        _json_out(result)
    else:
        click.echo(f"Initialized: {result['data_dir']}")
        click.echo(f"  wiki:    {result['wiki']}")
        click.echo(f"  sources: {result['sources']}")
        click.echo(f"  archive: {result['archive']}")
        click.echo(f"  log:     {result['log']}")
        click.echo(f"  schema:  {result['agent_schema']}")


# ── source ──────────────────────────────────────────────────────────────────


@main.group()
def source() -> None:
    """Manage immutable raw sources (optional intake layer)."""


@source.command("add")
@click.argument("target")
@click.option("--name", default=None, help="Destination filename under sources/.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def source_add(target: str, name: str | None, as_json: bool) -> None:
    """Copy a local file into sources/."""
    kb = _get_kb()
    try:
        result = kb.source_add(target, name=name)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None
    if as_json:
        _json_out(result)
    else:
        click.echo(f"Source added: {result['path']} ({result['bytes']} bytes)")


@source.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def source_list(as_json: bool) -> None:
    """List files under sources/."""
    kb = _get_kb()
    items = kb.source_list()
    if as_json:
        _json_out(items)
        return
    if not items:
        click.echo("No sources.")
        return
    for item in items:
        click.echo(f"  {item['path']:<50} {item['bytes']} bytes")


# ── extract ─────────────────────────────────────────────────────────────────


@main.command("extract")
@click.argument("target")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def extract_cmd(target: str, as_json: bool) -> None:
    """Extract plain text from a local file (no LLM)."""
    kb = _get_kb()
    try:
        result = kb.extract(target)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None
    if as_json:
        _json_out(result)
    else:
        click.echo(result["text"])


# ── log ─────────────────────────────────────────────────────────────────────


@main.command("log")
@click.option("--limit", type=int, default=50, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def log_cmd(limit: int, as_json: bool) -> None:
    """Show recent activity log entries."""
    kb = _get_kb()
    lines = kb.activity_log(limit=limit)
    if as_json:
        _json_out(lines)
        return
    if not lines:
        click.echo("Log is empty.")
        return
    for line in lines:
        click.echo(line)


# ── related ─────────────────────────────────────────────────────────────────


@main.command("related")
@click.argument("path")
@click.option("--limit", type=int, default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def related_cmd(path: str, limit: int, as_json: bool) -> None:
    """List entries that share tags with PATH."""
    kb = _get_kb()
    try:
        items = kb.related(path, limit=limit)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None
    if as_json:
        _json_out(items)
        return
    if not items:
        click.echo("No related entries.")
        return
    for item in items:
        click.echo(f"  {item['path']:<40} shared_tags={item['shared_tags']}")


# ── serve ───────────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--mode",
    type=click.Choice(["readonly", "managed", "autonomous"]),
    default="autonomous",
    help=(
        "Server mode: readonly (read only), managed (write with confirmation),"
        " autonomous (full access)."
    ),
)
def serve(mode: str) -> None:
    """Start the local MCP stdio server."""
    try:
        from ohkb.serve import create_server
    except ImportError:
        click.echo(
            "Error: MCP dependencies not installed.\nInstall with: pip install ohkb[serve]",
            err=True,
        )
        raise SystemExit(1) from None

    import os

    os.environ["OHKB_MODE"] = mode
    server = create_server(mode=mode)
    click.echo(f"ohkb MCP server starting (mode={mode}, transport=stdio) ...", err=True)
    click.echo("Waiting for MCP client on stdin. Press Ctrl+C to stop.", err=True)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
