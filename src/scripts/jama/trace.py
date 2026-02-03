#!/usr/bin/env python3
"""
Core trace matrix logic for Jama items.

Builds trace matrix data for items with their upstream/downstream relationships.
Reuses infrastructure from jama/links.py and jama/fields.py.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from scripts.jama.common import (
    expand_keys,
    get_item_id,
    html_to_markdown,
    load_keys_from_file_or_args,
    rate_limit,
)
from scripts.jama.database import get_item_type_fields, load_database
from scripts.jama.fields import resolve_field_name, resolve_field_value
from scripts.jama.links import (
    LinkedItem,
    fetch_item_metadata,
    get_downstream_ids,
    get_upstream_ids,
)

if TYPE_CHECKING:
    from py_jama_rest_client.client import JamaClient

__all__ = [
    "TraceRow",
    "build_trace_rows",
    "load_trace_keys",
    "matches_any_pattern",
    "natural_sort_key",
]


@dataclass
class TraceRow:
    """A row in the trace matrix."""

    item_id: int
    key: str
    project_id: int | None
    fields: dict[str, str] = field(default_factory=dict)
    upstream: list[LinkedItem] = field(default_factory=list)
    downstream: list[LinkedItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "item_id": self.item_id,
            "key": self.key,
            "project_id": self.project_id,
            "fields": self.fields,
            "upstream": [{"key": u.key, "name": u.name} for u in self.upstream],
            "downstream": [{"key": d.key, "name": d.name} for d in self.downstream],
        }


def natural_sort_key(text: str) -> tuple:
    """Natural sort key so ABC-2 sorts before ABC-19."""
    return tuple(int(t) if t.isdigit() else t.lower() for t in re.findall(r"\d+|\D+", text))


def matches_any_pattern(key: str, patterns: list[str]) -> bool:
    """Check if key contains any of the given patterns (case-insensitive).

    Patterns can be prefixes (e.g., "ABC-SWVER-") or partial matches (e.g., "SWVER-").
    Multiple patterns use OR logic.
    """
    if not patterns:
        return True  # No filter means match all
    upper = key.upper()
    return any(p.upper() in upper for p in patterns)


def load_trace_keys(args: list[str]) -> list[str]:
    """Load keys from command line args or file."""
    return load_keys_from_file_or_args(args)


def _fetch_item_fields(
    jama: JamaClient,
    item_id: int,
    field_names: list[str],
    database: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Fetch specific field values for an item."""
    try:
        item = jama.get_item(item_id)
    except Exception:
        return {}

    if not isinstance(item, dict):
        return {}

    fields = item.get("fields") or {}
    item_type_id = item.get("itemType")

    # Get field info for this item type
    if item_type_id:
        item_fields = get_item_type_fields(jama, item_type_id, database)
    else:
        item_fields = {}

    result: dict[str, str] = {}
    for field_input in field_names:
        # Special handling for 'name' - it's always available
        if field_input.lower() == "name":
            name_val = fields.get("name") or item.get("name") or ""
            result["name"] = str(name_val).strip()
            continue

        # Resolve field name through aliases
        actual_field = resolve_field_name(field_input, item_fields)
        if actual_field and actual_field in fields:
            raw_value = fields[actual_field]
            field_info = item_fields.get(actual_field, {})
            resolved = resolve_field_value(raw_value, field_info)

            # Strip HTML from rich text fields
            if isinstance(raw_value, str) and ("<" in raw_value or "&" in raw_value):
                resolved = html_to_markdown(resolved, clean=True).strip()

            result[field_input] = resolved
        else:
            # Try direct field access as fallback
            for fkey in fields:
                if fkey.lower() == field_input.lower() or fkey.lower().startswith(field_input.lower()):
                    raw_value = fields[fkey]
                    if isinstance(raw_value, str) and ("<" in raw_value or "&" in raw_value):
                        raw_value = html_to_markdown(raw_value, clean=True).strip()
                    result[field_input] = str(raw_value)
                    break
            else:
                result[field_input] = ""

    return result


def _fetch_related_items(
    jama: JamaClient,
    item_id: int,
    direction: str,
    patterns: list[str] | None = None,
) -> list[LinkedItem]:
    """Fetch related items, optionally filtering by key patterns."""
    if direction == "upstream":
        related_ids = get_upstream_ids(jama, item_id)
    else:
        related_ids = get_downstream_ids(jama, item_id)

    items: list[LinkedItem] = []
    for rel_id in related_ids:
        linked = fetch_item_metadata(jama, rel_id)
        if not linked:
            continue
        if patterns and not matches_any_pattern(linked.key, patterns):
            continue
        items.append(linked)
        rate_limit(0.02)

    # Natural sort by key
    items.sort(key=lambda r: natural_sort_key(r.key))
    return items


def build_trace_rows(
    jama: JamaClient,
    doc_keys: list[str],
    *,
    field_names: list[str] | None = None,
    upstream_patterns: list[str] | None = None,
    downstream_patterns: list[str] | None = None,
    verbose: bool = True,
) -> list[TraceRow]:
    """
    Build trace matrix rows for the given document keys.

    Args:
        jama: Jama client
        doc_keys: List of document keys to process
        field_names: List of field names to include (default: name, description)
        upstream_patterns: Patterns to filter upstream links (OR logic)
        downstream_patterns: Patterns to filter downstream links (OR logic)
        verbose: Print progress messages

    Returns:
        List of TraceRow objects
    """
    if field_names is None:
        field_names = ["name", "description"]

    database = load_database()
    rows: list[TraceRow] = []
    total = len(doc_keys)

    for idx, doc_key in enumerate(doc_keys, 1):
        if verbose:
            print(f"[{idx}/{total}] Processing {doc_key}...", file=sys.stderr)

        item_id = get_item_id(jama, doc_key)
        if not item_id:
            if verbose:
                print(f"  Warning: '{doc_key}' not found, skipping.", file=sys.stderr)
            continue

        # Fetch item metadata
        item = fetch_item_metadata(jama, item_id)
        if not item:
            if verbose:
                print(f"  Warning: Could not fetch details for '{doc_key}', skipping.", file=sys.stderr)
            continue

        # Fetch requested fields
        fields = _fetch_item_fields(jama, item_id, field_names, database)

        # Fetch related items with filters
        upstream = _fetch_related_items(jama, item_id, "upstream", upstream_patterns)
        downstream = _fetch_related_items(jama, item_id, "downstream", downstream_patterns)

        rows.append(
            TraceRow(
                item_id=item.id,
                key=item.key,
                project_id=item.project_id,
                fields=fields,
                upstream=upstream,
                downstream=downstream,
            )
        )

        rate_limit(0.05)

    return rows


def expand_trace_keys(
    jama: JamaClient,
    input_keys: list[str],
    *,
    verbose: bool = True,
) -> list[str]:
    """
    Expand input keys (which may include containers) to document keys.

    Args:
        jama: Jama client
        input_keys: List of keys (may include folder/container keys)
        verbose: Print warnings for missing or empty containers

    Returns:
        List of expanded document keys
    """

    def on_missing(key: str) -> None:
        if verbose:
            print(f"Warning: '{key}' not found in Jama.", file=sys.stderr)

    def on_empty(key: str) -> None:
        if verbose:
            print(f"Note: Container '{key}' has no items.", file=sys.stderr)

    return expand_keys(jama, input_keys, on_missing=on_missing, on_empty_container=on_empty)
