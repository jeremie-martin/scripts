#!/usr/bin/env python3

"""
Jama Auto Linker Script
Automatically creates relationships between SRS requirements and interface specifications
based on the comprehensive mapping analysis.
"""

import sys

from py_jama_rest_client.client import APIException

from scripts.jama.common import load_jama, rate_limit

# Interface ID to Document Key mapping
INTERFACE_ID_TO_DOCUMENT_KEY = {
    # Low-level interfaces
    "IFWINT-001-01": "ABSD-IMP_INT-17",
    "IFWINT-001-02": "ABSD-IMP_INT-18",
    "IFWINT-001-03": "ABSD-IMP_INT-3",
    "IFWINT-001-04": "ABSD-IMP_INT-20",
    "IFWINT-001-05": "ABSD-IMP_INT-21",
    "IFWINT-001-06": "ABSD-IMP_INT-22",
    "IFWINT-001-07": "ABSD-IMP_INT-23",
    "IFWINT-001-08": "ABSD-IMP_INT-24",
    "IFWINT-002-01": "ABSD-IMP_INT-27",
    "IFWINT-002-02": "ABSD-IMP_INT-26",
    "IFWINT-002-03": "ABSD-IMP_INT-30",
    "IFWINT-002-04": "ABSD-IMP_INT-7",
    "IFWINT-002-05": "ABSD-IMP_INT-25",
    "IFWINT-002-06": "ABSD-IMP_INT-5",
    "IFWINT-002-07": "ABSD-IMP_INT-28",
    "IFWINT-002-08": "ABSD-IMP_INT-19",
    "IFWINT-002-09": "ABSD-IMP_INT-29",
    "IFWINT-003-01": "ABSD-IMP_INT-14",
    "IFWINT-003-02": "ABSD-IMP_INT-15",
    "IFWINT-003-03": "ABSD-IMP_INT-16",
    # High-level interfaces
    "IFWINT-001": "ABSD-IMP_INT-1",
    "IFWINT-002": "ABSD-IMP_INT-2",
    "INT-001": "ABSD-IMP_INT-6",
    "IMPINT-001": "ABSD-IMP_INT-8",
    "IMPINT-002": "ABSD-IMP_INT-9",
    "IMPINT-003": "ABSD-IMP_INT-10",
    "IMPINT-004": "ABSD-IMP_INT-11",
    "IMPINT-005": "ABSD-IMP_INT-12",
    "IMPINT-006": "ABSD-IMP_INT-13",
}

# SRS to Interface mapping based on the comprehensive analysis
SRS_TO_INTERFACE_MAPPING = {
    "ABSD-DI3_IMP-207": ["INT-001", "IFWINT-001-01", "IFWINT-002-01", "IFWINT-003-01"],
    "ABSD-DI3_IMP-208": ["INT-001", "IFWINT-001-01", "IFWINT-002-01", "IFWINT-003-01"],
    "ABSD-DI3_IMP-209": ["INT-001", "IFWINT-001-01", "IFWINT-002-01", "IFWINT-003-01"],
    "ABSD-DI3_IMP-210": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-02",
        "IFWINT-002-01",
        "IFWINT-002-03",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-211": ["INT-001", "IFWINT-001-01", "IFWINT-003-01"],
    "ABSD-DI3_IMP-212": ["INT-001", "IFWINT-001-01", "IFWINT-003-01"],
    "ABSD-DI3_IMP-213": ["INT-001", "IFWINT-001-01", "IFWINT-003-01"],
    "ABSD-DI3_IMP-214": ["INT-001", "IFWINT-001-01", "IFWINT-003-01"],
    "ABSD-DI3_IMP-216": ["INT-001", "IFWINT-001-01", "IFWINT-002-01", "IFWINT-003-01"],
    "ABSD-DI3_IMP-217": ["INT-001", "IFWINT-001-01", "IMPINT-004", "IFWINT-003-01"],
    "ABSD-DI3_IMP-218": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IMPINT-001",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-219": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IMPINT-001",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-220": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IMPINT-001",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-221": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IMPINT-001",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-222": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IMPINT-001",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-223": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IMPINT-001",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-224": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IMPINT-001",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-249": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IFWINT-001-07",
        "IFWINT-002-08",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-225": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IFWINT-001-07",
        "IFWINT-002-08",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-226": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-002-08",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-227": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-002-08",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-390": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-002-08",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-228": ["INT-001", "IFWINT-001-01", "IFWINT-001-07", "IFWINT-003-01"],
    "ABSD-DI3_IMP-229": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-06",
        "IMPINT-005",
        "IFWINT-002-07",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-230": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IFWINT-001-06",
        "IMPINT-001",
        "IMPINT-005",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-231": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-04",
        "IMPINT-006",
        "IFWINT-002-05",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-232": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-05",
        "IMPINT-001",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-233": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-03",
        "IMPINT-003",
        "IFWINT-002-04",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-234": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-03",
        "IMPINT-003",
        "IFWINT-002-04",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-235": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-03",
        "IMPINT-003",
        "IFWINT-002-04",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-389": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-03",
        "IMPINT-003",
        "IMPINT-006",
        "IFWINT-002-04",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-236": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-03",
        "IMPINT-003",
        "IFWINT-002-04",
        "IFWINT-002-06",
        "IFWINT-003-01",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-237": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-002-02",
        "IFWINT-002-08",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-238": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-002-08",
        "IFWINT-002-09",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-239": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-02",
        "IFWINT-002-03",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-240": [
        "INT-001",
        "IFWINT-001-01",
        "IFWINT-001-02",
        "IFWINT-002-01",
        "IFWINT-002-03",
        "IFWINT-003-01",
    ],
    "ABSD-DI3_IMP-241": [
        "IFWINT-001-02",
        "IFWINT-001-08",
        "IFWINT-002-03",
        "IFWINT-002-09",
        "IFWINT-003-03",
    ],
    "ABSD-DI3_IMP-242": [
        "IFWINT-001-02",
        "IFWINT-001-03",
        "IFWINT-001-08",
        "IMPINT-003",
        "IFWINT-002-03",
        "IFWINT-002-04",
        "IFWINT-002-06",
        "IFWINT-002-09",
        "IFWINT-003-02",
        "IFWINT-003-03",
    ],
    "ABSD-DI3_IMP-243": [
        "IFWINT-001-06",
        "IMPINT-005",
        "IFWINT-002-02",
        "IFWINT-002-07",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-244": [
        "IFWINT-001-02",
        "IFWINT-002-03",
        "IFWINT-003-02",
        "IFWINT-003-03",
    ],
    "ABSD-DI3_IMP-245": [
        "IFWINT-001-02",
        "IFWINT-002-03",
        "IFWINT-003-02",
        "IFWINT-003-03",
    ],
    "ABSD-DI3_IMP-246": [
        "IFWINT-001-03",
        "IMPINT-003",
        "IFWINT-002-04",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-247": ["IFWINT-001-07", "IFWINT-002-08", "IFWINT-003-02"],
    "ABSD-DI3_IMP-248": [
        "IFWINT-001-07",
        "IFWINT-002-02",
        "IFWINT-002-08",
        "IFWINT-002-09",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-250": [
        "IFWINT-001-07",
        "IFWINT-002-02",
        "IFWINT-002-08",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-348": [
        "IFWINT-001-07",
        "IFWINT-002-02",
        "IFWINT-002-08",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-251": [
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-003-01",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-252": [
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-002-02",
        "IFWINT-002-08",
        "IFWINT-003-01",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-253": [
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-002-02",
        "IFWINT-002-08",
        "IFWINT-003-01",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-254": [
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-002-08",
        "IFWINT-003-01",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-255": [
        "IFWINT-001-01",
        "IFWINT-001-07",
        "IFWINT-002-02",
        "IFWINT-002-08",
        "IFWINT-003-01",
        "IFWINT-003-02",
    ],
    "ABSD-DI3_IMP-345": ["IFWINT-001-05", "IMPINT-001", "IFWINT-003-02"],
}


class JamaAutoLinker:
    def __init__(self):
        """Initialize the Jama Auto Linker with API connection."""
        self.jama = load_jama()
        self.item_cache = {}  # Cache for item ID lookups
        self.failed_lookups = set()  # Track failed lookups to avoid retries
        self.stats = {
            "total_srs": 0,
            "total_interfaces": 0,
            "total_mappings": 0,
            "successful_links": 0,
            "failed_links": 0,
            "skipped_links": 0,
            "srs_not_found": 0,
            "interface_not_found": 0,
        }

    def get_item_id(self, document_key: str) -> int | None:
        """Get Jama internal item ID from a document key with caching."""
        if document_key in self.item_cache:
            return self.item_cache[document_key]

        if document_key in self.failed_lookups:
            return None

        try:
            items = self.jama.get_abstract_items(contains=document_key)
            for item in items:
                if item.get("documentKey") == document_key:
                    item_id = item.get("id")
                    self.item_cache[document_key] = item_id
                    return item_id
        except APIException as e:
            print(f"API error looking up '{document_key}': {e}")
        except Exception as e:
            print(f"Unexpected error looking up '{document_key}': {e}")

        self.failed_lookups.add(document_key)
        return None

    def relationship_exists(self, from_item_id: int, to_item_id: int) -> bool:
        """Check if a relationship already exists between two items."""
        try:
            # Get downstream relationships from the source item
            downstream_rels = self.jama.get_items_downstream_relationships(from_item_id)

            # Check if target item is already linked
            for rel in downstream_rels:
                if rel.get("toItem") == to_item_id:
                    return True

            # Also check upstream relationships from the target item
            upstream_rels = self.jama.get_items_upstream_relationships(to_item_id)
            for rel in upstream_rels:
                if rel.get("fromItem") == from_item_id:
                    return True

        except APIException as e:
            print(f"Warning: Could not check existing relationships: {e}")
        except Exception as e:
            print(f"Warning: Unexpected error checking relationships: {e}")

        return False

    def create_relationship(self, from_item_id: int, to_item_id: int, from_key: str, to_key: str) -> bool:
        """Create a relationship between two items."""
        try:
            # Check if relationship already exists
            if self.relationship_exists(from_item_id, to_item_id):
                print(f"  → Relationship already exists: {from_key} ↔ {to_key}")
                self.stats["skipped_links"] += 1
                return True

            # Create the relationship
            relationship_id = self.jama.post_relationship(from_item=from_item_id, to_item=to_item_id)

            if relationship_id:
                print(f"  ✓ Created relationship: {from_key} → {to_key} (ID: {relationship_id})")
                self.stats["successful_links"] += 1
                return True
            else:
                print(f"  ✗ Failed to create relationship: {from_key} → {to_key}")
                self.stats["failed_links"] += 1
                return False

        except APIException as e:
            if "already exists" in str(e).lower():
                print(f"  → Relationship already exists: {from_key} ↔ {to_key}")
                self.stats["skipped_links"] += 1
                return True
            else:
                print(f"  ✗ API error creating relationship {from_key} → {to_key}: {e}")
                self.stats["failed_links"] += 1
                return False
        except Exception as e:
            print(f"  ✗ Unexpected error creating relationship {from_key} → {to_key}: {e}")
            self.stats["failed_links"] += 1
            return False

    def process_srs_requirement(self, srs_key: str, interface_keys: list[str]) -> None:
        """Process a single SRS requirement and its interface mappings."""
        print(f"\nProcessing SRS: {srs_key}")

        # Get SRS item ID
        srs_item_id = self.get_item_id(srs_key)
        if not srs_item_id:
            print(f"  ✗ SRS item not found: {srs_key}")
            self.stats["srs_not_found"] += 1
            return

        print(f"  Found SRS item ID: {srs_item_id}")

        # Process each interface
        for interface_id in interface_keys:
            # Convert interface ID to document key
            interface_doc_key = INTERFACE_ID_TO_DOCUMENT_KEY.get(interface_id)
            if not interface_doc_key:
                print(f"  ✗ Interface ID mapping not found: {interface_id}")
                self.stats["interface_not_found"] += 1
                continue

            # Get interface item ID using document key
            interface_item_id = self.get_item_id(interface_doc_key)
            if not interface_item_id:
                print(f"  ✗ Interface item not found: {interface_id} ({interface_doc_key})")
                self.stats["interface_not_found"] += 1
                continue

            # Create bidirectional relationship
            self.create_relationship(
                srs_item_id,
                interface_item_id,
                srs_key,
                f"{interface_id} ({interface_doc_key})",
            )

            # Add small delay to avoid rate limiting
            rate_limit(0.1)

    def run_auto_linking(self, dry_run: bool = False) -> None:
        """Run the automatic linking process."""
        print("=" * 80)
        print("JAMA AUTO LINKER - SRS to Interface Mapping")
        print("=" * 80)

        if dry_run:
            print("DRY RUN MODE - No actual relationships will be created")
            print("-" * 80)

        # Validate interface mappings
        print("Validating interface mappings...")
        missing_mappings = []
        for srs_key, interface_ids in SRS_TO_INTERFACE_MAPPING.items():
            for interface_id in interface_ids:
                if interface_id not in INTERFACE_ID_TO_DOCUMENT_KEY:
                    missing_mappings.append(interface_id)

        if missing_mappings:
            print(f"ERROR: Missing document key mappings for interfaces: {set(missing_mappings)}")
            sys.exit(1)
        else:
            print("✓ All interface mappings validated")

        # Calculate statistics
        self.stats["total_srs"] = len(SRS_TO_INTERFACE_MAPPING)
        self.stats["total_interfaces"] = len(INTERFACE_ID_TO_DOCUMENT_KEY)
        self.stats["total_mappings"] = sum(len(interfaces) for interfaces in SRS_TO_INTERFACE_MAPPING.values())

        print(f"Total SRS Requirements: {self.stats['total_srs']}")
        print(f"Total Unique Interfaces: {self.stats['total_interfaces']}")
        print(f"Total Mappings to Create: {self.stats['total_mappings']}")
        print("-" * 80)

        if dry_run:
            print("DRY RUN: Would process the following mappings:")
            for srs_key, interface_ids in SRS_TO_INTERFACE_MAPPING.items():
                print(f"  {srs_key} → {len(interface_ids)} interfaces:")
                for interface_id in interface_ids:
                    interface_doc_key = INTERFACE_ID_TO_DOCUMENT_KEY.get(interface_id, "NOT FOUND")
                    print(f"    - {interface_id} ({interface_doc_key})")
            return

        # Process each SRS requirement
        for srs_key, interface_keys in SRS_TO_INTERFACE_MAPPING.items():
            self.process_srs_requirement(srs_key, interface_keys)

            # Add delay between SRS requirements to be respectful to the API
            rate_limit(0.5)

        # Print final statistics
        self.print_final_stats()

    def print_final_stats(self) -> None:
        """Print final statistics."""
        print("\n" + "=" * 80)
        print("FINAL STATISTICS")
        print("=" * 80)
        print(f"Total SRS Requirements: {self.stats['total_srs']}")
        print(f"Total Unique Interfaces: {self.stats['total_interfaces']}")
        print(f"Total Mappings Expected: {self.stats['total_mappings']}")
        print(f"Successful Links Created: {self.stats['successful_links']}")
        print(f"Failed Links: {self.stats['failed_links']}")
        print(f"Skipped Links (already exist): {self.stats['skipped_links']}")
        print(f"SRS Items Not Found: {self.stats['srs_not_found']}")
        print(f"Interface Items Not Found: {self.stats['interface_not_found']}")
        print("-" * 80)

        success_rate = (
            (self.stats["successful_links"] + self.stats["skipped_links"]) / self.stats["total_mappings"] * 100
            if self.stats["total_mappings"] > 0
            else 0
        )
        print(f"Overall Success Rate: {success_rate:.1f}%")

        if self.stats["failed_links"] > 0 or self.stats["srs_not_found"] > 0 or self.stats["interface_not_found"] > 0:
            print("\nISSUES ENCOUNTERED:")
            if self.stats["srs_not_found"] > 0:
                print(f"  - {self.stats['srs_not_found']} SRS requirements not found in Jama")
            if self.stats["interface_not_found"] > 0:
                print(f"  - {self.stats['interface_not_found']} interface specifications not found in Jama")
            if self.stats["failed_links"] > 0:
                print(f"  - {self.stats['failed_links']} relationships failed to create")


def main():
    """Main function to run the auto linker."""
    import argparse

    parser = argparse.ArgumentParser(description="Automatically link SRS requirements to interface specifications in Jama")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true", default=True, help="Preview links (default)")
    grp.add_argument("--apply", action="store_true", help="Create relationships")
    parser.add_argument(
        "--specific-srs",
        type=str,
        help="Process only a specific SRS requirement (e.g., ABSD-DI3_IMP-207)",
    )

    args = parser.parse_args()

    try:
        linker = JamaAutoLinker()

        if args.specific_srs:
            # Process only a specific SRS requirement
            if args.specific_srs in SRS_TO_INTERFACE_MAPPING:
                interface_ids = SRS_TO_INTERFACE_MAPPING[args.specific_srs]
                print(f"Processing specific SRS: {args.specific_srs}")
                if args.apply:
                    linker.process_srs_requirement(args.specific_srs, interface_ids)
                else:
                    print(f"DRY RUN: Would link {args.specific_srs} to {len(interface_ids)} interfaces:")
                    for interface_id in interface_ids:
                        interface_doc_key = INTERFACE_ID_TO_DOCUMENT_KEY.get(interface_id, "NOT FOUND")
                        print(f"  - {interface_id} ({interface_doc_key})")
            else:
                print(f"Error: SRS requirement '{args.specific_srs}' not found in mapping")
                sys.exit(1)
        else:
            # Process all mappings
            linker.run_auto_linking(dry_run=not args.apply)

    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
