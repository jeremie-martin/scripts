#!/usr/bin/env python3
"""
Unified Jama item fetching tool with configurable field selection, local caching, and multiple output formats.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyperclip

from scripts.jama.common import (
    get_document_key_from_stub,
    get_item_id,
    is_container_stub,
    jama_url_for_item,
    load_jama,
)

DB_DIR = Path.home() / ".local" / "share" / "jamafetch"
DB_FILE = DB_DIR / "item_types.json"


FIELD_ALIASES = {
    "name": ["name", "title"],
    "description": ["description", "desc"],
    "rationale": ["rationale", "rationale$171"],
    "acceptance_criteria": ["acceptance_criteria", "acceptance_criteria$171", "ac", "AC"],
    "status": ["status"],
    "di_classification": ["di_classification", "di_classification$171", "di", "classification"],
    "no_downstream_di_required": ["no_downstream_di_required", "no_downstream_di_required$171", "no_di_required"],
    "globalId": ["globalId", "gid"],
    "createdDate": ["createdDate", "created"],
    "test_inputs": ["test_inputs", "inputs"],
    "initial_conditions": ["initial_conditions", "preconditions"],
    "test_outputs": ["test_outputs", "outputs"],
    "assumptions__constraints": ["assumptions__constraints", "assumptions"],
    "data_collection_actions": ["data_collection_actions", "actions"],
}


@dataclass
class ItemNode:
    """Represents an item or container in the tree."""

    doc_key: str | None
    name: str
    item_id: int
    path: list[str]
    is_container: bool
    children: list["ItemNode"]

    @property
    def path_str(self) -> str:
        """Get path as a string."""
        return " / ".join(self.path)


def get_field_aliases_help() -> str:
    """Generate help text for field aliases."""
    lines = ["Field aliases (can use actual Jama keys or these aliases):"]
    for canonical, aliases in FIELD_ALIASES.items():
        alias_str = ", ".join(aliases)
        lines.append(f"  {canonical}: {alias_str}")
    return "\n".join(lines)


def load_database() -> dict:
    """Load item type database from disk."""
    if DB_FILE.exists():
        try:
            with open(DB_FILE) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_database(database: dict) -> None:
    """Save item type database to disk."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with open(DB_FILE, "w") as f:
        json.dump(database, f, indent=2)


def get_item_type_fields(jama, item_type_id: int, database: dict) -> dict:
    """
    Get field information for an item type, using database or fetching from Jama.
    """
    str_item_type_id = str(item_type_id)

    if str_item_type_id in database:
        return database[str_item_type_id]["fields"]

    item_type = jama.get_item_type(item_type_id)
    fields = item_type.get("fields", [])

    field_info = {}
    for field in fields:
        field_name = field.get("name")
        field_type = field.get("fieldType")
        picklist = field.get("pickList")

        if not field_name:
            continue

        field_data = {
            "field_type": field_type,
            "base_name": field_name.split("$")[0] if "$" in field_name else field_name,
        }

        if picklist:
            picklist_id = picklist.get("id") if isinstance(picklist, dict) else picklist
            if picklist_id:
                field_data["picklist_id"] = picklist_id
                try:
                    options = jama.get_pick_list_options(picklist_id)
                    enum_values = {}
                    for opt in options:
                        opt_id = opt.get("id")
                        opt_name = opt.get("name")
                        if opt_id is not None and opt_name:
                            enum_values[str(opt_id)] = opt_name
                    field_data["enum_values"] = enum_values
                except Exception:
                    pass

        field_info[field_name] = field_data

    database[str_item_type_id] = {
        "item_type_name": item_type.get("name"),
        "doc_key_prefix": "",
        "fields": field_info,
    }

    save_database(database)
    print(f"Updated database with item type {item_type_id}", file=sys.stderr)

    return field_info


def resolve_field_value(value, field_info: dict) -> str:
    """Resolve a field value, converting enum IDs to human-readable names."""
    if value is None:
        return ""

    if isinstance(value, bool):
        return "True" if value else "False"

    if isinstance(value, list):
        enum_values = field_info.get("enum_values", {})
        if enum_values:
            resolved = []
            for item in value:
                if isinstance(item, int):
                    str_item = str(item)
                    resolved.append(enum_values.get(str_item, str_item))
                else:
                    resolved.append(str(item))
            return ", ".join(resolved)
        return ", ".join(str(v) for v in value)

    if isinstance(value, int):
        enum_values = field_info.get("enum_values", {})
        if enum_values:
            str_value = str(value)
            if str_value in enum_values:
                return enum_values[str_value]

    return str(value)


def resolve_field_name(field_input: str, item_fields: dict) -> str | None:
    """Resolve a field input to an actual Jama field name."""
    field_input_lower = field_input.lower()

    for canonical_name, aliases in FIELD_ALIASES.items():
        if field_input_lower in [a.lower() for a in aliases]:
            for actual_field_name, field_info in item_fields.items():
                if field_info.get("base_name") == canonical_name:
                    return actual_field_name

    for actual_field_name, field_info in item_fields.items():
        base_name = field_info.get("base_name", actual_field_name)
        if base_name.lower() == field_input_lower or actual_field_name.lower() == field_input_lower:
            return actual_field_name

    return None


def build_item_data(item: dict, fields_to_show: list[str], item_fields: dict, include_url: bool) -> dict:
    """Build a dictionary with item data for selected fields."""
    fields = item.get("fields", {})
    data = {
        "doc_key": item.get("documentKey", ""),
        "name": fields.get("name", ""),
    }

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
        data[display_name] = resolved_value

    if include_url:
        item_id = item.get("id")
        if item_id is not None:
            project_id = item.get("project", {})
            url = jama_url_for_item(item_id, project_id.get("id") if isinstance(project_id, dict) else project_id)
            data["url"] = url

    return data


def build_tree(
    jama,
    container_id: int,
    container_name: str,
    container_doc_key: str,
    path: list[str],
    seen_ids: set[int] | None = None,
) -> ItemNode:
    """
    Recursively build a tree structure from a container.

    Args:
        jama: Jama client
        container_id: Container item ID
        container_name: Container name
        container_doc_key: Container document key
        path: Current path in the tree
        seen_ids: Set of visited container IDs (for cycle detection)

    Returns:
        ItemNode representing the container tree
    """
    if seen_ids is None:
        seen_ids = set()

    if container_id in seen_ids:
        return ItemNode(doc_key=container_doc_key, name=container_name, item_id=container_id, path=path, is_container=True, children=[])

    seen_ids.add(container_id)
    current_path = [*path, container_name]

    try:
        children = jama.get_item_children(container_id)
    except Exception:
        return ItemNode(doc_key=container_doc_key, name=container_name, item_id=container_id, path=path, is_container=True, children=[])

    child_nodes = []
    for child in children:
        if not isinstance(child, dict):
            continue

        child_id = child.get("id")
        child_doc_key = get_document_key_from_stub(child)

        if is_container_stub(jama, child):
            if child_id and child_id not in seen_ids:
                child_name = child.get("name") or child.get("documentKey", "")
                child_doc_key = child_doc_key or child.get("documentKey", "")
                sub_tree = build_tree(jama, child_id, child_name, child_doc_key, current_path, seen_ids)
                child_nodes.append(sub_tree)
        elif child_doc_key:
            child_name = child.get("name", child_doc_key)
            child_nodes.append(
                ItemNode(doc_key=child_doc_key, name=child_name, item_id=child_id or 0, path=current_path, is_container=False, children=[])
            )

    return ItemNode(
        doc_key=container_doc_key, name=container_name, item_id=container_id, path=path, is_container=True, children=child_nodes
    )


def format_tree(
    jama,
    tree: ItemNode,
    fields_to_show: list[str] | None,
    include_url: bool,
    show_full: bool,
    format_type: str,
    indent: int = 0,
) -> list[str]:
    """
    Format a tree node and all its children according to the specified format.

    Args:
        jama: Jama client
        tree: Tree node to format
        fields_to_show: List of fields to display
        include_url: Whether to include URLs
        show_full: Whether to show all fields
        format_type: Output format type ('tree', 'path', 'nested', 'json', 'flat')
        indent: Current indentation level

    Returns:
        List of formatted strings
    """
    lines = []

    if tree.is_container and tree.children:
        if format_type == "tree":
            prefix = "├── " if indent > 0 else ""
            lines.append(f"{'  ' * indent}{prefix}[{tree.doc_key}] {tree.name}")
            for i, child in enumerate(tree.children):
                is_last = i == len(tree.children) - 1
                child_lines = format_tree(jama, child, fields_to_show, include_url, show_full, format_type, indent + 1)
                if child_lines and is_last and format_type == "tree":
                    child_lines[-1] = child_lines[-1].replace("├── ", "└── ", 1)
                lines.extend(child_lines)
        elif format_type == "path":
            for child in tree.children:
                child_lines = format_tree(jama, child, fields_to_show, include_url, show_full, format_type, indent)
                lines.extend(child_lines)
        elif format_type == "nested":
            lines.append(f"{'#' * (indent + 2)} {tree.doc_key}: {tree.name}")
            for child in tree.children:
                child_lines = format_tree(jama, child, fields_to_show, include_url, show_full, format_type, indent + 1)
                lines.extend(child_lines)
            lines.append("")
        elif format_type == "json" or format_type == "flat":
            for child in tree.children:
                child_lines = format_tree(jama, child, fields_to_show, include_url, show_full, format_type, indent)
                lines.extend(child_lines)
    elif not tree.is_container and tree.doc_key:
        item_id = get_item_id(jama, tree.doc_key)
        if item_id:
            item = jama.get_item(item_id)
            item_type_id = item.get("itemType")
            if item_type_id:
                database = load_database()
                item_fields = get_item_type_fields(jama, item_type_id, database)
                fields_to_display = list(item_fields.keys()) if show_full else (fields_to_show or [])

                item_data = build_item_data(item, fields_to_display, item_fields, include_url)

                if format_type == "tree":
                    lines.append(f"{'  ' * indent}└── {tree.doc_key}: {item_data.get('name', '')}")
                    for field_name, field_value in item_data.items():
                        if field_name not in ["doc_key", "name"]:
                            lines.append(f"{'  ' * (indent + 1)}    {field_name}: {str(field_value)[:80]}")
                elif format_type == "path":
                    path_prefix = f"[{tree.path_str}] " if tree.path else ""
                    lines.append(f"{path_prefix}{tree.doc_key}: {item_data.get('name', '')}")
                    for field_name, field_value in item_data.items():
                        if field_name not in ["doc_key", "name"]:
                            field_value_str = str(field_value).replace("\n", " ")[:200]
                            lines.append(f"@{field_name}: {field_value_str}")
                    lines.append("")
                elif format_type == "nested":
                    lines.append(f"{'## ' * indent}{tree.doc_key}: {item_data.get('name', '')}")
                    if tree.path:
                        lines.append(f"Path: {tree.path_str}")
                    lines.append("")
                    for field_name, field_value in item_data.items():
                        if field_name not in ["doc_key", "name", "url"]:
                            lines.append(f"### {field_name}")
                            lines.append(f"{field_value}")
                            lines.append("")
                    if "url" in item_data:
                        lines.append("### URL")
                        lines.append(f"{item_data['url']}")
                        lines.append("")
                elif format_type == "json":
                    item_json = json.dumps(item_data, ensure_ascii=False, indent=2)
                    lines.append(item_json)
                elif format_type == "flat":
                    lines.append(f"# {tree.doc_key}: {item_data.get('name', '')}")
                    if tree.path:
                        lines.append(f"Path: {tree.path_str}")
                    for field_name, field_value in item_data.items():
                        if field_name not in ["doc_key", "name"]:
                            lines.append(f"## {field_name}")
                            lines.append(f"{field_value}")
                            lines.append("")
                    lines.append("-" * 60)

    return lines


def fetch_items_tree(
    jama,
    input_keys: list[str],
    fields_to_show: list[str] | None,
    include_url: bool,
    show_full: bool,
    format_type: str,
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

    Returns:
        List of formatted strings
    """
    all_lines = []

    for input_key in input_keys:
        item_id = get_item_id(jama, input_key)
        if not item_id:
            print(f"Warning: Could not find item '{input_key}'", file=sys.stderr)
            continue

        item = jama.get_item(item_id)

        if is_container_stub(jama, item):
            container_name = item.get("name") or input_key
            tree = build_tree(jama, item_id, container_name, input_key, [])
            tree_lines = format_tree(jama, tree, fields_to_show, include_url, show_full, format_type)
            all_lines.extend(tree_lines)
        else:
            item_type_id = item.get("itemType")
            if item_type_id:
                database = load_database()
                item_fields = get_item_type_fields(jama, item_type_id, database)
                fields_to_display = list(item_fields.keys()) if show_full else (fields_to_show or [])

                item_data = build_item_data(item, fields_to_display, item_fields, include_url)

                if format_type == "tree":
                    all_lines.append(f"[{input_key}] {item_data.get('name', '')}")
                    for field_name, field_value in item_data.items():
                        if field_name not in ["doc_key", "name"]:
                            all_lines.append(f"    {field_name}: {str(field_value)[:80]}")
                elif format_type == "path":
                    all_lines.append(f"{input_key}: {item_data.get('name', '')}")
                    for field_name, field_value in item_data.items():
                        if field_name not in ["doc_key", "name"]:
                            field_value_str = str(field_value).replace("\n", " ")[:200]
                            all_lines.append(f"@{field_name}: {field_value_str}")
                    all_lines.append("")
                elif format_type == "nested":
                    all_lines.append(f"## {input_key}: {item_data.get('name', '')}")
                    for field_name, field_value in item_data.items():
                        if field_name not in ["doc_key", "name", "url"]:
                            all_lines.append(f"### {field_name}")
                            all_lines.append(f"{field_value}")
                            all_lines.append("")
                    if "url" in item_data:
                        all_lines.append("### URL")
                        all_lines.append(f"{item_data['url']}")
                        all_lines.append("")
                elif format_type == "json":
                    item_json = json.dumps(item_data, ensure_ascii=False, indent=2)
                    all_lines.append(item_json)
                elif format_type == "flat":
                    all_lines.append(f"# {input_key}: {item_data.get('name', '')}")
                    for field_name, field_value in item_data.items():
                        if field_name not in ["doc_key", "name"]:
                            all_lines.append(f"## {field_name}")
                            all_lines.append(f"{field_value}")
                            all_lines.append("")
                    all_lines.append("-" * 60)

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
        default="flat",
        help="Output format: tree (ASCII tree), path (path prefix), nested (sections), json (structured), flat (default)",
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
        if not database:
            print("No item types in database")
            return 0
        print(f"Database: {DB_FILE}")
        print(f"Total item types: {len(database)}\n")
        for item_type_id, item_type_info in database.items():
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
        try:
            pyperclip.copy(combined)
            print("Output copied to clipboard.")
        except Exception as e:
            print(f"Failed to copy to clipboard: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
