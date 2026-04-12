"""orag CLI -- knowledge base for LLM agents."""

from __future__ import annotations

import json
import sys

import click

from orag import __version__
from orag.kb import KnowledgeBase


def _json_out(data: dict | list) -> None:
    """Print JSON to stdout."""
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


def _get_kb() -> KnowledgeBase:
    return KnowledgeBase()


def _split_csv(val: str | None) -> list[str] | None:
    """Split a comma-separated string into a list, or return None."""
    if val is None:
        return None
    return [v.strip() for v in val.split(",") if v.strip()]


# ── Main group ──────────────────────────────────────────────────────────────


@click.group()
@click.version_option(__version__, prog_name="orag")
def main() -> None:
    """orag -- A knowledge base for LLM agents."""


# ── search ──────────────────────────────────────────────────────────────────


@main.command()
@click.argument("query")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("-c", "--category", default=None, help="Filter by category.")
def search(query: str, as_json: bool, category: str | None) -> None:
    """Search the knowledge base."""
    kb = _get_kb()
    results = kb.search(query, category=category)

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
@click.option("-f", "--file", "from_file", type=click.Path(exists=True), help="Read content from file.")
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
        raise SystemExit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    # Print warnings to stderr
    for w in result.get("warnings", []):
        click.echo(f"Warning: {w}", err=True)

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
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

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
            raise SystemExit(1)

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
        raise SystemExit(1)

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
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

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
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if as_json:
        _json_out(result)
    else:
        click.echo(f"Archived: {result['path']}")


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
            click.echo(f"{prefix}  {name}/  ...  (run: orag tree {full_path} --depth {depth})")
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
    '...' with a hint to drill down using 'orag tree <path>'.

    Examples:

      orag tree                  # root, 2 levels deep
      orag tree python           # zoom into python category
      orag tree python --depth 3 # expand deeper
    """
    kb = _get_kb()
    try:
        result = kb.tree(path, depth=depth)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

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


# ── serve ───────────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--mode",
    type=click.Choice(["readonly", "managed", "autonomous"]),
    default="autonomous",
    help="Server mode: readonly (read only), managed (write with confirmation), autonomous (full access).",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "streamable-http"]),
    default="stdio",
    help="MCP transport protocol.",
)
@click.option("--port", type=int, default=8000, help="Port for HTTP transport.")
@click.option("--host", default="127.0.0.1", help="Host for HTTP transport.")
def serve(mode: str, transport: str, port: int, host: str) -> None:
    """Start the MCP server."""
    try:
        from orag.serve import create_server
    except ImportError:
        click.echo(
            "Error: MCP dependencies not installed.\n"
            "Install with: pip install orag[serve]",
            err=True,
        )
        raise SystemExit(1)

    import os

    os.environ["ORAG_MODE"] = mode
    server = create_server(mode=mode)

    if transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
