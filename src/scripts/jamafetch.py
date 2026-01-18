#!/usr/bin/env python3
"""
Unified Jama item fetching tool with configurable field selection and local caching.
"""

import argparse
import json
import sys
from pathlib import Path

import pyperclip

from scripts.jama.common import get_item_id, jama_url_for_item, load_jama

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

    Args:
        jama: Jama client
        item_type_id: Item type ID
        database: Current database

    Returns:
        Dict mapping field names to field info
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
    """
    Resolve a field value, converting enum IDs to human-readable names.

    Args:
        value: The field value
        field_info: Field information from database

    Returns:
        Resolved string value
    """
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
    """
    Resolve a field input to an actual Jama field name.

    Args:
        field_input: User-provided field name (alias or actual key)
        item_fields: Dict of available fields for this item type

    Returns:
        Actual Jama field name, or None if not found
    """
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


def format_item_output(
    item: dict,
    fields_to_show: list[str],
    item_fields: dict,
    include_url: bool = False,
) -> str:
    """
    Format a Jama item for output.

    Args:
        item: Jama item data
        fields_to_show: List of field names (canonical or actual keys) to display
        item_fields: Field info for this item type
        include_url: Whether to include Jama URL

    Returns:
        Formatted string
    """
    fields = item.get("fields", {})
    doc_key = item.get("documentKey", "")
    global_id = item.get("globalId", "")
    item_id = item.get("id")
    project_id = item.get("project", {})

    lines = [f"# {doc_key}"]

    name = fields.get("name", "")
    if name:
        lines.append(f"{name}")

    if global_id:
        lines.append(f"Global ID: {global_id}")

    if include_url and item_id:
        url = jama_url_for_item(item_id, project_id.get("id") if isinstance(project_id, dict) else project_id)
        lines.append(f"URL: {url}")

    lines.append("")

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

        if resolved_value:
            display_name = field_info.get("base_name", actual_field_name)
            lines.append(f"{display_name}:")
            lines.append(f"{resolved_value}")
            lines.append("")

    return "\n".join(lines)


def fetch_items(
    jama,
    document_keys: list[str],
    fields_to_show: list[str] | None = None,
    include_url: bool = False,
    show_full: bool = False,
) -> list[str]:
    """
    Fetch and format multiple Jama items.

    Args:
        jama: Jama client
        document_keys: List of document keys to fetch
        fields_to_show: List of fields to display (None = name only)
        include_url: Whether to include URLs
        show_full: Whether to show all fields

    Returns:
        List of formatted item strings
    """
    database = load_database()
    outputs = []

    for doc_key in document_keys:
        item_id = get_item_id(jama, doc_key)
        if not item_id:
            print(f"Warning: Could not find item '{doc_key}'", file=sys.stderr)
            continue

        try:
            item = jama.get_item(item_id)
        except Exception as e:
            print(f"Warning: Error fetching item '{doc_key}': {e}", file=sys.stderr)
            continue

        item_type_id = item.get("itemType")
        if not item_type_id:
            print(f"Warning: No item type for '{doc_key}'", file=sys.stderr)
            continue

        item_fields = get_item_type_fields(jama, item_type_id, database)

        fields_to_display = list(item_fields.keys()) if show_full else fields_to_show or []

        output = format_item_output(item, fields_to_display, item_fields, include_url=include_url)
        outputs.append(output)

    return outputs


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Jama items with configurable field selection and local caching.",
        epilog=get_field_aliases_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "keys",
        nargs="*",
        metavar="JAMA_KEY",
        help="Jama document keys (e.g., ABSD-SWVER-257)",
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

    outputs = fetch_items(
        jama,
        args.keys,
        fields_to_show=fields_to_show,
        include_url=args.url,
        show_full=args.full,
    )

    if not outputs:
        sys.exit(1)

    combined = ("\n" + "-" * 60 + "\n").join(outputs)

    print(combined)

    if not args.no_clipboard:
        try:
            pyperclip.copy(combined)
            print("\nOutput copied to clipboard.")
        except Exception as e:
            print(f"\nFailed to copy to clipboard: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
