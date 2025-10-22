#!/usr/bin/env python3
import argparse
import os
import sys

from scripts.jama.common import expand_keys, find_field_key, get_field_names_from_schema, get_item_id, load_jama


def update_test_fields(jama_client, doc_id: str):
    """
    Updates empty test fields with default values for a given document key.
    Uses item type schema to find correct field names, including fields that
    are missing from the item response when empty.
    """
    try:
        # Find the item ID by document key
        item_id = get_item_id(jama_client, doc_id)
        if not item_id:
            print(f"Error: Could not find item with document key '{doc_id}'", file=sys.stderr)
            return

        # Retrieve current fields and item type
        item = jama_client.get_item(item_id)
        fields = item.get("fields", {})
        item_type_id = item.get("itemType")

        if not item_type_id:
            print(f"Error: Could not determine item type for {doc_id}", file=sys.stderr)
            return

        # Get field name mappings from schema (cached)
        schema_fields = get_field_names_from_schema(
            os.getenv("JAMA_URL", ""),
            os.getenv("CLIENT_ID", ""),
            item_type_id
        )

        # Default field values
        field_mappings = {
            "initial_conditions": "N/A",
            "test_inputs": "N/A",
            "data_collection_actions": "Operator saves the intermediate report.",
            "assumptions__constraints": "N/A",
            "test_outputs": ("Test result intermediate report containing the date and time the test was run along with the test result."),
        }

        updates = []

        # For each field we want to update, find the actual schema field name
        for base, default in field_mappings.items():
            # First try to get from schema
            actual_field_name = schema_fields.get(base)

            if actual_field_name:
                # Check if field is missing or empty
                current_value = fields.get(actual_field_name)
                if current_value is None:
                    # Field doesn't exist in the response, use 'add' operation
                    updates.append({
                        "op": "add",
                        "path": f"/fields/{actual_field_name}",
                        "value": default,
                    })
                    print(f"Will add {base} ({actual_field_name}): '{default}'")
                elif not current_value:  # Empty string or other falsy value
                    # Field exists but is empty, use 'replace' operation
                    updates.append({
                        "op": "replace",
                        "path": f"/fields/{actual_field_name}",
                        "value": default,
                    })
                    print(f"Will replace {base} ({actual_field_name}): '{default}'")
                else:
                    print(f"Field {base} ({actual_field_name}) already has value: '{current_value[:50]}...' - skipping")
            else:
                # Fallback to old method for fields that don't follow the $suffix pattern
                fallback_field = find_field_key(fields, base)
                if fallback_field:
                    current_value = fields.get(fallback_field)
                    if not current_value:
                        # Field exists in response but is empty, use 'replace'
                        updates.append({
                            "op": "replace",
                            "path": f"/fields/{fallback_field}",
                            "value": default,
                        })
                        print(f"Will replace {base} ({fallback_field}): '{default}' (fallback method)")
                    else:
                        print(f"Field {base} ({fallback_field}) already has value - skipping")
                else:
                    print(f"Warning: field '{base}' not found in schema or item; skipping", file=sys.stderr)

        # Apply updates if any
        if updates:
            print(f"\nApplying {len(updates)} updates to {doc_id}:")
            for update in updates:
                print(f"  {update['path']} = '{update['value']}'")
            jama_client.patch_item(item_id, updates)
            print(f"Successfully updated empty fields for {doc_id}")
        else:
            print(f"No empty fields to update for {doc_id}")

    except Exception as e:
        print(f"Error updating {doc_id}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Update empty test fields for Jama items by document key or all items in a folder.")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recursively fetch items in subfolders for folder keys.")
    parser.add_argument("ids", nargs="*", help="One or more Jama document keys or folder keys containing 'FLD'.")
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

    def handle_missing(key: str) -> None:
        label = "folder" if "FLD" in key.upper() else "item"
        print(f"Error: Could not find {label} with document key '{key}'", file=sys.stderr)

    def handle_empty(key: str) -> None:
        label = "folder" if "FLD" in key.upper() else "container"
        print(f"No items found in {label} '{key}'.", file=sys.stderr)

    document_keys = expand_keys(
        jama,
        input_ids,
        recursive=args.recursive,
        on_missing=handle_missing,
        on_empty_container=handle_empty,
    )

    if not document_keys:
        sys.exit(1)

    print("\nAttempting updates...")
    for doc_id in document_keys:
        update_test_fields(jama, doc_id)


if __name__ == "__main__":
    raise SystemExit(main())
