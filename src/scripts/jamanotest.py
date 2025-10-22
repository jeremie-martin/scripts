#!/usr/bin/env python3
"""
jamanotest.py

Checks downstream test coverage for Jama items and folders.
For each provided Jama document or folder key, fetches the item(s), retrieves downstream relationships,
filters for test links (document keys starting with "ABSD-SWVER-"), and reports coverage.

Usage:
    python jamanotest.py [--recursive] JAMA_KEY [JAMA_KEY ...]
Options:
    -r, --recursive   Recursively fetch items in subfolders for folder keys.
"""

import argparse
import sys

from py_jama_rest_client.client import APIException

from scripts.jama.common import expand_keys, get_item_id, load_jama


def get_downstream_coverage(jama, item_id: int) -> list[str]:
    """Fetch downstream-relationship items and return those with test document keys."""
    try:
        rels = jama.get_items_downstream_relationships(item_id)
    except APIException as e:
        print(f"Error fetching downstream for {item_id}: {e}", file=sys.stderr)
        return []
    covered = []
    for rel in rels:
        to_id = rel.get("toItem")
        # fetch the linked item to get its documentKey
        try:
            item = jama.get_item(to_id)
            doc_key = item.get("documentKey") or item.get("fields", {}).get("documentKey")
            if doc_key and doc_key.startswith("ABSD-SWVER-"):
                covered.append(doc_key)
        except APIException:
            continue
    return covered


def check_coverage_for_key(jama, doc_key: str) -> bool:
    """Check and report coverage for a single document key."""
    item_id = get_item_id(jama, doc_key)
    if not item_id:
        print(f"Error: item '{doc_key}' not found.")
        return False
    coverage = get_downstream_coverage(jama, item_id)
    print(f"\nDocument Key: {doc_key}")
    if coverage:
        print("Covered by tests:")
        for ck in coverage:
            print(f"  - {ck}")
        return True
    else:
        print("No downstream test items found!")
        return False


def main():
    parser = argparse.ArgumentParser(description="Check test coverage for Jama items by downstream links.")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recursively expand folder keys.")
    parser.add_argument("keys", nargs="+", metavar="JAMA_KEY", help="Jama document or folder key (e.g. ABSD-SWVER-257 or FLD-XYZ)")
    args = parser.parse_args()

    try:
        jama = load_jama()
    except Exception as e:
        print(f"Jama auth error: {e}", file=sys.stderr)
        return 2

    def handle_missing(key: str) -> None:
        label = "folder" if "FLD" in key.upper() else "item"
        print(f"Error: {label} '{key}' not found.")

    def handle_empty(key: str) -> None:
        label = "folder" if "FLD" in key.upper() else "container"
        print(f"No items in {label} '{key}'")

    all_keys = expand_keys(
        jama,
        args.keys,
        recursive=args.recursive,
        on_missing=handle_missing,
        on_empty_container=handle_empty,
    )

    if not all_keys:
        sys.exit(1)

    total = len(all_keys)
    covered_count = 0
    print("\n=== Test Coverage Report ===")
    for k in all_keys:
        if check_coverage_for_key(jama, k):
            covered_count += 1

    print("\n=== Summary ===")
    print(f"Total items checked: {total}")
    print(f"Items covered by tests: {covered_count}")
    print(f"Items missing coverage: {total - covered_count}")


if __name__ == "__main__":
    raise SystemExit(main())
