#!/usr/bin/env python3
"""
Output formatters for trace matrix data.

Provides table, JSON, and Excel formatters for TraceRow data.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from scripts.jama.common import jama_url_for_item
from scripts.jama.trace import TraceRow, natural_sort_key

if TYPE_CHECKING:
    pass

__all__ = [
    "TraceExcelFormatter",
    "TraceJsonFormatter",
    "TraceTableFormatter",
    "timestamped_path",
]

# Excel styling constants
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


def timestamped_path(base_path: Path) -> Path:
    """Add timestamp to filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return base_path.with_name(f"{base_path.stem}_{timestamp}{base_path.suffix}")


class TraceTableFormatter:
    """Format trace rows as terminal-friendly text table."""

    def format(self, rows: list[TraceRow], field_names: list[str]) -> str:
        """Format trace rows as a text table."""
        if not rows:
            return "No data."

        lines: list[str] = []

        for row in rows:
            # Header line with key
            lines.append(f"=== {row.key} ===")

            # Fields
            for field_name in field_names:
                value = row.fields.get(field_name, "")
                # Truncate long values for terminal display
                if len(value) > 200:
                    value = value[:200] + "..."
                lines.append(f"  {field_name}: {value}")

            # Upstream
            lines.append(f"  Upstream ({len(row.upstream)}):")
            if row.upstream:
                for item in row.upstream:
                    lines.append(f"    {item.key}: {item.name}")
            else:
                lines.append("    (none)")

            # Downstream
            lines.append(f"  Downstream ({len(row.downstream)}):")
            if row.downstream:
                for item in row.downstream:
                    lines.append(f"    {item.key}: {item.name}")
            else:
                lines.append("    (none)")

            lines.append("")

        return "\n".join(lines)


class TraceJsonFormatter:
    """Format trace rows as JSON."""

    def format(self, rows: list[TraceRow], field_names: list[str]) -> str:
        """Format trace rows as JSON."""
        data = [row.to_dict() for row in rows]
        if len(data) == 1:
            return json.dumps(data[0], indent=2)
        return json.dumps(data, indent=2)


class TraceExcelFormatter:
    """Format trace rows as Excel workbook."""

    def format(self, rows: list[TraceRow], field_names: list[str], output_path: Path) -> None:
        """Write trace rows to an Excel file."""
        wb = Workbook()
        ws = wb.active
        ws.title = "Trace Matrix"

        # Build header row: Upstream | Key | [fields...] | Downstream
        headers = ["Upstream"] + ["Key"] + [self._format_header(f) for f in field_names] + ["Downstream"]
        ws.append(headers)

        # Style header row
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGNMENT
            cell.border = THIN_BORDER

        # Data rows
        for row_data in rows:
            r = ws.max_row + 1

            # Build upstream cell (newline-separated keys)
            upstream_text = "\n".join(
                item.key for item in sorted(row_data.upstream, key=lambda x: natural_sort_key(x.key))
            )

            # Build downstream cell (newline-separated keys)
            downstream_text = "\n".join(
                item.key for item in sorted(row_data.downstream, key=lambda x: natural_sort_key(x.key))
            )

            # Collect field values
            field_values = [row_data.fields.get(f, "") for f in field_names]

            # Build row values
            values = [upstream_text, row_data.key] + field_values + [downstream_text]

            for col_idx, value in enumerate(values, 1):
                cell = ws.cell(row=r, column=col_idx, value=value)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                cell.border = THIN_BORDER

                # Make the Key column (col 2) a hyperlink
                if col_idx == 2 and row_data.item_id:
                    try:
                        url = jama_url_for_item(row_data.item_id, row_data.project_id)
                        cell.hyperlink = url
                        cell.style = "Hyperlink"
                    except Exception:
                        pass  # Skip hyperlink if URL generation fails

        self._autosize_columns(ws)

        # Set minimum row height for data rows
        for row_dim in ws.row_dimensions.values():
            if row_dim.height is None:
                row_dim.height = 18

        wb.save(output_path)

    def _format_header(self, field_name: str) -> str:
        """Format a field name as a header title."""
        # Convert snake_case to Title Case
        return field_name.replace("_", " ").title()

    def _autosize_columns(self, ws) -> None:
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
