#!/usr/bin/env python3
"""
Script to inspect Jama items and display their full structure.
Useful for understanding item types and field structures.
Handles both individual items and folders (with optional recursive traversal).
"""

import argparse
import sys

import pyperclip

from scripts.jama.common import expand_keys, get_item_id, load_jama, load_keys_from_file_or_args


def fetch_fields(jama_client, document_key: str) -> str | None:
    """
    Download a Jama item by document key and return a formatted string of its fields:

    FieldName: FieldValue
    ...
    """
    item_id = get_item_id(jama_client, document_key)
    if not item_id:
        print(
            f"Error: Could not find item with document key '{document_key}'",
            file=sys.stderr,
        )
        return None

    try:
        item = jama_client.get_item(item_id)
    except Exception as e:
        print(f"Error retrieving item '{document_key}': {e}", file=sys.stderr)
        return None

    fields = item.get("fields", {})
    lines: list[str] = [f"{item.get('documentKey', document_key)} ({item_id}) fields:"]
    for key, value in fields.items():
        # Normalize value for display
        display_value = value.strip() if isinstance(value, str) else repr(value)
        lines.append(f"{key}: {display_value}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Download and output Jama item fields by document key or folder key.")
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively fetch items in subfolders for folder keys.",
    )
    parser.add_argument(
        "keys",
        nargs="+",
        metavar="JAMA_KEY",
        help="One or more Jama document keys (e.g., ABSD-SWVER-257) or folder keys containing 'FLD'.",
    )
    args = parser.parse_args()

    # Initialize JAMA client using shared helper
    try:
        jama = load_jama()
    except Exception as e:
        sys.exit(f"Error: {e}")

    def handle_missing(key: str) -> None:
        label = "folder" if "FLD" in key.upper() else "item"
        print(
            f"Error: Could not find {label} with document key '{key}'",
            file=sys.stderr,
        )

    def handle_empty(key: str) -> None:
        label = "folder" if "FLD" in key.upper() else "container"
        print(f"No items found in {label} '{key}'.", file=sys.stderr)

    keys = load_keys_from_file_or_args(args.keys)
    document_keys = expand_keys(
        jama,
        keys,
        recursive=args.recursive,
        on_missing=handle_missing,
        on_empty_container=handle_empty,
    )

    if not document_keys:
        sys.exit(1)

    outputs: list[str] = []
    for doc_key in document_keys:
        result = fetch_fields(jama, doc_key)
        if result:
            outputs.append(result)

    combined = "\n\n".join(outputs)
    if not combined:
        sys.exit(1)

    # Print to terminal
    print(combined)

    # Copy combined output to clipboard by default
    try:
        pyperclip.copy(combined)
        print("\nCombined output has been copied to the clipboard.")
    except Exception as e:
        print(f"\nFailed to copy to clipboard: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
