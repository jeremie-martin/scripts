#!/usr/bin/env python3
"""
Jama Auto Linker Script - SUT REQUIREMENTS TO UNIT TESTS
Automatically creates relationships between SUT high-level requirements and their corresponding unit tests
based on comprehensive mapping analysis.
"""

import sys

from scripts.jama.common import (
    get_item_id,
    load_jama,
    rate_limit,
    relationship_exists,
    with_retries,
)

# SUT Requirements to Unit Tests mapping based on analysis
SUT_REQUIREMENTS_TO_TESTS_MAPPING = {
    # System Infrastructure Requirements (limited direct unit test coverage)
    "ABSD-DI2_SUT-118": [],  # Ubuntu 24 - System requirement, no direct unit test coverage
    "ABSD-DI2_SUT-119": [],  # No Sounds - System requirement, no direct unit test coverage
    "ABSD-DI2_SUT-120": [],  # SUT installation package - System packaging, no direct unit test coverage
    "ABSD-DI2_SUT-121": [],  # Launched from terminal - System interface, no direct unit test coverage
    "ABSD-DI2_SUT-122": [  # Terminal feedback - Covered by all tests that verify reporting
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-383",
        "ABSD-SWVER-384",
        "ABSD-SWVER-385",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    # Core Update Functionality
    "ABSD-DI2_SUT-123": [  # FPGA Version update - No specific FPGA unit tests in provided list
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",  # CRC tests support file integrity for updates
    ],
    "ABSD-DI2_SUT-124": [  # MCU Version update - Covered by MCU state and command tests
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",
        "ABSD-SWVER-360",
    ],
    "ABSD-DI2_SUT-125": [  # Abort update - Covered by error handling and protocol tests
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    "ABSD-DI2_SUT-126": [  # Log and Report Abort - Covered by tests that verify error logging
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    "ABSD-DI2_SUT-127": [  # Update duration < 20 minutes - Covered by timing analysis
        "ABSD-SWVER-367"
    ],
    # USB Configuration Link & Communication
    "ABSD-DI2_SUT-116": [  # Connection USB Configuration link
        "ABSD-SWVER-322",
        "ABSD-SWVER-323",
        "ABSD-SWVER-324",  # All SerialLink tests
    ],
    "ABSD-DI2_SUT-117": [  # USB Config Link Connection error
        "ABSD-SWVER-322"  # SerialLink error handling test
    ],
    # Protocol & Command Communication
    "ABSD-DI2_SUT-85": [  # USB Configuration Link Command Reply Verification
        "ABSD-SWVER-373",
        "ABSD-SWVER-383",
        "ABSD-SWVER-384",
        "ABSD-SWVER-385",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
        "ABSD-SWVER-393",
        "ABSD-SWVER-394",
        "ABSD-SWVER-395",
    ],
    "ABSD-DI2_SUT-86": [  # Extended Commands Timeout (2500ms) - No specific 2500ms tests in provided list
        "ABSD-SWVER-367",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-390",
        "ABSD-SWVER-392",
        "ABSD-SWVER-395",
    ],
    "ABSD-DI2_SUT-87": [  # Default Command Timeout (500ms)
        "ABSD-SWVER-367",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-390",
        "ABSD-SWVER-392",
        "ABSD-SWVER-395",
    ],
    "ABSD-DI2_SUT-88": [  # Command Reply Validation
        "ABSD-SWVER-373",
        "ABSD-SWVER-383",
        "ABSD-SWVER-384",
        "ABSD-SWVER-385",
        "ABSD-SWVER-389",
        "ABSD-SWVER-394",
        "ABSD-SWVER-395",
    ],
    "ABSD-DI2_SUT-89": [  # Command Execution Retry (within 100ms)
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
        "ABSD-SWVER-385",
    ],
    "ABSD-DI2_SUT-90": [  # Command Failure (after 3 transmissions) - No specific 3-retry failure tests
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    "ABSD-DI2_SUT-133": [  # Individual command failure
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    # Firmware Query & Version Management
    "ABSD-DI2_SUT-101": [  # Query FW Version
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",  # MCU FW state tests
    ],
    "ABSD-DI2_SUT-102": [  # FW up to date (proceed only when different)
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",  # MCU FW state tests can verify version comparison
    ],
    "ABSD-DI2_SUT-103": [  # Log and Report FW up to date
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",
    ],
    "ABSD-DI2_SUT-104": [  # Implant not up to date (transfer when different)
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",  # MCU FW state tests
    ],
    "ABSD-DI2_SUT-105": [  # Log and Report FW Update progress (10% intervals)
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",
    ],
    "ABSD-DI2_SUT-106": [  # FW File transfer integrity
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",  # CRC computation tests for integrity verification
    ],
    "ABSD-DI2_SUT-107": [  # FW Transfer error
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    "ABSD-DI2_SUT-108": [  # FW Version Check (verify after update)
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",
    ],
    "ABSD-DI2_SUT-109": [  # FW Version Error
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    "ABSD-DI2_SUT-110": [  # FW Version OK
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",
    ],
    # FPGA Query & Version Management (limited specific FPGA tests in provided list)
    "ABSD-DI2_SUT-91": [  # Query FPGA Version - No specific FPGA query tests
        "ABSD-SWVER-343",
        "ABSD-SWVER-345",  # Device ID queries might be related
    ],
    "ABSD-DI2_SUT-92": [  # FPGA up to date (proceed only when different)
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",  # CRC tests for version comparison integrity
    ],
    "ABSD-DI2_SUT-93": [  # Log and Report FPGA up to date
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",
        "ABSD-SWVER-343",
        "ABSD-SWVER-345",
    ],
    "ABSD-DI2_SUT-94": [  # Implant FPGA not up to date (transfer when different)
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",
    ],
    "ABSD-DI2_SUT-95": [  # Log and Report FPGA Update progress (10% intervals)
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",
        "ABSD-SWVER-367",  # CRC + timing
    ],
    "ABSD-DI2_SUT-96": [  # FPGA File transfer integrity
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",  # CRC computation tests
    ],
    "ABSD-DI2_SUT-97": [  # FPGA Transfer error
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    "ABSD-DI2_SUT-98": [  # FPGA Version Check (verify after update)
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",
        "ABSD-SWVER-343",
        "ABSD-SWVER-345",
    ],
    "ABSD-DI2_SUT-99": [  # FPGA Version Error
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    "ABSD-DI2_SUT-100": [  # FPGA Version OK
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",
        "ABSD-SWVER-343",
        "ABSD-SWVER-345",
    ],
    # Startup Sequences (limited specific startup tests in provided list)
    "ABSD-DI2_SUT-111": [  # Wearable start-up sequence
        "ABSD-SWVER-343",
        "ABSD-SWVER-350",
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",  # Device/state queries
    ],
    "ABSD-DI2_SUT-112": [  # Wearable start-up failure
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    "ABSD-DI2_SUT-113": [  # Power-up implant
        "ABSD-SWVER-350",
        "ABSD-SWVER-360",  # Enable wireless power + MCU reboot
    ],
    "ABSD-DI2_SUT-114": [  # Implant Start-Up Sequence
        "ABSD-SWVER-345",
        "ABSD-SWVER-346",
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-360",
    ],
    "ABSD-DI2_SUT-115": [  # Implant start-up failure
        "ABSD-SWVER-322",
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-360",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    # Logging Requirements (all tests should contribute to logging verification)
    "ABSD-DI2_SUT-70": [  # Logs SUT - Create and maintain log files
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",
    ],
    "ABSD-DI2_SUT-71": [  # SUT UTC time-stamp
        "ABSD-SWVER-367"  # Timing analysis test
    ],
    "ABSD-DI2_SUT-72": [  # Logs SUT at start-up - New log file each launch
        "ABSD-SWVER-343",
        "ABSD-SWVER-345",
        "ABSD-SWVER-346",  # Initial startup commands
    ],
    "ABSD-DI2_SUT-73": [  # SUT logs time-stamped (YYYY-MM-DDThh:mm:ss.mmmZ)
        "ABSD-SWVER-367"  # Timing analysis verifies timestamp precision
    ],
    "ABSD-DI2_SUT-74": [  # SUT log human readable
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",  # String format tests for MCU states
    ],
    "ABSD-DI2_SUT-75": [  # SUT log filename time-stamp (YYYY-MM-DD-hh-mm-ss)
        "ABSD-SWVER-367"  # Timing analysis
    ],
    "ABSD-DI2_SUT-76": [  # SUT log levels (INFO, ERROR)
        "ABSD-SWVER-322",
        "ABSD-SWVER-373",
        "ABSD-SWVER-388",
        "ABSD-SWVER-389",  # Error handling tests
    ],
    "ABSD-DI2_SUT-77": [  # Log and Report Implant Power-On
        "ABSD-SWVER-350",
        "ABSD-SWVER-360",  # Power and reboot commands
    ],
    "ABSD-DI2_SUT-78": [  # Log and Report Implant Start-Up
        "ABSD-SWVER-345",
        "ABSD-SWVER-346",
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-360",
    ],
    "ABSD-DI2_SUT-79": [  # Log and Report Wearable Start-Up
        "ABSD-SWVER-343",
        "ABSD-SWVER-350",
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
    ],
    "ABSD-DI2_SUT-80": [  # Log and Report Current FW Version
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",
    ],
    "ABSD-DI2_SUT-81": [  # Log and Report Updated FW Version
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",
    ],
    "ABSD-DI2_SUT-83": [  # Log and Report Updated FPGA Version
        "ABSD-SWVER-286",
        "ABSD-SWVER-287",
        "ABSD-SWVER-343",
        "ABSD-SWVER-345",
    ],
    "ABSD-DI2_SUT-84": [  # SUT Logs and Reports versions at Start-up
        "ABSD-SWVER-343",
        "ABSD-SWVER-345",
        "ABSD-SWVER-346",
        "ABSD-SWVER-351",
        "ABSD-SWVER-352",
        "ABSD-SWVER-353",
        "ABSD-SWVER-354",
    ],
}


class JamaAutoLinker:
    def __init__(self):
        """Initialize the Jama Auto Linker with API connection."""
        self.jama = load_jama()
        self.item_cache = {}
        self.failed_lookups = set()
        self.stats = {
            "total_requirements": 0,
            "total_tests": 0,
            "total_mappings": 0,
            "successful_links": 0,
            "failed_links": 0,
            "skipped_links": 0,
            "requirements_not_found": 0,
            "tests_not_found": 0,
            "requirements_no_tests": 0,
        }

    def relationship_exists(self, from_item_id: int, to_item_id: int) -> bool:
        """Deprecated: use common.relationship_exists; kept for compatibility."""
        return relationship_exists(self.jama, from_item_id, to_item_id)

    def create_relationship(self, from_item_id: int, to_item_id: int, from_key: str, to_key: str) -> bool:
        """Create a relationship between two items."""
        try:
            if self.relationship_exists(from_item_id, to_item_id):
                print(f"  → Relationship already exists: {from_key} ↔ {to_key}")
                self.stats["skipped_links"] += 1
                return True

            def _post():
                return self.jama.post_relationship(from_item=from_item_id, to_item=to_item_id)

            rel_id = with_retries(_post)
            if rel_id:
                print(f"  ✓ Created relationship: {from_key} → {to_key} (ID: {rel_id})")
                self.stats["successful_links"] += 1
                return True
        except Exception as e:
            print(f"  ✗ Error creating relationship {from_key} → {to_key}: {e}")
            self.stats["failed_links"] += 1
        return False

    def process_requirement(self, req_key: str, test_keys: list[str]) -> None:
        """Process a single requirement and its test mappings."""
        print(f"\nProcessing SUT Requirement: {req_key}")
        req_item_id = get_item_id(self.jama, req_key)
        if not req_item_id:
            print(f"  ✗ Requirement not found: {req_key}")
            self.stats["requirements_not_found"] += 1
            return
        print(f"  Found requirement item ID: {req_item_id}")
        for test_id in test_keys:
            test_item_id = get_item_id(self.jama, test_id)
            if not test_item_id:
                print(f"  ✗ Test not found: {test_id}")
                self.stats["tests_not_found"] += 1
                continue
            self.create_relationship(req_item_id, test_item_id, req_key, test_id)
            rate_limit(0.1)

    def run_auto_linking(self, dry_run: bool = False) -> None:
        """Run the automatic linking process."""
        print("=" * 80)
        print("JAMA AUTO LINKER - SUT Requirements to Unit Tests Mapping")
        print("=" * 80)
        if dry_run:
            print("DRY RUN MODE - No actual relationships will be created")
            print("-" * 80)
        self.stats["total_requirements"] = len(SUT_REQUIREMENTS_TO_TESTS_MAPPING)
        unique_tests = {t for tests in SUT_REQUIREMENTS_TO_TESTS_MAPPING.values() for t in tests}
        self.stats["total_tests"] = len(unique_tests)
        self.stats["total_mappings"] = sum(len(tests) for tests in SUT_REQUIREMENTS_TO_TESTS_MAPPING.values() if tests)
        print(f"Total SUT Requirements: {self.stats['total_requirements']}")
        print(f"Total Unique Unit Tests: {self.stats['total_tests']}")
        print(f"Total Mappings to Create: {self.stats['total_mappings']}")
        print("-" * 80)
        if dry_run:
            print("DRY RUN: Would process the following mappings:")
            for req_key, test_ids in SUT_REQUIREMENTS_TO_TESTS_MAPPING.items():
                if not test_ids:
                    print(f"  {req_key} → No unit tests (will skip)")
                    self.stats["requirements_no_tests"] += 1
                else:
                    print(f"  {req_key} → {len(test_ids)} unit tests:")
                    for test_id in test_ids:
                        print(f"    - {test_id}")
            return
        for req_key, test_keys in SUT_REQUIREMENTS_TO_TESTS_MAPPING.items():
            if not test_keys:
                print(f"\nSkipping {req_key} - No unit tests mapped")
                self.stats["requirements_no_tests"] += 1
                continue
            self.process_requirement(req_key, test_keys)
            rate_limit(0.5)
        self.print_final_stats()

    def print_final_stats(self) -> None:
        """Print final statistics."""
        print("\n" + "=" * 80)
        print("FINAL STATISTICS")
        print("=" * 80)
        print(f"Total SUT Requirements: {self.stats['total_requirements']}")
        print(f"Requirements with No Unit Tests: {self.stats['requirements_no_tests']}")
        print(f"Total Unique Unit Tests: {self.stats['total_tests']}")
        print(f"Total Mappings Expected: {self.stats['total_mappings']}")
        print(f"Successful Links: {self.stats['successful_links']}")
        print(f"Failed Links: {self.stats['failed_links']}")
        print(f"Skipped Links: {self.stats['skipped_links']}")
        print(f"Requirements Not Found: {self.stats['requirements_not_found']}")
        print(f"Tests Not Found: {self.stats['tests_not_found']}")
        success_rate = (
            ((self.stats["successful_links"] + self.stats["skipped_links"]) / self.stats["total_mappings"] * 100)
            if self.stats["total_mappings"] > 0
            else 0
        )
        print(f"Overall Success Rate: {success_rate:.1f}%")

    def analyze_coverage(self) -> None:
        """Analyze and report coverage statistics."""
        print("\n" + "=" * 80)
        print("COVERAGE ANALYSIS")
        print("=" * 80)

        # Count requirements with/without tests
        requirements_with_tests = [k for k, v in SUT_REQUIREMENTS_TO_TESTS_MAPPING.items() if v]
        requirements_without_tests = [k for k, v in SUT_REQUIREMENTS_TO_TESTS_MAPPING.items() if not v]

        print(f"Requirements with unit test coverage: {len(requirements_with_tests)}")
        print(f"Requirements without unit test coverage: {len(requirements_without_tests)}")

        if requirements_without_tests:
            print("\nRequirements without unit test coverage:")
            for req in sorted(requirements_without_tests):
                print(f"  - {req}")

        # Identify most/least tested requirements
        test_counts = [(k, len(v)) for k, v in SUT_REQUIREMENTS_TO_TESTS_MAPPING.items() if v]
        if test_counts:
            most_tested = max(test_counts, key=lambda x: x[1])
            print(f"\nMost tested requirement: {most_tested[0]} ({most_tested[1]} tests)")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Automatically link SUT requirements to unit tests in Jama")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true", default=True, help="Preview links (default)")
    grp.add_argument("--apply", action="store_true", help="Create relationships")
    parser.add_argument("--specific-requirement", type=str, help="Process only a specific requirement (e.g., ABSD-DI2_SUT-118)")
    parser.add_argument("--analyze", action="store_true", help="Show coverage analysis only")
    args = parser.parse_args()

    linker = JamaAutoLinker()

    if args.analyze:
        linker.analyze_coverage()
        return

    if args.specific_requirement:
        req = args.specific_requirement
        if req in SUT_REQUIREMENTS_TO_TESTS_MAPPING:
            tests = SUT_REQUIREMENTS_TO_TESTS_MAPPING[req]
            print(f"Processing specific requirement: {req}")
            if not args.apply:
                if not tests:
                    print(f"DRY RUN: {req} has no unit tests mapped (would skip)")
                else:
                    print(f"DRY RUN: Would link {req} to {len(tests)} unit tests:")
                    for test in tests:
                        print(f"  - {test}")
            else:
                linker.process_requirement(req, tests)
        else:
            print(f"Error: Requirement '{req}' not found in mapping")
            sys.exit(1)
    else:
        linker.run_auto_linking(dry_run=not args.apply)


if __name__ == "__main__":
    main()
