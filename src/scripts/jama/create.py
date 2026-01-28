#!/usr/bin/env python3
"""Item creation logic for Jama."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from scripts.jama.common import get_item_id, load_jama
from scripts.jama.database import load_database

if TYPE_CHECKING:
    from py_jama_rest_client.client import JamaClient

__all__ = [
    "ITEM_TYPE_ALIASES",
    "create_item",
    "resolve_item_type_alias",
]

# Item type aliases for common types
# Maps canonical name to aliases
ITEM_TYPE_ALIASES: dict[str, list[str]] = {
    "Requirement": ["req", "requirement", "requirements"],
    "Test Case": ["test", "testcase", "tc", "test_case"],
    "Text": ["txt", "text", "doc", "document"],
    "Folder": ["folder", "fld"],
    "Set": ["set"],
    "Component": ["component", "cmp"],
}

# Maps canonical name to Jama typeKeys (what the API actually uses)
TYPE_KEY_MAP: dict[str, list[str]] = {
    "Requirement": ["DI2", "DI", "DI1", "DI3", "REQ", "DISYS"],
    "Test Case": ["TC", "TEST", "SWVER", "VER"],
    "Text": ["TXT", "TEXT"],
    "Folder": ["FLD", "FOLDER"],
    "Set": ["SET"],
    "Component": ["CMP", "COMPONENT"],
}


def resolve_item_type_alias(alias: str) -> str:
    """
    Resolve an item type alias to its canonical name.

    Args:
        alias: Alias like "req", "tc", "txt"

    Returns:
        Canonical name like "Requirement", "Test Case", "Text"
    """
    alias_lower = alias.lower()
    for canonical, aliases in ITEM_TYPE_ALIASES.items():
        if alias_lower in [a.lower() for a in aliases] or alias_lower == canonical.lower():
            return canonical
    # If no match, return the original (maybe it's already canonical)
    return alias


def _find_item_type_id(database: dict[str, Any], type_name: str) -> int | None:
    """Find item type ID by name or typeKey in database."""
    type_name_lower = type_name.lower()

    # First try by item_type_name
    for item_type_id, item_info in database.get("item_types", {}).items():
        item_name = item_info.get("item_type_name") or ""
        if item_name and item_name.lower() == type_name_lower:
            return int(item_type_id)

    # Then try by typeKey using our mapping
    type_keys = TYPE_KEY_MAP.get(type_name, [])
    for item_type_id, item_info in database.get("item_types", {}).items():
        item_type_key = item_info.get("type_key", "")
        if item_type_key and item_type_key in type_keys:
            return int(item_type_id)

    return None


def _find_item_type_id_for_prefix(database: dict[str, Any], parent_prefix: str, type_name: str) -> int | None:
    """
    Find item type ID that matches both a prefix pattern and type name.

    Args:
        database: Database dict
        parent_prefix: Prefix from parent (e.g., "ABC-DI2")
        type_name: Canonical item type name

    Returns:
        Item type ID or None
    """
    # First try to get from prefix_map
    prefix_info = database.get("prefix_map", {}).get(parent_prefix)
    if prefix_info:
        return prefix_info.get("item_type_id")

    # Otherwise search item_types for matching name
    return _find_item_type_id(database, type_name)


def create_item(
    jama: JamaClient,
    item_type: str,
    parent_key: str,
    name: str,
    *,
    description: str | None = None,
    fields: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """
    Create a new item in Jama.

    Args:
        jama: Jama client
        item_type: Item type name or alias (e.g., "req", "testcase", "text")
        parent_key: Parent container document key (e.g., "ABC-DI2-FLD-001")
        name: Name for the new item
        description: Optional description
        fields: Optional additional fields dict
        dry_run: If True, don't actually create, just return what would be created

    Returns:
        Dict with created item info (including doc_key) or None on failure
    """
    database = load_database()

    # Check if item_type is a numeric ID
    item_type_id_direct = None
    if item_type.isdigit():
        item_type_id_direct = int(item_type)
        canonical_type = item_type
        print(f"Item type: {item_type} (direct ID)", file=sys.stderr)
    else:
        # Resolve item type alias
        canonical_type = resolve_item_type_alias(item_type)
        print(f"Item type: {item_type} -> {canonical_type}", file=sys.stderr)

    # Get parent item ID
    parent_id = get_item_id(jama, parent_key)
    if not parent_id:
        print(f"Error: Could not find parent container '{parent_key}'", file=sys.stderr)
        return None

    # Get parent item to determine project
    try:
        parent_item = jama.get_item(parent_id)
    except Exception as e:
        print(f"Error fetching parent item: {e}", file=sys.stderr)
        return None

    project_id = parent_item.get("project")
    if isinstance(project_id, dict):
        project_id = project_id.get("id")

    if not project_id:
        print(f"Error: Could not determine project from parent '{parent_key}'", file=sys.stderr)
        return None

    # Try to find item type ID
    item_type_id = item_type_id_direct  # Use direct ID if provided

    if not item_type_id:
        # Try finding by canonical name in database
        item_type_id = _find_item_type_id(database, canonical_type)

    if not item_type_id:
        # Try fetching item types from project and finding match
        try:
            project_item_types = jama.get_item_types(project_id)
            for it in project_item_types:
                if it.get("name", "").lower() == canonical_type.lower():
                    item_type_id = it.get("id")
                    break
        except Exception as e:
            print(f"Warning: Could not fetch project item types: {e}", file=sys.stderr)

    if not item_type_id:
        print(f"Error: Could not find item type '{canonical_type}' in database or project", file=sys.stderr)
        print("Try running 'jama db sync' to refresh the database", file=sys.stderr)
        return None

    # Build fields dict
    item_fields: dict[str, Any] = {"name": name}
    if description:
        item_fields["description"] = description
    if fields:
        item_fields.update(fields)

    if dry_run:
        print(f"[DRY RUN] Would create {canonical_type} under {parent_key}:", file=sys.stderr)
        print(f"  Project ID: {project_id}", file=sys.stderr)
        print(f"  Item Type ID: {item_type_id}", file=sys.stderr)
        print(f"  Parent ID: {parent_id}", file=sys.stderr)
        print(f"  Fields: {item_fields}", file=sys.stderr)
        return {
            "dry_run": True,
            "project_id": project_id,
            "item_type_id": item_type_id,
            "parent_id": parent_id,
            "fields": item_fields,
        }

    # Create the item
    try:
        result = jama.post_item(
            project=project_id,
            item_type_id=item_type_id,
            child_item_type_id=item_type_id,
            location={"item": parent_id},  # post_item wraps this in {"parent": ...}
            fields=item_fields,
        )

        # Result should contain the new item ID
        if isinstance(result, dict):
            new_id = result.get("id")
            if new_id:
                # Fetch the item to get its document key
                new_item = jama.get_item(new_id)
                doc_key = new_item.get("documentKey", "")
                print(f"Created item: {doc_key} (ID: {new_id})", file=sys.stderr)
                return {
                    "id": new_id,
                    "doc_key": doc_key,
                    "name": name,
                    "item_type": canonical_type,
                    "parent_key": parent_key,
                }
        elif isinstance(result, int):
            # Some versions return just the ID
            new_item = jama.get_item(result)
            doc_key = new_item.get("documentKey", "")
            print(f"Created item: {doc_key} (ID: {result})", file=sys.stderr)
            return {
                "id": result,
                "doc_key": doc_key,
                "name": name,
                "item_type": canonical_type,
                "parent_key": parent_key,
            }

        print(f"Warning: Unexpected response from Jama: {result}", file=sys.stderr)
        return None

    except Exception as e:
        print(f"Error creating item: {e}", file=sys.stderr)
        return None


def create_item_cli(
    item_type: str,
    parent_key: str,
    name: str,
    *,
    description: str | None = None,
    fields: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> int:
    """
    CLI wrapper for create_item.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        jama = load_jama()
    except Exception as e:
        print(f"Jama auth error: {e}", file=sys.stderr)
        return 2

    result = create_item(
        jama,
        item_type,
        parent_key,
        name,
        description=description,
        fields=fields,
        dry_run=dry_run,
    )

    if result:
        if not dry_run:
            print(f"Successfully created: {result.get('doc_key', 'unknown')}")
        return 0
    return 1
