#!/usr/bin/env python3
"""
Script to update Jama items from a JSON configuration file.
"""

import argparse
import json
import os
import sys

from py_jama_rest_client.client import APIException

from scripts.jama.common import get_field_names_from_schema, get_item_id, load_jama


def update_item_fields(
    jama,
    doc_key: str,
    updates: dict,
    overwrite: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Update fields for a Jama item.

    Args:
        jama: Jama client instance
        doc_key: Document key of the item to update
        updates: Dictionary of field base names to new values
        overwrite: If False, only update empty/missing fields
        dry_run: If True, don't actually update, just report

    Returns:
        True if updates were (or would be) applied, False otherwise
    """
    item_id = get_item_id(jama, doc_key)
    if not item_id:
        print(f"Error: Could not find item with document key '{doc_key}'", file=sys.stderr)
        return False

    item = jama.get_item(item_id)
    fields = item.get("fields", {})
    item_type_id = item.get("itemType")

    if not item_type_id:
        print(f"Error: Could not determine item type for {doc_key}", file=sys.stderr)
        return False

    schema_fields = get_field_names_from_schema(
        os.getenv("JAMA_URL", ""),
        os.getenv("CLIENT_ID", ""),
        item_type_id,
    )

    patch_operations = []

    for base_name, new_value in updates.items():
        actual_field_name = schema_fields.get(base_name)

        if not actual_field_name:
            print(f"Warning: field '{base_name}' not found in schema; skipping", file=sys.stderr)
            continue

        current_value = fields.get(actual_field_name)

        if current_value is None:
            op = "add"
            print(f"  Will ADD {base_name} ({actual_field_name}): {repr(new_value)[:100]}")
            patch_operations.append(
                {
                    "op": op,
                    "path": f"/fields/{actual_field_name}",
                    "value": new_value,
                }
            )
        elif not current_value or overwrite:
            op = "replace" if current_value else "add"
            print(f"  Will {op.upper()} {base_name} ({actual_field_name}): {repr(new_value)[:100]}")
            if current_value:
                print(f"    (overwriting: {str(current_value)[:50]!r}...)")
            patch_operations.append(
                {
                    "op": op,
                    "path": f"/fields/{actual_field_name}",
                    "value": new_value,
                }
            )
        else:
            print(f"  Skipping {base_name} ({actual_field_name}): already has value {str(current_value)[:50]!r}...")

    if not patch_operations:
        print(f"  No updates to apply for {doc_key}")
        return False

    if dry_run:
        print(f"  [DRY RUN] Would apply {len(patch_operations)} update(s) to {doc_key}")
        return True

    try:
        jama.patch_item(item_id, patch_operations)
        print(f"  Successfully updated {doc_key} with {len(patch_operations)} change(s)")
        return True
    except APIException as e:
        print(f"  Error updating {doc_key}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Update Jama items from a JSON configuration file.")
    parser.add_argument(
        "json_file",
        help='JSON file containing updates (format: {"DOC_KEY": {"field": "value", ...}})',
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing field values (default: only update empty/missing fields)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without actually making changes",
    )
    args = parser.parse_args()

    try:
        jama = load_jama()
    except Exception as e:
        print(f"Jama auth error: {e}", file=sys.stderr)
        return 2

    try:
        with open(args.json_file) as f:
            update_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{args.json_file}' not found", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{args.json_file}': {e}", file=sys.stderr)
        return 1

    if not isinstance(update_data, dict):
        print("Error: JSON must be a dictionary mapping document keys to field updates", file=sys.stderr)
        return 1

    total_items = len(update_data)
    updated_count = 0
    failed_count = 0
    skipped_count = 0

    print(f"Processing {total_items} item(s) from '{args.json_file}'")
    if args.dry_run:
        print("[DRY RUN MODE - No changes will be made]")
    if args.overwrite:
        print("[OVERWRITE MODE - Existing values will be replaced]")
    print("-" * 60)

    for doc_key, updates in update_data.items():
        if not isinstance(updates, dict):
            print(f"Error: Updates for '{doc_key}' must be a dictionary", file=sys.stderr)
            failed_count += 1
            continue

        print(f"\nItem: {doc_key}")
        success = update_item_fields(
            jama,
            doc_key,
            updates,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
        if success:
            updated_count += 1
        else:
            failed_count += 1

    print("\n" + "=" * 60)
    print(f"Summary: {updated_count} updated, {failed_count} failed, {skipped_count} skipped")

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
