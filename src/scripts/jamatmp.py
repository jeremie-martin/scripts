#!/usr/bin/env python3
"""
Script to find all upstream-linked Jama items for a source key and link them
to a target item key. Supports dry-run mode.
"""

from __future__ import annotations

import argparse

from py_jama_rest_client.client import AlreadyExistsException, APIException

from scripts.jama.common import get_item_id, load_jama, rate_limit


def get_upstream_items(jama, item_id: int):
    """Return a list of dicts for items that link upstream to the given item."""
    # You can also use get_items_upstream_relationships if you need the raw relationships
    return jama.get_items_upstream_related(item_id)


def link_upstream_to_target(jama, source_key: str, target_key: str, dry_run: bool):
    print(f"\n— Processing mapping {source_key} → {target_key} —")
    src_id = get_item_id(jama, source_key)
    tgt_id = get_item_id(jama, target_key)

    if not src_id:
        print(f"  ✗ Source item not found: {source_key}")
        return
    if not tgt_id:
        print(f"  ✗ Target item not found: {target_key}")
        return

    upstream = get_upstream_items(jama, src_id)
    if not upstream:
        print(f"  – No upstream links found for {source_key} (ID {src_id})")
        return

    print(f"  • Found {len(upstream)} upstream item(s) for {source_key} (ID {src_id}):")
    for itm in upstream:
        up_id = itm.get("id")
        up_key = itm.get("documentKey", f"(ID {up_id})")
        action = f"Link {up_key} (ID {up_id}) → {target_key} (ID {tgt_id})"
        if dry_run:
            print(f"    → [DRY-RUN] {action}")
        else:
            try:
                jama.post_relationship(from_item=up_id, to_item=tgt_id)
                print(f"    ✓ {action}")
            except AlreadyExistsException:
                print(f"    → Skipped, relationship already exists: {action}")
            except APIException as e:
                print(f"    ✗ Failed to create relationship: {action}: {e}")
            # Be polite to the API
            rate_limit(0.1)


def main():
    parser = argparse.ArgumentParser(description="Link all upstream items of a source key to a target key in Jama")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done, without making any API changes")
    args = parser.parse_args()

    # Initialize client
    try:
        jama = load_jama()
    except Exception as e:
        raise SystemExit(f"Error: {e}")

    # Define your mappings here
    mappings = [
        ("ABSD-ImpSI-2", "ABSD-IMP_INT-1"),
        ("ABSD-ImpSI-3", "ABSD-IMP_INT-2"),
    ]

    for src, tgt in mappings:
        link_upstream_to_target(jama, src, tgt, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
