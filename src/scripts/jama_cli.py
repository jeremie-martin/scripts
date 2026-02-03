#!/usr/bin/env python3
"""Unified Jama CLI with subcommands for fetch, update, create, and database management."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Annotated, Any

import typer

app = typer.Typer(
    help="Unified Jama CLI - fetch, update, create items and manage local database.",
    no_args_is_help=True,
)


# =============================================================================
# Fetch subcommand
# =============================================================================


@app.command()
def fetch(
    keys: Annotated[list[str], typer.Argument(help="Jama document keys or container keys")],
    fields: Annotated[str | None, typer.Option("--fields", "-f", help="Comma-separated fields to show")] = None,
    full: Annotated[bool, typer.Option("--full", help="Show all fields")] = False,
    url: Annotated[bool, typer.Option("--url", help="Include Jama URL for each item")] = False,
    links: Annotated[str | None, typer.Option("--links", "-l", help="Include links: 'all', 'upstream', or 'downstream'")] = None,
    format: Annotated[str, typer.Option("--format", help="Output format: tree, path, nested, json, flat")] = "path",
    no_clipboard: Annotated[bool, typer.Option("--no-clipboard", help="Don't copy output to clipboard")] = False,
):
    """Fetch Jama items with configurable field selection and output formats."""
    # Build args for jamafetch
    args = ["jamafetch"]
    args.extend(keys)

    if fields:
        args.extend(["--fields", fields])
    if full:
        args.append("--full")
    if url:
        args.append("--url")
    if links is not None:
        args.extend(["--links", links])
    if format:
        args.extend(["--format", format])
    if no_clipboard:
        args.append("--no-clipboard")

    try:
        code = subprocess.call(args)
        raise typer.Exit(code)
    except FileNotFoundError:
        typer.echo("Error: jamafetch not found. Is it installed?", err=True)
        raise typer.Exit(127) from None


# =============================================================================
# Update subcommand
# =============================================================================


@app.command()
def update(
    doc_key: Annotated[str | None, typer.Argument(help="Document key to update (for single-item mode)")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d", help="Set description field")] = None,
    rationale: Annotated[str | None, typer.Option("--rationale", "-r", help="Set rationale field")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Set name field")] = None,
    json_data: Annotated[str | None, typer.Option("--json", "-j", help="JSON object with field updates")] = None,
    file: Annotated[Path | None, typer.Option("--file", "-F", help="JSON file with bulk updates")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite existing field values")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be updated")] = False,
):
    """
    Update Jama item fields.

    Single-item mode (new):
        jama update ABC-DI2-123 --description "New desc" --rationale "New rationale"
        jama update ABC-DI2-123 --json '{"description": "...", "rationale": "..."}'

    Bulk mode (existing functionality):
        jama update --file updates.json
    """
    from scripts.jama.common import load_jama
    from scripts.jamaupdate import update_item_fields

    # Validate arguments
    if file is not None:
        # Bulk mode - forward to existing jamaupdate
        args = ["jamaupdate", str(file)]
        if overwrite:
            args.append("--overwrite")
        if dry_run:
            args.append("--dry-run")
        try:
            code = subprocess.call(args)
            raise typer.Exit(code)
        except FileNotFoundError:
            typer.echo("Error: jamaupdate not found. Is it installed?", err=True)
            raise typer.Exit(127) from None

    # Single-item mode
    if not doc_key:
        typer.echo("Error: DOC_KEY required for single-item mode, or use --file for bulk mode", err=True)
        raise typer.Exit(1)

    # Build updates dict
    updates: dict[str, Any] = {}

    if json_data:
        try:
            updates = json.loads(json_data)
            if not isinstance(updates, dict):
                typer.echo("Error: --json must be a JSON object", err=True)
                raise typer.Exit(1)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: Invalid JSON: {e}", err=True)
            raise typer.Exit(1) from None

    # Add individual field options
    if description is not None:
        updates["description"] = description
    if rationale is not None:
        updates["rationale"] = rationale
    if name is not None:
        updates["name"] = name

    if not updates:
        typer.echo("Error: No fields to update. Use --description, --rationale, --name, or --json", err=True)
        raise typer.Exit(1)

    # Perform update
    try:
        jama = load_jama()
    except Exception as e:
        typer.echo(f"Jama auth error: {e}", err=True)
        raise typer.Exit(2) from None

    typer.echo(f"Updating: {doc_key}")
    if dry_run:
        typer.echo("[DRY RUN MODE - No changes will be made]")
    if overwrite:
        typer.echo("[OVERWRITE MODE - Existing values will be replaced]")
    typer.echo("-" * 60)

    success = update_item_fields(jama, doc_key, updates, overwrite=overwrite, dry_run=dry_run)

    if success:
        typer.echo("\nUpdate completed successfully")
        raise typer.Exit(0)
    else:
        typer.echo("\nUpdate failed", err=True)
        raise typer.Exit(1)


# =============================================================================
# Create subcommand
# =============================================================================

create_app = typer.Typer(help="Create new Jama items", no_args_is_help=True)
app.add_typer(create_app, name="create")


def _create_item(
    item_type: str,
    parent: str,
    name: str,
    description: str | None,
    fields_json: str | None,
    dry_run: bool,
):
    """Common creation logic."""
    from scripts.jama.create import create_item_cli

    fields = None
    if fields_json:
        try:
            fields = json.loads(fields_json)
        except json.JSONDecodeError as e:
            typer.echo(f"Error: Invalid JSON: {e}", err=True)
            raise typer.Exit(1) from None

    code = create_item_cli(
        item_type,
        parent,
        name,
        description=description,
        fields=fields,
        dry_run=dry_run,
    )
    raise typer.Exit(code)


@create_app.command("requirement")
def create_requirement(
    parent: Annotated[str, typer.Option("--parent", "-p", help="Parent container document key")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the new item")],
    description: Annotated[str | None, typer.Option("--description", "-d", help="Description")] = None,
    fields: Annotated[str | None, typer.Option("--fields", "-f", help="Additional fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created")] = False,
):
    """Create a new Requirement item."""
    _create_item("requirement", parent, name, description, fields, dry_run)


@create_app.command("req")
def create_req(
    parent: Annotated[str, typer.Option("--parent", "-p", help="Parent container document key")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the new item")],
    description: Annotated[str | None, typer.Option("--description", "-d", help="Description")] = None,
    fields: Annotated[str | None, typer.Option("--fields", "-f", help="Additional fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created")] = False,
):
    """Create a new Requirement item (alias for 'requirement')."""
    _create_item("requirement", parent, name, description, fields, dry_run)


@create_app.command("testcase")
def create_testcase(
    parent: Annotated[str, typer.Option("--parent", "-p", help="Parent container document key")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the new item")],
    description: Annotated[str | None, typer.Option("--description", "-d", help="Description")] = None,
    fields: Annotated[str | None, typer.Option("--fields", "-f", help="Additional fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created")] = False,
):
    """Create a new Test Case item."""
    _create_item("testcase", parent, name, description, fields, dry_run)


@create_app.command("tc")
def create_tc(
    parent: Annotated[str, typer.Option("--parent", "-p", help="Parent container document key")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the new item")],
    description: Annotated[str | None, typer.Option("--description", "-d", help="Description")] = None,
    fields: Annotated[str | None, typer.Option("--fields", "-f", help="Additional fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created")] = False,
):
    """Create a new Test Case item (alias for 'testcase')."""
    _create_item("testcase", parent, name, description, fields, dry_run)


@create_app.command("text")
def create_text(
    parent: Annotated[str, typer.Option("--parent", "-p", help="Parent container document key")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the new item")],
    description: Annotated[str | None, typer.Option("--description", "-d", help="Description")] = None,
    fields: Annotated[str | None, typer.Option("--fields", "-f", help="Additional fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created")] = False,
):
    """Create a new Text item."""
    _create_item("text", parent, name, description, fields, dry_run)


@create_app.command("txt")
def create_txt(
    parent: Annotated[str, typer.Option("--parent", "-p", help="Parent container document key")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the new item")],
    description: Annotated[str | None, typer.Option("--description", "-d", help="Description")] = None,
    fields: Annotated[str | None, typer.Option("--fields", "-f", help="Additional fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created")] = False,
):
    """Create a new Text item (alias for 'text')."""
    _create_item("text", parent, name, description, fields, dry_run)


# Generic create with type argument
@create_app.command("item")
def create_item_cmd(
    item_type: Annotated[str, typer.Argument(help="Item type (requirement, testcase, text, or actual type name)")],
    parent: Annotated[str, typer.Option("--parent", "-p", help="Parent container document key")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the new item")],
    description: Annotated[str | None, typer.Option("--description", "-d", help="Description")] = None,
    fields: Annotated[str | None, typer.Option("--fields", "-f", help="Additional fields as JSON")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created")] = False,
):
    """Create a new item of any type."""
    _create_item(item_type, parent, name, description, fields, dry_run)


# =============================================================================
# Database subcommand
# =============================================================================

db_app = typer.Typer(help="Manage local Jama database", no_args_is_help=True)
app.add_typer(db_app, name="db")


@db_app.command("sync")
def db_sync(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show detailed progress")] = True,
):
    """Sync database from Jama API (refresh item types and prefix mappings)."""
    from scripts.jama.common import load_jama
    from scripts.jama.database import sync_database

    try:
        jama = load_jama()
    except Exception as e:
        typer.echo(f"Jama auth error: {e}", err=True)
        raise typer.Exit(2) from None

    database = sync_database(jama, verbose=verbose)
    typer.echo(f"\nDatabase synced: {len(database.get('item_types', {}))} item types, {len(database.get('prefix_map', {}))} prefixes")


@db_app.command("show")
def db_show(
    prefixes: Annotated[bool, typer.Option("--prefixes", "-p", help="Show prefix mappings")] = False,
    types: Annotated[bool, typer.Option("--types", "-t", help="Show item types")] = False,
):
    """Show cached database contents."""
    from scripts.jama.database import DB_FILE, load_database

    database = load_database()

    typer.echo(f"Database: {DB_FILE}")
    typer.echo(f"Version: {database.get('version', 'unknown')}")
    typer.echo(f"Item types: {len(database.get('item_types', {}))}")
    typer.echo(f"Prefix mappings: {len(database.get('prefix_map', {}))}")
    typer.echo()

    # If neither flag specified, show both
    show_types = types or not (types or prefixes)
    show_prefixes = prefixes or not (types or prefixes)

    if show_types:
        typer.echo("Item Types:")
        typer.echo("-" * 40)
        for item_type_id, info in sorted(database.get("item_types", {}).items()):
            name = info.get("item_type_name", "Unknown")
            field_count = len(info.get("fields", {}))
            typer.echo(f"  {item_type_id}: {name} ({field_count} fields)")
        typer.echo()

    if show_prefixes:
        typer.echo("Prefix Mappings:")
        typer.echo("-" * 40)
        for prefix, info in sorted(database.get("prefix_map", {}).items()):
            project_id = info.get("project_id", "?")
            item_type_id = info.get("item_type_id", "?")
            typer.echo(f"  {prefix} -> project={project_id}, item_type={item_type_id}")


@db_app.command("migrate")
def db_migrate():
    """Migrate from old jamafetch database to new format."""
    from scripts.jama.database import migrate_from_v1, save_database

    database = migrate_from_v1()
    save_database(database)
    typer.echo(f"Migration complete: {len(database.get('item_types', {}))} item types migrated")


@db_app.command("path")
def db_path():
    """Show database file path."""
    from scripts.jama.database import DB_FILE

    typer.echo(str(DB_FILE))


# =============================================================================
# Aliases subcommand
# =============================================================================


# =============================================================================
# Links subcommands
# =============================================================================


# =============================================================================
# Trace subcommand
# =============================================================================


@app.command("trace")
def trace(
    keys: Annotated[list[str], typer.Argument(help="Jama document keys, container keys, or a file with keys")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file (.xlsx or .json)")] = None,
    fields: Annotated[str, typer.Option("--fields", "-f", help="Comma-separated fields")] = "name,description",
    upstream: Annotated[list[str] | None, typer.Option("--upstream", "-u", help="Filter upstream by pattern (repeatable)")] = None,
    downstream: Annotated[list[str] | None, typer.Option("--downstream", "-d", help="Filter downstream by pattern (repeatable)")] = None,
    format: Annotated[str, typer.Option("--format", help="Terminal output format: table or json")] = "table",
    no_timestamp: Annotated[bool, typer.Option("--no-timestamp", help="Don't timestamp output filename")] = False,
):
    """
    Build trace matrix for Jama items with upstream/downstream links.

    Creates a traceability matrix with columns: Upstream | Key | Fields... | Downstream

    Examples:
        jama trace ABC-FLD-164 -o matrix.xlsx
        jama trace ABC-REQ-1 -f name,description,ac,rationale
        jama trace keys.txt -u SWVER- -d TEST- --format json
        jama trace ABC-FLD-100 -u REQ- -u DI2- -d TC- -o full_matrix.xlsx
    """
    from scripts.jama.common import load_jama
    from scripts.jama.trace import build_trace_rows, expand_trace_keys, load_trace_keys
    from scripts.jama.trace_formatters import (
        TraceExcelFormatter,
        TraceJsonFormatter,
        TraceTableFormatter,
        timestamped_path,
    )

    try:
        jama = load_jama()
    except Exception as e:
        typer.echo(f"Jama auth error: {e}", err=True)
        raise typer.Exit(2) from None

    # Load and expand keys
    input_keys = load_trace_keys(list(keys))
    doc_keys = expand_trace_keys(jama, input_keys)

    if not doc_keys:
        typer.echo("No valid document keys to process.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Processing {len(doc_keys)} item(s)...", err=True)

    # Parse field names
    field_names = [f.strip() for f in fields.split(",") if f.strip()]

    # Show active filters
    if upstream:
        typer.echo(f"Upstream filter(s): {', '.join(upstream)}", err=True)
    if downstream:
        typer.echo(f"Downstream filter(s): {', '.join(downstream)}", err=True)

    # Build trace rows
    rows = build_trace_rows(
        jama,
        doc_keys,
        field_names=field_names,
        upstream_patterns=upstream,
        downstream_patterns=downstream,
    )

    if not rows:
        typer.echo("No data to export.", err=True)
        raise typer.Exit(1)

    # Output handling
    if output:
        output_path = Path(output)

        # Ensure .xlsx extension for Excel output
        if output_path.suffix.lower() not in (".xlsx", ".json"):
            output_path = output_path.with_suffix(".xlsx")

        # Add timestamp unless disabled
        if not no_timestamp:
            output_path = timestamped_path(output_path)

        if output_path.suffix.lower() == ".json":
            # JSON file output
            formatter = TraceJsonFormatter()
            output_path.write_text(formatter.format(rows, field_names))
        else:
            # Excel output
            formatter = TraceExcelFormatter()
            formatter.format(rows, field_names, output_path)

        typer.echo(f"Wrote {len(rows)} row(s) to: {output_path}")
    else:
        # Terminal output
        if format == "json":
            formatter = TraceJsonFormatter()
            typer.echo(formatter.format(rows, field_names))
        else:
            formatter = TraceTableFormatter()
            typer.echo(formatter.format(rows, field_names))


@app.command("links")
def get_links(
    keys: Annotated[list[str], typer.Argument(help="Jama document keys to query")],
    upstream: Annotated[bool, typer.Option("--upstream", "-u", help="Show only upstream links")] = False,
    downstream: Annotated[bool, typer.Option("--downstream", "-d", help="Show only downstream links")] = False,
    as_json: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """
    Get upstream and downstream links for Jama items.

    Examples:
        jama links ABC-SWVER-13              # Show all links
        jama links ABC-SWVER-13 --upstream   # Only upstream links
        jama links ABC-DI2-86 ABC-DI2-87     # Multiple items
        jama links ABC-SWVER-13 --json       # JSON output
    """
    from scripts.jama.common import load_jama
    from scripts.jama.links import format_links_json, format_links_table, get_item_links

    try:
        jama = load_jama()
    except Exception as e:
        typer.echo(f"Jama auth error: {e}", err=True)
        raise typer.Exit(2) from None

    # Determine what to show
    show_upstream = upstream or not (upstream or downstream)
    show_downstream = downstream or not (upstream or downstream)

    links_list = []
    for key in keys:
        typer.echo(f"Fetching links for {key}...", err=True)
        item_links = get_item_links(
            jama,
            key,
            include_upstream=show_upstream,
            include_downstream=show_downstream,
        )
        if item_links:
            links_list.append(item_links)
        else:
            typer.echo(f"Warning: '{key}' not found", err=True)

    if not links_list:
        typer.echo("No items found.", err=True)
        raise typer.Exit(1)

    if as_json:
        typer.echo(format_links_json(links_list))
    else:
        for i, links in enumerate(links_list):
            if i > 0:
                typer.echo("\n" + "-" * 60 + "\n")
            typer.echo(format_links_table(links, show_upstream=show_upstream, show_downstream=show_downstream))


@app.command("link-upstream")
def link_upstream_cmd(
    item: Annotated[str, typer.Argument(help="Item to add links to")],
    targets: Annotated[list[str], typer.Argument(help="Targets that become upstream of item")],
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview without creating links")] = False,
):
    """
    Create upstream links (targets become upstream of item).

    This makes item trace TO targets. Typically used to link a test case
    to requirements it verifies.

    Examples:
        jama link-upstream ABC-TC-1 ABC-REQ-1              # TC traces to REQ
        jama link-upstream ABC-TC-1 ABC-REQ-1 ABC-REQ-2    # Multiple targets
        jama link-upstream ABC-TC-1 ABC-REQ-1 --dry-run    # Preview
    """
    from scripts.jama.common import load_jama
    from scripts.jama.links import create_links_upstream, print_create_results

    try:
        jama = load_jama()
    except Exception as e:
        typer.echo(f"Jama auth error: {e}", err=True)
        raise typer.Exit(2) from None

    typer.echo(f"Creating upstream links: {item} -> {len(targets)} target(s)...")
    if dry_run:
        typer.echo("[DRY RUN MODE - No changes will be made]")
    typer.echo()

    results = create_links_upstream(jama, item, targets, dry_run=dry_run)
    print_create_results(results, dry_run=dry_run)

    errors = sum(1 for r in results if r["status"] == "error")
    if errors > 0:
        raise typer.Exit(1)


@app.command("link-downstream")
def link_downstream_cmd(
    item: Annotated[str, typer.Argument(help="Item to add links to")],
    targets: Annotated[list[str], typer.Argument(help="Targets that become downstream of item")],
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview without creating links")] = False,
):
    """
    Create downstream links (targets become downstream of item).

    This makes targets trace TO item. Typically used to link test cases
    to a requirement they verify.

    Examples:
        jama link-downstream ABC-REQ-1 ABC-TC-1              # TC traces to REQ
        jama link-downstream ABC-REQ-1 ABC-TC-1 ABC-TC-2     # Multiple targets
        jama link-downstream ABC-REQ-1 ABC-TC-1 --dry-run    # Preview
    """
    from scripts.jama.common import load_jama
    from scripts.jama.links import create_links_downstream, print_create_results

    try:
        jama = load_jama()
    except Exception as e:
        typer.echo(f"Jama auth error: {e}", err=True)
        raise typer.Exit(2) from None

    typer.echo(f"Creating downstream links: {item} <- {len(targets)} target(s)...")
    if dry_run:
        typer.echo("[DRY RUN MODE - No changes will be made]")
    typer.echo()

    results = create_links_downstream(jama, item, targets, dry_run=dry_run)
    print_create_results(results, dry_run=dry_run)

    errors = sum(1 for r in results if r["status"] == "error")
    if errors > 0:
        raise typer.Exit(1)


@app.command("unlink")
def unlink_cmd(
    item: Annotated[str, typer.Argument(help="Document key to unlink from")],
    targets: Annotated[list[str] | None, typer.Argument(help="Specific targets to unlink")] = None,
    all_upstream: Annotated[bool, typer.Option("--all-upstream", help="Remove all upstream links")] = False,
    all_downstream: Annotated[bool, typer.Option("--all-downstream", help="Remove all downstream links")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview without deleting")] = False,
):
    """
    Remove links from an item.

    Examples:
        jama unlink ABC-TC-1 ABC-REQ-1              # Remove specific link
        jama unlink ABC-TC-1 ABC-REQ-1 ABC-REQ-2    # Multiple targets
        jama unlink ABC-TC-1 --all-upstream         # Remove all upstream links
        jama unlink ABC-TC-1 --all-downstream       # Remove all downstream links
        jama unlink ABC-TC-1 ABC-REQ-1 --dry-run    # Preview
    """
    from scripts.jama.common import load_jama
    from scripts.jama.links import delete_all_links, delete_links, print_delete_results

    # Validate arguments
    if not targets and not all_upstream and not all_downstream:
        typer.echo("Error: Specify targets to unlink or use --all-upstream/--all-downstream", err=True)
        raise typer.Exit(1)

    if targets and (all_upstream or all_downstream):
        typer.echo("Error: Cannot specify both targets and --all-upstream/--all-downstream", err=True)
        raise typer.Exit(1)

    try:
        jama = load_jama()
    except Exception as e:
        typer.echo(f"Jama auth error: {e}", err=True)
        raise typer.Exit(2) from None

    if dry_run:
        typer.echo("[DRY RUN MODE - No changes will be made]")
    typer.echo()

    if targets:
        typer.echo(f"Removing links: {item} <-> {len(targets)} target(s)...")
        results = delete_links(jama, item, targets, dry_run=dry_run)
    else:
        direction: str
        if all_upstream and all_downstream:
            direction = "both"
            typer.echo(f"Removing all links from {item}...")
        elif all_upstream:
            direction = "upstream"
            typer.echo(f"Removing all upstream links from {item}...")
        else:
            direction = "downstream"
            typer.echo(f"Removing all downstream links from {item}...")
        results = delete_all_links(jama, item, direction=direction, dry_run=dry_run)  # type: ignore[arg-type]

    print_delete_results(results, dry_run=dry_run)

    errors = sum(1 for r in results if r["status"] == "error")
    if errors > 0:
        raise typer.Exit(1)


# =============================================================================
# Aliases subcommand
# =============================================================================


@app.command("aliases")
def list_aliases():
    """List all field aliases."""
    from scripts.jama.fields import get_field_aliases_help

    typer.echo(get_field_aliases_help())


# =============================================================================
# Version
# =============================================================================


@app.command("version")
def version():
    """Show version information."""
    from scripts import __version__

    typer.echo(f"jama CLI v{__version__}")


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
