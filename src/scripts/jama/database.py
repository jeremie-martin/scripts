#!/usr/bin/env python3
"""Enhanced Jama database with prefix mappings and item type caching."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from py_jama_rest_client.client import JamaClient

__all__ = [
    "DB_DIR",
    "DB_FILE",
    "get_item_type_fields",
    "load_database",
    "lookup_prefix",
    "migrate_from_v1",
    "save_database",
    "sync_database",
]

# New database location
DB_DIR = Path.home() / ".local" / "share" / "jama"
DB_FILE = DB_DIR / "database.json"

# Old jamafetch database location for migration
OLD_DB_DIR = Path.home() / ".local" / "share" / "jamafetch"
OLD_DB_FILE = OLD_DB_DIR / "item_types.json"

CURRENT_VERSION = 2


def _empty_database() -> dict[str, Any]:
    """Return an empty database structure."""
    return {
        "version": CURRENT_VERSION,
        "item_types": {},
        "prefix_map": {},
    }


def load_database() -> dict[str, Any]:
    """Load database from disk, migrating from v1 if needed."""
    if DB_FILE.exists():
        try:
            with open(DB_FILE) as f:
                data = json.load(f)
            # Check version and migrate if needed
            if data.get("version", 1) < CURRENT_VERSION:
                data = _migrate_database(data)
                save_database(data)
            return data
        except (OSError, json.JSONDecodeError) as e:
            print(f"Warning: Failed to load database ({e}), starting fresh", file=sys.stderr)
            return _empty_database()

    # Try to migrate from old jamafetch database
    if OLD_DB_FILE.exists():
        data = migrate_from_v1()
        save_database(data)
        return data

    return _empty_database()


def save_database(database: dict[str, Any]) -> None:
    """Save database to disk."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    database["version"] = CURRENT_VERSION
    with open(DB_FILE, "w") as f:
        json.dump(database, f, indent=2)


def _migrate_database(old_data: dict[str, Any]) -> dict[str, Any]:
    """Migrate database from older versions."""
    version = old_data.get("version", 1)

    if version == 1:
        # v1 had flat item_types dict at root level
        return {
            "version": CURRENT_VERSION,
            "item_types": old_data.get("item_types", old_data),
            "prefix_map": old_data.get("prefix_map", {}),
        }

    return old_data


def migrate_from_v1() -> dict[str, Any]:
    """Migrate from old jamafetch database (v1 format)."""
    database = _empty_database()

    if not OLD_DB_FILE.exists():
        return database

    try:
        with open(OLD_DB_FILE) as f:
            old_data = json.load(f)

        # Old format was just {item_type_id: {fields: ..., item_type_name: ..., doc_key_prefix: ...}}
        if isinstance(old_data, dict):
            for item_type_id, item_info in old_data.items():
                if isinstance(item_info, dict) and "fields" in item_info:
                    database["item_types"][item_type_id] = item_info

        print(f"Migrated {len(database['item_types'])} item types from old database", file=sys.stderr)

    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to migrate old database ({e})", file=sys.stderr)

    return database


def lookup_prefix(doc_key: str) -> tuple[int | None, int | None]:
    """
    Look up project_id and item_type_id from a document key prefix.

    Args:
        doc_key: Document key like "ABC-DI2-123"

    Returns:
        Tuple of (project_id, item_type_id) or (None, None) if not found
    """
    database = load_database()
    prefix_map = database.get("prefix_map", {})

    # Extract prefix from doc_key (everything before the last number segment)
    # e.g., "ABC-DI2-123" -> "ABC-DI2"
    match = re.match(r"^(.+?)-\d+$", doc_key)
    if not match:
        return None, None

    prefix = match.group(1)

    if prefix in prefix_map:
        info = prefix_map[prefix]
        return info.get("project_id"), info.get("item_type_id")

    return None, None


def _extract_prefix_from_doc_key(doc_key: str) -> str | None:
    """Extract the prefix portion from a document key."""
    match = re.match(r"^(.+?)-\d+$", doc_key)
    return match.group(1) if match else None


def get_item_type_fields(jama: JamaClient, item_type_id: int, database: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Get field information for an item type, using database or fetching from Jama.

    Args:
        jama: Jama client
        item_type_id: Item type ID
        database: Optional database dict (will be loaded if not provided)

    Returns:
        Dictionary of field name -> field info
    """
    if database is None:
        database = load_database()

    str_item_type_id = str(item_type_id)

    if str_item_type_id in database.get("item_types", {}):
        return database["item_types"][str_item_type_id]["fields"]

    # Fetch from Jama API
    item_type = jama.get_item_type(item_type_id)
    fields = item_type.get("fields", [])

    field_info: dict[str, Any] = {}
    for field in fields:
        field_name = field.get("name")
        field_type = field.get("fieldType")
        picklist = field.get("pickList")

        if not field_name:
            continue

        field_data: dict[str, Any] = {
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
                except Exception as e:
                    print(f"Warning: Failed to fetch picklist options for {picklist_id}: {e}", file=sys.stderr)
                    field_data.pop("picklist_id", None)

        field_info[field_name] = field_data

    # Store in database
    if "item_types" not in database:
        database["item_types"] = {}

    database["item_types"][str_item_type_id] = {
        "item_type_name": item_type.get("name"),
        "type_key": item_type.get("typeKey"),
        "doc_key_prefix": "",
        "fields": field_info,
    }

    save_database(database)
    print(f"Updated database with item type {item_type_id}", file=sys.stderr)

    return field_info


def sync_database(jama: JamaClient, *, verbose: bool = True) -> dict[str, Any]:
    """
    Sync database from Jama API, refreshing item types and building prefix map.

    Args:
        jama: Jama client
        verbose: Print progress messages

    Returns:
        Updated database
    """
    database = load_database()

    if verbose:
        print("Fetching projects from Jama...", file=sys.stderr)

    try:
        projects = jama.get_projects()
    except Exception as e:
        print(f"Error fetching projects: {e}", file=sys.stderr)
        return database

    prefix_map: dict[str, dict[str, int]] = {}

    for project in projects:
        project_id = project.get("id")
        project_key = project.get("projectKey", "")

        if not project_id:
            continue

        if verbose:
            print(f"Processing project {project_key} (ID: {project_id})...", file=sys.stderr)

        try:
            item_types = jama.get_item_types(project_id)
        except Exception as e:
            print(f"  Warning: Failed to get item types for project {project_key}: {e}", file=sys.stderr)
            continue

        for item_type in item_types:
            if not isinstance(item_type, dict):
                continue

            item_type_id = item_type.get("id")
            display = item_type.get("display")
            display_prefix = display.get("documentKey", "") if isinstance(display, dict) else ""

            if not item_type_id:
                continue

            # Build prefix from project key and type-specific prefix
            if display_prefix:
                full_prefix = f"{project_key}-{display_prefix}" if project_key else display_prefix
                prefix_map[full_prefix] = {
                    "project_id": project_id,
                    "item_type_id": item_type_id,
                }

            # Cache item type fields and update name
            str_item_type_id = str(item_type_id)
            item_type_name = item_type.get("name")

            if str_item_type_id not in database.get("item_types", {}):
                try:
                    get_item_type_fields(jama, item_type_id, database)
                except Exception as e:
                    print(f"  Warning: Failed to cache item type {item_type_id}: {e}", file=sys.stderr)

            # Always update item type name and typeKey if we have them (fixes old entries)
            if str_item_type_id in database.get("item_types", {}):
                if item_type_name:
                    database["item_types"][str_item_type_id]["item_type_name"] = item_type_name
                type_key = item_type.get("typeKey")
                if type_key:
                    database["item_types"][str_item_type_id]["type_key"] = type_key

    database["prefix_map"] = prefix_map
    save_database(database)

    if verbose:
        print(f"Synced {len(prefix_map)} prefixes and {len(database.get('item_types', {}))} item types", file=sys.stderr)

    return database


def get_item_type_by_name(database: dict[str, Any], name: str) -> int | None:
    """
    Look up an item type ID by name (case-insensitive).

    Args:
        database: Database dict
        name: Item type name to find

    Returns:
        Item type ID or None if not found
    """
    name_lower = name.lower()
    for item_type_id, item_info in database.get("item_types", {}).items():
        item_name = item_info.get("item_type_name", "")
        if item_name.lower() == name_lower:
            return int(item_type_id)
    return None


def get_prefix_info(database: dict[str, Any], doc_key: str) -> dict[str, Any] | None:
    """
    Get full prefix info for a document key.

    Args:
        database: Database dict
        doc_key: Document key

    Returns:
        Dict with project_id, item_type_id or None
    """
    prefix = _extract_prefix_from_doc_key(doc_key)
    if not prefix:
        return None
    return database.get("prefix_map", {}).get(prefix)
