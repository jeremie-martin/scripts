#!/usr/bin/env python3
"""
Script to inspect Jama items and display their full structure.
Useful for understanding item types and field structures.
Handles both individual items and folders (with optional recursive traversal),
with optional HTML cleaning and Markdown conversion for string fields.
"""

import argparse
import sys

import pyperclip

from scripts.jama.common import (
    clean_html_content,
    expand_keys,
    get_item_id,
    html_to_markdown,
    load_jama,
    load_keys_from_file_or_args,
)


def fetch_fields(
    jama_client,
    document_key: str,
    *,
    clean_html_output: bool = False,
    output_markdown: bool = False,
) -> str | None:
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
        # Normalize value for display, optionally cleaning/converting HTML content
        if isinstance(value, str):
            display_value = value.strip()
            if clean_html_output or output_markdown:
                display_value = clean_html_content(display_value)
            if output_markdown:
                display_value = html_to_markdown(display_value, clean=False)
        else:
            display_value = repr(value)
        suffix = " (Markdown)" if output_markdown and isinstance(value, str) else ""
        lines.append(f"{key}{suffix}: {display_value}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Download and output Jama item fields by document key or container key.")
    parser.add_argument(
        "--clean-html",
        action="store_true",
        help="Strip inline styles and span wrappers from string field values before output.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Convert string field values to Markdown (implies --clean-html).",
    )
    parser.add_argument(
        "keys",
        nargs="+",
        metavar="JAMA_KEY",
        help="One or more Jama document keys (e.g., ABSD-SWVER-257) or container keys (folders/sets/components).",
    )
    args = parser.parse_args()

    # Initialize JAMA client using shared helper
    try:
        jama = load_jama()
    except Exception as e:
        sys.exit(f"Error: {e}")

    def handle_missing(key: str) -> None:
        print(
            f"Error: Could not find item with document key '{key}'",
            file=sys.stderr,
        )

    def handle_empty(key: str) -> None:
        print(f"No items found in container '{key}'.", file=sys.stderr)

    keys = load_keys_from_file_or_args(args.keys)
    document_keys = expand_keys(
        jama,
        keys,
        on_missing=handle_missing,
        on_empty_container=handle_empty,
    )

    if not document_keys:
        sys.exit(1)

    outputs: list[str] = []
    for doc_key in document_keys:
        result = fetch_fields(
            jama,
            doc_key,
            clean_html_output=args.clean_html or args.markdown,
            output_markdown=args.markdown,
        )
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
