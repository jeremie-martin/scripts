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
