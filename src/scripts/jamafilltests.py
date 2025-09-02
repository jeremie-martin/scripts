#!/usr/bin/env python3
import sys
import json
import argparse
from typing import List
from scripts.jama.common import (
    load_jama,
    get_item_id,
    collect_keys_from_folder,
    find_field_key,
)



def update_test_fields(jama_client, doc_id: str):
    """
    Updates empty test fields with default values for a given document key.
    """
    try:
        # Find the item ID by document key
        item_id = get_item_id(jama_client, doc_id)
        if not item_id:
            print(f"Error: Could not find item with document key '{doc_id}'", file=sys.stderr)
            return

        # Retrieve current fields
        item = jama_client.get_item(item_id)
        fields = item.get("fields", {})

        # Default field values
        field_mappings = {
            "initial_conditions": "N/A",
            "test_inputs": "N/A",
            "data_collection_actions": "Operator saves the intermediate report.",
            "assumptions__constraints": "N/A",
            "test_outputs": (
                "Test result intermediate report containing the date and time the test was run "
                "along with the test result."
            ),
        }

        updates = []
        # Determine actual keys present on this item matching our bases
        key_map = { base: find_field_key(fields, base) for base in field_mappings }

        # Prepare updates only for actual keys present and currently empty
        for base, default in field_mappings.items():
            actual = key_map.get(base)
            if actual:
                if not fields.get(actual):
                    updates.append({
                        "op": "replace",
                        "path": f"/fields/{actual}",
                        "value": default,
                    })
            else:
                print(f"Warning: field '{base}' not present on item; skipping", file=sys.stderr)

        # Apply updates if any
        if updates:
            print(f"\nApplying updates to {doc_id}:", json.dumps(updates, indent=2))
            jama_client.patch_item(item_id, updates)
            print(f"Successfully updated empty fields for {doc_id}")
        else:
            print(f"No empty fields to update for {doc_id}")

    except Exception as e:
        print(f"Error updating {doc_id}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Update empty test fields for Jama items by document key or all items in a folder."
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recursively fetch items in subfolders for folder keys."
    )
    parser.add_argument(
        "ids", nargs="*",
        help="One or more Jama document keys or folder keys containing 'FLD'."
    )
    args = parser.parse_args()

    try:
        jama = load_jama()
    except Exception as e:
        print(f"Jama auth error: {e}", file=sys.stderr)
        return 2

    # Gather IDs from args or stdin
    input_ids = []
    if args.ids:
        input_ids = args.ids
    elif not sys.stdin.isatty():
        input_ids = [line.strip() for line in sys.stdin if line.strip()]

    if not input_ids:
        parser.print_usage()
        sys.exit(1)

    # Resolve folder keys into document keys
    document_keys: List[str] = []
    for key in input_ids:
        if "FLD" in key.upper():
            folder_id = get_item_id(jama, key)
            if not folder_id:
                print(f"Error: Could not find folder with document key '{key}'", file=sys.stderr)
                continue
            found = collect_keys_from_folder(jama, folder_id, recursive=args.recursive)
            if not found:
                print(f"No items found in folder '{key}'.", file=sys.stderr)
            else:
                document_keys.extend(found)
        else:
            document_keys.append(key)

    if not document_keys:
        sys.exit(1)

    print("\nAttempting updates...")
    for doc_id in document_keys:
        update_test_fields(jama, doc_id)


if __name__ == "__main__":
    raise SystemExit(main())
