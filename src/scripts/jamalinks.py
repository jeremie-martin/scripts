#!/usr/bin/env python3
"""
jamalinks.py

Export Jama items with their upstream and downstream links to Excel.

Creates a matrix with columns:
  Upstream ID | Key | Name | Description | Downstream ID

One row per input item. Multiple upstream/downstream links are joined with
newlines within the same cell (natural sort order).

Supports filtering upstream and downstream links by key patterns.

Usage:
    jamalinks ABC-FLD-164 -o links.xlsx
    jamalinks ABC-REQ-1 ABC-REQ-2 --upstream SWVER- --downstream TEST-
    jamalinks keys.txt -u SWVER- -u FWVER- -d TEST-
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from py_jama_rest_client.client import APIException

from scripts.jama.common import (
    expand_keys,
    get_item_id,
    html_to_markdown,
    jama_url_for_item,
    load_jama,
    load_keys_from_file_or_args,
    rate_limit,
)


@dataclass(frozen=True)
class ItemRef:
    """Reference to a Jama item with its key metadata."""

    id: int
    key: str
    name: str
    description: str = ""
    project_id: int | None = None


# Styling constants
HEADER_FILL = PatternFill(start_color="E2E3E5", end_color="E2E3E5", fill_type="solid")
HEADER_FONT = Font(bold=True)
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
THIN_BORDER_SIDE = Side(border_style="thin", color="000000")
THIN_BORDER = Border(
    left=THIN_BORDER_SIDE,
    right=THIN_BORDER_SIDE,
    top=THIN_BORDER_SIDE,
    bottom=THIN_BORDER_SIDE,
)


def natural_key(text: str) -> tuple:
    """Natural sort key so ABC-2 sorts before ABC-19."""
    return tuple(int(t) if t.isdigit() else t.lower() for t in re.findall(r"\d+|\D+", text))


def matches_any_pattern(key: str, patterns: list[str]) -> bool:
    """Check if key contains any of the given patterns (case-insensitive).

    Patterns can be prefixes (e.g., "ABC-SWVER-") or partial matches (e.g., "SWVER-").
    """
    if not patterns:
        return True  # No filter means match all
    upper = key.upper()
    return any(p.upper() in upper for p in patterns)


def fetch_item_info(jama, item_id: int, *, include_description: bool = True) -> ItemRef | None:
    """Fetch item metadata from Jama by ID."""
    try:
        item = jama.get_item(item_id)
    except APIException:
        return None
    if not isinstance(item, dict):
        return None

    fields = item.get("fields") or {}
    key = item.get("documentKey") or fields.get("documentKey") or ""
    if not key:
        return None

    name = fields.get("name") or item.get("name") or ""
    name = str(name).strip()

    description = ""
    if include_description:
        # Try common description field names
        for desc_key in ("description", "description$171", "description$199"):
            if desc_key in fields and fields[desc_key]:
                description = str(fields[desc_key])
                break
        # Fallback: search for any field containing "description"
        if not description:
            for fkey, fval in fields.items():
                if "description" in fkey.lower() and isinstance(fval, str) and fval.strip():
                    description = fval
                    break

    # Extract project ID
    project = item.get("project")
    if isinstance(project, dict):
        project_id = project.get("id")
    elif isinstance(project, int):
        project_id = project
    else:
        project_id = None

    return ItemRef(id=item_id, key=key, name=name, description=description, project_id=project_id)


def get_related_ids(jama, item_id: int, direction: str) -> list[int]:
    """Get upstream or downstream related item IDs."""
    try:
        if direction == "upstream":
            rels = jama.get_items_upstream_relationships(item_id)
            return [r.get("fromItem") for r in rels if r.get("fromItem")]
        else:
            rels = jama.get_items_downstream_relationships(item_id)
            return [r.get("toItem") for r in rels if r.get("toItem")]
    except APIException:
        return []


def fetch_related_items(
    jama,
    item_id: int,
    direction: str,
    *,
    patterns: list[str] | None = None,
) -> list[ItemRef]:
    """Fetch related items, optionally filtering by key patterns."""
    related_ids = get_related_ids(jama, item_id, direction)
    items: list[ItemRef] = []

    for rel_id in related_ids:
        ref = fetch_item_info(jama, rel_id, include_description=False)
        if not ref:
            continue
        if patterns and not matches_any_pattern(ref.key, patterns):
            continue
        items.append(ref)

    # Natural sort by key
    items.sort(key=lambda r: natural_key(r.key))
    return items


def format_cell_value(items: list[ItemRef]) -> str:
    """Format a list of item refs as newline-separated keys for a cell."""
    if not items:
        return ""
    return "\n".join(item.key for item in items)


def build_rows(
    jama,
    doc_keys: list[str],
    *,
    upstream_filters: list[str],
    downstream_filters: list[str],
) -> list[dict]:
    """Build one row per input item with links joined by newlines in cells."""
    rows: list[dict] = []
    total = len(doc_keys)

    for idx, doc_key in enumerate(doc_keys, 1):
        print(f"[{idx}/{total}] Processing {doc_key}...", file=sys.stderr)

        item_id = get_item_id(jama, doc_key)
        if not item_id:
            print(f"  Warning: '{doc_key}' not found, skipping.", file=sys.stderr)
            continue

        item = fetch_item_info(jama, item_id, include_description=True)
        if not item:
            print(f"  Warning: Could not fetch details for '{doc_key}', skipping.", file=sys.stderr)
            continue

        # Process description - always strip HTML to plain text
        description = item.description
        if description:
            description = html_to_markdown(description, clean=True).strip()

        # Fetch related items with filters (already natural-sorted)
        upstreams = fetch_related_items(jama, item_id, "upstream", patterns=upstream_filters or None)
        downstreams = fetch_related_items(jama, item_id, "downstream", patterns=downstream_filters or None)

        # One row per item, with links joined by newlines in cells
        rows.append({
            "upstream_id": format_cell_value(upstreams),
            "key": item.key,
            "name": item.name,
            "description": description,
            "downstream_id": format_cell_value(downstreams),
            "item_id": item.id,
            "project_id": item.project_id,
        })

        rate_limit(0.05)

    return rows


def autosize_columns(ws) -> None:
    """Auto-size columns based on content."""
    for col_idx in range(1, ws.max_column + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx, values_only=True):
            for value in row:
                if value is None:
                    continue
                # For multiline cells, consider the longest line
                for line in str(value).split("\n"):
                    max_len = max(max_len, len(line))
        ws.column_dimensions[col_letter].width = min(max(12, max_len + 2), 80)


def write_xlsx(rows: list[dict], output_path: Path) -> None:
    """Write rows to an Excel file."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Links Matrix"

    # Header row
    headers = ["Upstream ID", "Key", "Name", "Description", "Downstream ID"]
    ws.append(headers)

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT
        cell.border = THIN_BORDER

    # Data rows
    for row_data in rows:
        r = ws.max_row + 1
        values = [
            row_data["upstream_id"],
            row_data["key"],
            row_data["name"],
            row_data["description"],
            row_data["downstream_id"],
        ]

        for col_idx, value in enumerate(values, 1):
            cell = ws.cell(row=r, column=col_idx, value=value)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = THIN_BORDER

            # Make the Key column a hyperlink
            if col_idx == 2 and row_data.get("item_id"):
                try:
                    url = jama_url_for_item(row_data["item_id"], row_data.get("project_id"))
                    cell.hyperlink = url
                    cell.style = "Hyperlink"
                except Exception:
                    pass  # Skip hyperlink if URL generation fails

    autosize_columns(ws)

    # Set minimum row height for data rows
    for row_dim in ws.row_dimensions.values():
        if row_dim.height is None:
            row_dim.height = 18

    wb.save(output_path)


def timestamped_path(base_path: Path) -> Path:
    """Add timestamp to filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base_path.with_name(f"{base_path.stem}_{timestamp}{base_path.suffix}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export Jama items with upstream/downstream links to Excel (one row per item).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  jamalinks ABC-FLD-164 -o links.xlsx
  jamalinks ABC-REQ-1 -u SWVER- -d TEST-
  jamalinks keys.txt --upstream SWVER- --upstream FWVER-
        """,
    )
    parser.add_argument(
        "keys",
        nargs="+",
        metavar="KEY_OR_FILE",
        help="Jama document keys, folder keys, or a text file with keys (one per line).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="jama_links.xlsx",
        help="Output Excel file path (default: jama_links.xlsx). Timestamp will be added.",
    )
    parser.add_argument(
        "-u",
        "--upstream",
        action="append",
        dest="upstream_filters",
        metavar="PREFIX",
        help="Filter upstream links by key prefix (can be repeated for multiple prefixes, OR logic).",
    )
    parser.add_argument(
        "-d",
        "--downstream",
        action="append",
        dest="downstream_filters",
        metavar="PREFIX",
        help="Filter downstream links by key prefix (can be repeated for multiple prefixes, OR logic).",
    )
    parser.add_argument(
        "--no-timestamp",
        action="store_true",
        help="Don't add timestamp to output filename.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Connect to Jama
    try:
        jama = load_jama()
    except Exception as e:
        print(f"Jama connection error: {e}", file=sys.stderr)
        return 2

    # Load and expand keys
    input_keys = load_keys_from_file_or_args(args.keys)

    def on_missing(key: str) -> None:
        print(f"Warning: '{key}' not found in Jama.", file=sys.stderr)

    def on_empty(key: str) -> None:
        print(f"Note: Container '{key}' has no items.", file=sys.stderr)

    doc_keys = expand_keys(jama, input_keys, on_missing=on_missing, on_empty_container=on_empty)

    if not doc_keys:
        print("No valid document keys to process.", file=sys.stderr)
        return 1

    print(f"Processing {len(doc_keys)} item(s)...", file=sys.stderr)

    # Show active filters
    if args.upstream_filters:
        print(f"Upstream filter(s): {', '.join(args.upstream_filters)}", file=sys.stderr)
    if args.downstream_filters:
        print(f"Downstream filter(s): {', '.join(args.downstream_filters)}", file=sys.stderr)

    # Build rows
    rows = build_rows(
        jama,
        doc_keys,
        upstream_filters=args.upstream_filters or [],
        downstream_filters=args.downstream_filters or [],
    )

    if not rows:
        print("No data to export.", file=sys.stderr)
        return 1

    # Write output
    output_path = Path(args.output)
    if output_path.suffix.lower() != ".xlsx":
        output_path = output_path.with_suffix(".xlsx")

    if not args.no_timestamp:
        output_path = timestamped_path(output_path)

    write_xlsx(rows, output_path)
    print(f"Wrote {len(rows)} row(s) to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
