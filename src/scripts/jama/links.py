#!/usr/bin/env python3
"""
Link management for Jama items.

Provides functions to query and create upstream/downstream relationships.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Any

from py_jama_rest_client.client import APIException, JamaClient

from scripts.jama.common import (
    get_item_id,
    jama_url_for_item,
    rate_limit,
    relationship_exists,
)


@dataclass
class LinkedItem:
    """Represents a linked item with its metadata."""

    id: int
    key: str
    name: str
    project_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ItemLinks:
    """Links for a single item."""

    id: int
    key: str
    name: str
    project_id: int | None
    upstream: list[LinkedItem]
    downstream: list[LinkedItem]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "project_id": self.project_id,
            "upstream": [u.to_dict() for u in self.upstream],
            "downstream": [d.to_dict() for d in self.downstream],
        }


def fetch_item_metadata(jama: JamaClient, item_id: int) -> LinkedItem | None:
    """Fetch basic item metadata by ID."""
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

    # Extract project ID
    project = item.get("project")
    if isinstance(project, dict):
        project_id = project.get("id")
    elif isinstance(project, int):
        project_id = project
    else:
        project_id = None

    return LinkedItem(id=item_id, key=key, name=name, project_id=project_id)


def get_upstream_ids(jama: JamaClient, item_id: int) -> list[int]:
    """Get upstream related item IDs (items that this item links TO)."""
    try:
        rels = jama.get_items_upstream_relationships(item_id)
        return [r.get("fromItem") for r in rels if r.get("fromItem")]
    except APIException:
        return []


def get_downstream_ids(jama: JamaClient, item_id: int) -> list[int]:
    """Get downstream related item IDs (items that link TO this item)."""
    try:
        rels = jama.get_items_downstream_relationships(item_id)
        return [r.get("toItem") for r in rels if r.get("toItem")]
    except APIException:
        return []


def get_item_links(
    jama: JamaClient,
    doc_key: str,
    *,
    include_upstream: bool = True,
    include_downstream: bool = True,
) -> ItemLinks | None:
    """
    Get all links for an item.

    Args:
        jama: Jama client
        doc_key: Document key (e.g., "ABC-DI2-123")
        include_upstream: Include upstream links
        include_downstream: Include downstream links

    Returns:
        ItemLinks object or None if item not found
    """
    item_id = get_item_id(jama, doc_key)
    if not item_id:
        return None

    item = fetch_item_metadata(jama, item_id)
    if not item:
        return None

    upstream: list[LinkedItem] = []
    downstream: list[LinkedItem] = []

    if include_upstream:
        for up_id in get_upstream_ids(jama, item_id):
            linked = fetch_item_metadata(jama, up_id)
            if linked:
                upstream.append(linked)
            rate_limit(0.02)

    if include_downstream:
        for down_id in get_downstream_ids(jama, item_id):
            linked = fetch_item_metadata(jama, down_id)
            if linked:
                downstream.append(linked)
            rate_limit(0.02)

    # Sort by key for consistent output
    upstream.sort(key=lambda x: x.key)
    downstream.sort(key=lambda x: x.key)

    return ItemLinks(
        id=item.id,
        key=item.key,
        name=item.name,
        project_id=item.project_id,
        upstream=upstream,
        downstream=downstream,
    )


def create_link(
    jama: JamaClient,
    source_key: str,
    target_key: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Create an upstream link from source to target.

    This creates a relationship where target becomes upstream of source.
    In Jama terms: post_relationship(from_item=target, to_item=source)

    Args:
        jama: Jama client
        source_key: Source document key (the item you're linking FROM)
        target_key: Target document key (the item you're linking TO - becomes upstream)
        dry_run: If True, don't actually create the link

    Returns:
        Dict with status: "created", "exists", "skipped", or "error"
    """
    result = {
        "source": source_key,
        "target": target_key,
        "status": "error",
        "message": "",
    }

    # Resolve IDs
    source_id = get_item_id(jama, source_key)
    if not source_id:
        result["message"] = f"Source item '{source_key}' not found"
        return result

    target_id = get_item_id(jama, target_key)
    if not target_id:
        result["message"] = f"Target item '{target_key}' not found"
        return result

    # Check if relationship already exists
    if relationship_exists(jama, target_id, source_id):
        result["status"] = "exists"
        result["message"] = "Relationship already exists"
        return result

    if dry_run:
        result["status"] = "skipped"
        result["message"] = "Would create link (dry run)"
        return result

    # Create the relationship
    # In Jama: from_item is upstream of to_item
    # So we want target to be upstream of source
    try:
        rel_id = jama.post_relationship(from_item=target_id, to_item=source_id)
        result["status"] = "created"
        result["message"] = f"Created relationship (id={rel_id})"
        result["relationship_id"] = rel_id
    except APIException as e:
        result["message"] = f"API error: {e}"

    return result


def create_links(
    jama: JamaClient,
    source_key: str,
    target_keys: list[str],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Create upstream links from source to multiple targets.

    Args:
        jama: Jama client
        source_key: Source document key
        target_keys: List of target document keys
        dry_run: If True, don't actually create links

    Returns:
        List of result dicts for each target
    """
    results = []
    for target_key in target_keys:
        result = create_link(jama, source_key, target_key, dry_run=dry_run)
        results.append(result)
        if result["status"] == "created":
            rate_limit(0.1)  # Rate limit successful creations
    return results


def format_links_table(links: ItemLinks, *, show_upstream: bool = True, show_downstream: bool = True) -> str:
    """Format links as a readable table."""
    lines = []
    lines.append(f"{links.key}: {links.name}")
    lines.append("")

    if show_upstream:
        lines.append(f"  Upstream ({len(links.upstream)}):")
        if links.upstream:
            for item in links.upstream:
                lines.append(f"    {item.key}: {item.name}")
        else:
            lines.append("    (none)")
        lines.append("")

    if show_downstream:
        lines.append(f"  Downstream ({len(links.downstream)}):")
        if links.downstream:
            for item in links.downstream:
                lines.append(f"    {item.key}: {item.name}")
        else:
            lines.append("    (none)")

    return "\n".join(lines)


def format_links_json(links_list: list[ItemLinks]) -> str:
    """Format links as JSON."""
    data = [l.to_dict() for l in links_list]
    if len(data) == 1:
        return json.dumps(data[0], indent=2)
    return json.dumps(data, indent=2)


def print_create_results(results: list[dict[str, Any]], *, dry_run: bool = False) -> None:
    """Print link creation results."""
    created = sum(1 for r in results if r["status"] == "created")
    exists = sum(1 for r in results if r["status"] == "exists")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    for r in results:
        status_icon = {
            "created": "+",
            "exists": "=",
            "skipped": "~",
            "error": "!",
        }.get(r["status"], "?")
        print(f"  [{status_icon}] {r['source']} -> {r['target']}: {r['message']}")

    print()
    if dry_run:
        print(f"Summary (dry run): {skipped} would be created, {exists} already exist, {errors} errors")
    else:
        print(f"Summary: {created} created, {exists} already exist, {errors} errors")
