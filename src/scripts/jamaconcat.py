#!/usr/bin/env python3
"""
Script to download generic Jama items by document key (or all items in a folder detected by key prefix),
fetch raw HTML description, and output each item's title and description,
optionally cleaning HTML, converting to Markdown, and copying to the clipboard.

Usage:
    python your_script.py [--recursive] [--version] JAMA_KEY [JAMA_KEY ...]
Options:
    -r, --recursive   Recursively fetch items in subfolders for folder keys.
    -v, --version     Fetch and append the Jama item version to each document key.
"""

import argparse
import sys

import pyperclip

from scripts.jama.common import (
    clean_html_content,
    expand_keys,
    find_field_key,
    get_item_id,
    html_to_markdown,
    jama_url_for_item,
    load_jama,
    load_keys_from_file_or_args,
)


def fetch_item(
    jama,
    document_key: str,
    *,
    fetch_version: bool = False,
    clean_html_output: bool = False,
    output_markdown: bool = False,
) -> str | None:
    """
    Download a generic item from Jama and return formatted string:

    Document Key: <document_key>[v<version>]
    Document Title: <title>
    Document Description:
    <Raw HTML Description>
    """
    item_id = get_item_id(jama, document_key)
    if not item_id:
        print(
            f"Error: Could not find item with document key '{document_key}'",
            file=sys.stderr,
        )
        return None

    try:
        item = jama.get_item(item_id)
    except Exception as e:
        print(f"Error retrieving item '{document_key}': {e}", file=sys.stderr)
        return None

    fields = item.get("fields", {})
    title = fields.get("name", document_key).strip()
    desc_key = find_field_key(fields, "description")
    description_html = fields.get(desc_key, "") if desc_key else ""

    if clean_html_output or output_markdown:
        description_html = clean_html_content(description_html)
    if output_markdown:
        description_html = html_to_markdown(description_html, clean=False)

    print("Processing item:", document_key)

    # optionally fetch version metadata
    version_suffix = ""
    if fetch_version:
        try:
            versions = jama.get_item_versions(item_id)
            latest = max(v.get("versionNumber", 1) for v in versions) if versions else 1
        except Exception as e:
            print(
                f"Warning: could not fetch versions for '{document_key}': {e}",
                file=sys.stderr,
            )
            latest = 1
        version_suffix = f"v{latest}"

    url = jama_url_for_item(item_id)

    description_label = "Document Description"
    if output_markdown:
        description_label += " (Markdown)"

    return (
        f"Document Key: {document_key}{version_suffix}\n"
        f"Document URL: {url}\n"
        f"Document Title: {title}\n"
        f"{description_label}:\n{description_html}\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Download and output generic Jama items with raw HTML descriptions.")
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively fetch items in subfolders for folder keys.",
    )
    parser.add_argument(
        "-v",
        "--version",
        dest="fetch_version",
        action="store_true",
        help="Fetch and append the Jama item version to each document key.",
    )
    parser.add_argument(
        "--clean-html",
        action="store_true",
        help="Strip inline styles and span wrappers from item descriptions before output.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Output item descriptions as Markdown (implies --clean-html).",
    )
    parser.add_argument(
        "keys",
        nargs="+",
        metavar="JAMA_KEY",
        help="One or more Jama document keys (e.g., ABSD-SWVER-257) or folder keys containing 'FLD'.",
    )
    args = parser.parse_args()

    try:
        jama = load_jama()
    except Exception as e:
        print(f"Jama auth error: {e}", file=sys.stderr)
        return 2

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
        result = fetch_item(
            jama,
            doc_key,
            fetch_version=args.fetch_version,
            clean_html_output=args.clean_html or args.markdown,
            output_markdown=args.markdown,
        )
        if result:
            outputs.append(result)

    combined = "\n".join(outputs)
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
    raise SystemExit(main())
