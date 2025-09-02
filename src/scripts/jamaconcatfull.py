#!/usr/bin/env python3
"""
Script to inspect Jama items and display their full structure.
Useful for understanding item types and field structures.
Handles both individual items and folders (with optional recursive traversal).
"""

import sys
import argparse
import os
from typing import Optional, List, Set
import pyperclip
from scripts.jama.common import load_jama, get_item_id, collect_keys_from_folder



def fetch_fields(jama_client, document_key: str) -> Optional[str]:
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
    lines: List[str] = [f"{item.get('documentKey', document_key)} ({item_id}) fields:"]
    for key, value in fields.items():
        # Normalize value for display
        if isinstance(value, str):
            display_value = value.strip()
        else:
            display_value = repr(value)
        lines.append(f"{key}: {display_value}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Download and output Jama item fields by document key or folder key."
    )
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

    # Collect document keys, expanding folders if requested
    document_keys: List[str] = []
    # if args.keys is a text file which exists, just loads all the keys from the text file (either absolute or relative paths)
    if os.path.isfile(args.keys[0]):
        with open(args.keys[0], "r") as f:
            keys = [line.strip() for line in f if line.strip()]
    else:
        keys = args.keys

    for key in keys:
        if "FLD" in key.upper():
            folder_id = get_item_id(jama, key)
            if not folder_id:
                print(
                    f"Error: Could not find folder with document key '{key}'",
                    file=sys.stderr,
                )
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

    outputs: List[str] = []
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
