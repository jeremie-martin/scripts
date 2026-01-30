#!/usr/bin/env python3
"""
Unified Jama item fetching tool with configurable field selection, local caching, and multiple output formats.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from scripts.jama.common import (
    get_item_id,
    is_container_stub,
    jama_url_for_item,
    load_jama,
    safe_copy_to_clipboard,
)
from scripts.jama.database import (
    DB_FILE,
    get_item_type_fields,
    load_database,
)
from scripts.jama.fields import (
    get_field_aliases_help,
    resolve_field_name,
    resolve_field_value,
)
from scripts.jama.formatters import ItemData, ItemLinks, LinkData, get_formatter
from scripts.jama.links import get_item_links
from scripts.jama.tree import ItemNode, build_tree


def build_item_data(
    item: dict,
    fields_to_show: list[str],
    item_fields: dict,
    include_url: bool,
    links: ItemLinks | None = None,
) -> ItemData:
    """Build an ItemData object with selected fields."""
    fields = item.get("fields", {})
    doc_key = item.get("documentKey", "")
    name = fields.get("name", "")

    selected_fields = {}

    seen_fields = set()

    for field_input in fields_to_show:
        if field_input in ["name", "documentKey", "globalId"]:
            continue

        actual_field_name = resolve_field_name(field_input, item_fields)
        if not actual_field_name:
            continue

        if actual_field_name in seen_fields:
            continue
        seen_fields.add(actual_field_name)

        value = fields.get(actual_field_name)
        field_info = item_fields.get(actual_field_name, {})

        if value is None:
            continue

        resolved_value = resolve_field_value(value, field_info)
        display_name = field_info.get("base_name", actual_field_name)
        selected_fields[display_name] = resolved_value

    url = None
    if include_url:
        item_id = item.get("id")
        if item_id is not None:
            project_id = item.get("project", {})
            url = jama_url_for_item(item_id, project_id.get("id") if isinstance(project_id, dict) else project_id)

    return ItemData(doc_key=doc_key, name=name, fields=selected_fields, url=url, links=links)


def fetch_links_for_item(jama, doc_key: str, links_mode: str | None) -> ItemLinks | None:
    """Fetch links for an item based on links_mode.

    Args:
        jama: Jama client
        doc_key: Document key
        links_mode: 'all', 'upstream', 'downstream', or None

    Returns:
        ItemLinks object or None if links not requested
    """
    if not links_mode:
        return None

    include_upstream = links_mode in ("all", "upstream")
    include_downstream = links_mode in ("all", "downstream")

    item_links = get_item_links(
        jama,
        doc_key,
        include_upstream=include_upstream,
        include_downstream=include_downstream,
    )

    if not item_links:
        return None

    return ItemLinks(
        upstream=[LinkData(key=l.key, name=l.name) for l in item_links.upstream],
        downstream=[LinkData(key=l.key, name=l.name) for l in item_links.downstream],
    )


def format_tree_recursive(
    jama,
    tree: ItemNode,
    formatter,
    fields_to_show: list[str] | None,
    include_url: bool,
    show_full: bool,
    format_type: str,
    indent: int = 0,
    database: dict | None = None,
    links_mode: str | None = None,
) -> list[str]:
    """
    Format a tree node and all its children according to specified format.

    Args:
        jama: Jama client
        tree: Tree node to format
        formatter: Formatter instance
        fields_to_show: List of fields to display
        include_url: Whether to include URLs
        show_full: Whether to show all fields
        format_type: Output format type ('tree', 'path', 'nested', 'json', 'flat')
        indent: Current indentation level
        database: Item type database (optional, loaded once and passed down)
        links_mode: Links to include ('all', 'upstream', 'downstream', or None)

    Returns:
        List of formatted strings
    """
    lines = []

    if database is None:
        database = load_database()

    if tree.is_container and tree.children:
        if format_type == "tree":
            container_lines = formatter.format_container(tree.name, tree.doc_key, indent)
            lines.extend(container_lines)
            for i, child in enumerate(tree.children):
                is_last = i == len(tree.children) - 1
                child_lines = format_tree_recursive(
                    jama, child, formatter, fields_to_show, include_url, show_full, format_type, indent + 1, database, links_mode
                )
                if is_last and format_type == "tree" and child_lines:
                    child_lines[0] = child_lines[0].replace("├── ", "└── ", 1)
                lines.extend(child_lines)
        elif format_type == "nested":
            container_lines = formatter.format_container(tree.name, tree.doc_key, indent)
            lines.extend(container_lines)
            for child in tree.children:
                child_lines = format_tree_recursive(
                    jama, child, formatter, fields_to_show, include_url, show_full, format_type, indent + 1, database, links_mode
                )
                lines.extend(child_lines)
        else:
            for child in tree.children:
                child_lines = format_tree_recursive(
                    jama, child, formatter, fields_to_show, include_url, show_full, format_type, indent, database, links_mode
                )
                lines.extend(child_lines)
    elif not tree.is_container and tree.doc_key:
        item_id = get_item_id(jama, tree.doc_key)
        if item_id:
            item = jama.get_item(item_id)
            if item is None:
                return lines
            item_type_id = item.get("itemType")
            if item_type_id:
                item_fields = get_item_type_fields(jama, item_type_id, database)
                fields_to_display = list(item_fields.keys()) if show_full else (fields_to_show or ["description"])

                links = fetch_links_for_item(jama, tree.doc_key, links_mode)
                item_data = build_item_data(item, fields_to_display, item_fields, include_url, links)
                item_data.path = tree.path_str if tree.path_str else None

                item_lines = formatter.format_item(item_data, indent)
                lines.extend(item_lines)

    return lines


def fetch_items_tree(
    jama,
    input_keys: list[str],
    fields_to_show: list[str] | None,
    include_url: bool,
    show_full: bool,
    format_type: str,
    links_mode: str | None = None,
) -> list[str]:
    """
    Fetch items from Jama with tree structure preservation.

    Args:
        jama: Jama client
        input_keys: List of input keys (can be containers)
        fields_to_show: List of fields to display
        include_url: Whether to include URLs
        show_full: Whether to show all fields
        format_type: Output format type
        links_mode: Links to include ('all', 'upstream', 'downstream', or None)

    Returns:
        List of formatted strings
    """
    formatter = get_formatter(format_type)
    all_lines = []
    database = load_database()

    for input_key in input_keys:
        item_id = get_item_id(jama, input_key)
        if not item_id:
            print(f"Warning: Could not find item '{input_key}'", file=sys.stderr)
            continue

        item = jama.get_item(item_id)
        if item is None:
            continue
        is_container = is_container_stub(jama, item)

        if is_container:
            container_name = item.get("name") or item.get("fields", {}).get("name") or input_key
            tree = build_tree(jama, item_id, container_name, input_key, [])
            tree_lines = format_tree_recursive(jama, tree, formatter, fields_to_show, include_url, show_full, format_type, 0, database, links_mode)
            all_lines.extend(tree_lines)
        else:
            item_type_id = item.get("itemType")
            if item_type_id:
                item_fields = get_item_type_fields(jama, item_type_id, database)
                fields_to_display = list(item_fields.keys()) if show_full else (fields_to_show or ["description"])

                doc_key = item.get("documentKey", input_key)
                links = fetch_links_for_item(jama, doc_key, links_mode)
                item_data = build_item_data(item, fields_to_display, item_fields, include_url, links)
                item_lines = formatter.format_item(item_data)
                all_lines.extend(item_lines)

    return all_lines


def get_output_filename(keys: list[str], format_type: str) -> Path:
    """Generate output filename in /tmp based on first 5 keys, timestamp, and format."""
    first_keys = "_".join(keys[:5])
    safe_keys = re.sub(r"[^a-zA-Z0-9_-]", "_", first_keys)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jamafetch_{safe_keys}_{timestamp}.{format_type}"
    return Path("/tmp") / filename


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Jama items with configurable field selection, local caching, and multiple output formats.",
        epilog=get_field_aliases_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "keys",
        nargs="*",
        metavar="JAMA_KEY",
        help="Jama document keys or container keys (folders/sets/components)",
    )
    parser.add_argument(
        "--fields",
        type=str,
        help="Comma-separated list of fields to show (e.g., 'description,rationale,ac'). Use aliases or actual Jama keys.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Show all fields (overrides --fields)",
    )
    parser.add_argument(
        "--url",
        action="store_true",
        help="Include Jama URL for each item",
    )
    parser.add_argument(
        "--format",
        choices=["tree", "path", "nested", "json", "flat"],
        default="path",
        help="Output format: tree (ASCII tree), path (default, path prefix), nested (sections), json (structured), flat",
    )
    parser.add_argument(
        "--links",
        nargs="?",
        const="all",
        choices=["all", "upstream", "downstream"],
        help="Include links in output: all (default if flag used), upstream, or downstream",
    )
    parser.add_argument(
        "--no-clipboard",
        action="store_true",
        help="Don't copy output to clipboard",
    )
    parser.add_argument(
        "--list-aliases",
        action="store_true",
        help="List all field aliases and exit",
    )
    parser.add_argument(
        "--list-db",
        action="store_true",
        help="List all item types in database and exit",
    )
    args = parser.parse_args()

    if args.list_aliases:
        print(get_field_aliases_help())
        return 0

    if args.list_db:
        database = load_database()
        item_types = database.get("item_types", {})
        if not item_types:
            print("No item types in database")
            return 0
        print(f"Database: {DB_FILE}")
        print(f"Version: {database.get('version', 'unknown')}")
        print(f"Total item types: {len(item_types)}\n")
        for item_type_id, item_type_info in item_types.items():
            print(f"Item Type ID: {item_type_id}")
            print(f"  Name: {item_type_info.get('item_type_name', 'Unknown')}")
            print(f"  Prefix: {item_type_info.get('doc_key_prefix', 'Unknown')}")
            print(f"  Fields: {len(item_type_info.get('fields', {}))}")
        return 0

    if not args.keys:
        parser.error("JAMA_KEY is required (unless using --list-aliases or --list-db)")

    try:
        jama = load_jama()
    except Exception as e:
        print(f"Jama auth error: {e}", file=sys.stderr)
        return 2

    fields_to_show = None
    if args.fields:
        fields_to_show = [f.strip() for f in args.fields.split(",") if f.strip()]

    outputs = fetch_items_tree(
        jama,
        args.keys,
        fields_to_show=fields_to_show,
        include_url=args.url,
        show_full=args.full,
        format_type=args.format,
        links_mode=args.links,
    )

    if not outputs:
        sys.exit(1)

    combined = "\n".join(outputs)

    print(combined)

    output_file = get_output_filename(args.keys, args.format)
    try:
        output_file.write_text(combined)
        print(f"\nOutput saved to: {output_file}")
    except Exception as e:
        print(f"\nFailed to save output file: {e}", file=sys.stderr)

    if not args.no_clipboard and args.format != "json":
        safe_copy_to_clipboard(combined)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
