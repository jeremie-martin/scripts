#!/usr/bin/env python3
"""MCP server for Jama integration - provides LLM-friendly access to Jama items."""

from __future__ import annotations

import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

# Initialize MCP server
server = Server("jama-mcp")


def _get_jama():
    """Get Jama client, raising descriptive error if auth fails."""
    from scripts.jama.common import load_jama

    return load_jama()


# =============================================================================
# MCP Tools
# =============================================================================


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Jama tools."""
    return [
        Tool(
            name="fetch_item",
            description="Fetch a single Jama item by document key (e.g., ABC-DI2-123). Returns item fields in a readable format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_key": {
                        "type": "string",
                        "description": "Document key of the item (e.g., ABC-DI2-123)",
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of fields to include (default: description). Use 'all' for all fields.",
                    },
                    "include_url": {
                        "type": "boolean",
                        "description": "Include Jama URL in output",
                        "default": False,
                    },
                },
                "required": ["doc_key"],
            },
        ),
        Tool(
            name="fetch_container",
            description="Fetch all items in a Jama container (folder, set, or component). Returns items in a structured format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "container_key": {
                        "type": "string",
                        "description": "Document key of the container (e.g., ABC-DI2-FLD-001)",
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of fields to include for each item",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["path", "json", "flat"],
                        "description": "Output format (default: path)",
                        "default": "path",
                    },
                },
                "required": ["container_key"],
            },
        ),
        Tool(
            name="update_item",
            description="Update fields on a Jama item. Only updates specified fields; others remain unchanged.",
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_key": {
                        "type": "string",
                        "description": "Document key of the item to update",
                    },
                    "fields": {
                        "type": "object",
                        "description": "Dictionary of field names to new values",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "If true, overwrite existing values; if false, only update empty fields",
                        "default": False,
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show what would be updated without making changes",
                        "default": False,
                    },
                },
                "required": ["doc_key", "fields"],
            },
        ),
        Tool(
            name="create_item",
            description="Create a new Jama item under a parent container.",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_type": {
                        "type": "string",
                        "description": "Item type: requirement/req, testcase/tc, text/txt, or actual type name",
                    },
                    "parent_key": {
                        "type": "string",
                        "description": "Document key of the parent container",
                    },
                    "name": {
                        "type": "string",
                        "description": "Name for the new item",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description for the new item",
                    },
                    "fields": {
                        "type": "object",
                        "description": "Additional fields to set",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show what would be created without making changes",
                        "default": False,
                    },
                },
                "required": ["item_type", "parent_key", "name"],
            },
        ),
        Tool(
            name="list_item_types",
            description="List available item types from the local database.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="sync_database",
            description="Refresh the local database from Jama API. Use this if item types or prefixes are missing.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "fetch_item":
            return await _fetch_item(arguments)
        elif name == "fetch_container":
            return await _fetch_container(arguments)
        elif name == "update_item":
            return await _update_item(arguments)
        elif name == "create_item":
            return await _create_item(arguments)
        elif name == "list_item_types":
            return await _list_item_types(arguments)
        elif name == "sync_database":
            return await _sync_database(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _fetch_item(args: dict[str, Any]) -> list[TextContent]:
    """Fetch a single item."""
    from scripts.jama.common import get_item_id, jama_url_for_item
    from scripts.jama.database import get_item_type_fields, load_database
    from scripts.jama.fields import resolve_field_name, resolve_field_value

    doc_key = args["doc_key"]
    field_list = args.get("fields", ["description"])
    include_url = args.get("include_url", False)

    jama = _get_jama()
    database = load_database()

    item_id = get_item_id(jama, doc_key)
    if not item_id:
        return [TextContent(type="text", text=f"Item not found: {doc_key}")]

    item = jama.get_item(item_id)
    if not item:
        return [TextContent(type="text", text=f"Failed to fetch item: {doc_key}")]

    item_type_id = item.get("itemType")
    item_fields = get_item_type_fields(jama, item_type_id, database) if item_type_id else {}
    fields = item.get("fields", {})

    # Determine which fields to show
    fields_to_show = list(item_fields.keys()) if "all" in field_list else field_list

    # Build output
    lines = [f"# {doc_key}: {fields.get('name', 'Unnamed')}"]

    for field_input in fields_to_show:
        if field_input in ["name", "documentKey"]:
            continue

        actual_field_name = resolve_field_name(field_input, item_fields)
        if not actual_field_name:
            continue

        value = fields.get(actual_field_name)
        if value is None:
            continue

        field_info = item_fields.get(actual_field_name, {})
        resolved_value = resolve_field_value(value, field_info)
        display_name = field_info.get("base_name", actual_field_name)

        lines.append(f"\n## {display_name}")
        lines.append(resolved_value)

    if include_url:
        project_id = item.get("project", {})
        if isinstance(project_id, dict):
            project_id = project_id.get("id")
        url = jama_url_for_item(item_id, project_id)
        lines.append(f"\n## URL\n{url}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _fetch_container(args: dict[str, Any]) -> list[TextContent]:
    """Fetch items from a container."""
    from scripts.jamafetch import fetch_items_tree

    container_key = args["container_key"]
    field_list = args.get("fields", ["description"])
    format_type = args.get("format", "path")

    jama = _get_jama()

    outputs = fetch_items_tree(
        jama,
        [container_key],
        fields_to_show=field_list,
        include_url=False,
        show_full=False,
        format_type=format_type,
    )

    if not outputs:
        return [TextContent(type="text", text=f"No items found in container: {container_key}")]

    return [TextContent(type="text", text="\n".join(outputs))]


async def _update_item(args: dict[str, Any]) -> list[TextContent]:
    """Update an item."""
    from scripts.jamaupdate import update_item_fields

    doc_key = args["doc_key"]
    fields = args["fields"]
    overwrite = args.get("overwrite", False)
    dry_run = args.get("dry_run", False)

    jama = _get_jama()

    # Capture output
    import io
    from contextlib import redirect_stdout

    output = io.StringIO()
    with redirect_stdout(output):
        success = update_item_fields(jama, doc_key, fields, overwrite=overwrite, dry_run=dry_run)

    result = output.getvalue()
    if success:
        result += f"\n{'[DRY RUN] ' if dry_run else ''}Update successful"
    else:
        result += "\nUpdate failed"

    return [TextContent(type="text", text=result)]


async def _create_item(args: dict[str, Any]) -> list[TextContent]:
    """Create a new item."""
    from scripts.jama.create import create_item

    jama = _get_jama()

    result = create_item(
        jama,
        args["item_type"],
        args["parent_key"],
        args["name"],
        description=args.get("description"),
        fields=args.get("fields"),
        dry_run=args.get("dry_run", False),
    )

    if result:
        if args.get("dry_run"):
            return [TextContent(type="text", text=f"[DRY RUN] Would create item:\n{json.dumps(result, indent=2)}")]
        return [TextContent(type="text", text=f"Created item: {result.get('doc_key', 'unknown')} (ID: {result.get('id')})")]

    return [TextContent(type="text", text="Failed to create item")]


async def _list_item_types(args: dict[str, Any]) -> list[TextContent]:
    """List item types from database."""
    from scripts.jama.database import load_database

    database = load_database()
    item_types = database.get("item_types", {})

    if not item_types:
        return [TextContent(type="text", text="No item types in database. Run sync_database to refresh.")]

    lines = ["# Item Types", ""]
    for type_id, info in sorted(item_types.items()):
        name = info.get("item_type_name", "Unknown")
        field_count = len(info.get("fields", {}))
        lines.append(f"- **{name}** (ID: {type_id}, {field_count} fields)")

    return [TextContent(type="text", text="\n".join(lines))]


async def _sync_database(args: dict[str, Any]) -> list[TextContent]:
    """Sync database from Jama."""
    from scripts.jama.database import sync_database

    jama = _get_jama()
    database = sync_database(jama, verbose=False)

    item_count = len(database.get("item_types", {}))
    prefix_count = len(database.get("prefix_map", {}))

    return [TextContent(type="text", text=f"Database synced: {item_count} item types, {prefix_count} prefixes")]


# =============================================================================
# MCP Resources
# =============================================================================


@server.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources."""
    return [
        Resource(
            uri="jama://database",
            name="Jama Database",
            description="Local database metadata including item types and prefix mappings",
            mimeType="application/json",
        ),
        Resource(
            uri="jama://aliases",
            name="Field Aliases",
            description="Available field name aliases for Jama items",
            mimeType="text/plain",
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource."""
    if uri == "jama://database":
        from scripts.jama.database import DB_FILE, load_database

        database = load_database()
        return json.dumps(
            {
                "path": str(DB_FILE),
                "version": database.get("version"),
                "item_type_count": len(database.get("item_types", {})),
                "prefix_count": len(database.get("prefix_map", {})),
                "prefixes": list(database.get("prefix_map", {}).keys()),
            },
            indent=2,
        )
    elif uri == "jama://aliases":
        from scripts.jama.fields import get_field_aliases_help

        return get_field_aliases_help()
    else:
        return f"Unknown resource: {uri}"


# =============================================================================
# Main
# =============================================================================


async def run_server():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Entry point for MCP server."""
    import asyncio

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
