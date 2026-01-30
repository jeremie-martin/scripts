#!/usr/bin/env python3
"""
Link management for Jama items.

Provides functions to query and create upstream/downstream relationships.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from typing import Any, Literal

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


def get_upstream_relationships(jama: JamaClient, item_id: int) -> list[dict[str, Any]]:
    """Get upstream relationships (items that this item links TO).

    Returns list of relationship dicts with 'id', 'fromItem', 'toItem'.
    """
    try:
        return jama.get_items_upstream_relationships(item_id)
    except APIException:
        return []


def get_downstream_relationships(jama: JamaClient, item_id: int) -> list[dict[str, Any]]:
    """Get downstream relationships (items that link TO this item).

    Returns list of relationship dicts with 'id', 'fromItem', 'toItem'.
    """
    try:
        return jama.get_items_downstream_relationships(item_id)
    except APIException:
        return []


def get_upstream_ids(jama: JamaClient, item_id: int) -> list[int]:
    """Get upstream related item IDs (items that this item links TO)."""
    rels = get_upstream_relationships(jama, item_id)
    return [r.get("fromItem") for r in rels if r.get("fromItem")]


def get_downstream_ids(jama: JamaClient, item_id: int) -> list[int]:
    """Get downstream related item IDs (items that link TO this item)."""
    rels = get_downstream_relationships(jama, item_id)
    return [r.get("toItem") for r in rels if r.get("toItem")]


def find_relationship_id(
    jama: JamaClient,
    from_item_id: int,
    to_item_id: int,
) -> int | None:
    """Find the relationship ID between two items.

    Searches downstream relationships of from_item for a relationship
    where toItem == to_item_id.

    Returns relationship ID if found, None otherwise.
    """
    rels = get_downstream_relationships(jama, from_item_id)
    for rel in rels:
        if rel.get("toItem") == to_item_id:
            return rel.get("id")
    return None


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


def create_link_upstream(
    jama: JamaClient,
    item_key: str,
    target_key: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Create an upstream link (target becomes upstream of item).

    This means item traces TO target.
    In Jama terms: post_relationship(from_item=target, to_item=item)

    Args:
        jama: Jama client
        item_key: The item you're adding links to
        target_key: The item that becomes upstream (item will trace to this)
        dry_run: If True, don't actually create the link

    Returns:
        Dict with status: "created", "exists", "skipped", or "error"
    """
    result = {
        "item": item_key,
        "target": target_key,
        "direction": "upstream",
        "status": "error",
        "message": "",
    }

    # Resolve IDs
    item_id = get_item_id(jama, item_key)
    if not item_id:
        result["message"] = f"Item '{item_key}' not found"
        return result

    target_id = get_item_id(jama, target_key)
    if not target_id:
        result["message"] = f"Target item '{target_key}' not found"
        return result

    # Check if relationship already exists
    # For upstream: target is from_item, item is to_item
    if relationship_exists(jama, target_id, item_id):
        result["status"] = "exists"
        result["message"] = "Relationship already exists"
        return result

    if dry_run:
        result["status"] = "skipped"
        result["message"] = "Would create link (dry run)"
        return result

    # Create the relationship
    # In Jama: from_item is upstream of to_item
    # So we want target to be upstream of item
    try:
        rel_id = jama.post_relationship(from_item=target_id, to_item=item_id)
        result["status"] = "created"
        result["message"] = f"Created relationship (id={rel_id})"
        result["relationship_id"] = rel_id
    except APIException as e:
        result["message"] = f"API error: {e}"

    return result


def create_link_downstream(
    jama: JamaClient,
    item_key: str,
    target_key: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Create a downstream link (target becomes downstream of item).

    This means target traces TO item.
    In Jama terms: post_relationship(from_item=item, to_item=target)

    Args:
        jama: Jama client
        item_key: The item you're adding links to
        target_key: The item that becomes downstream (will trace to item)
        dry_run: If True, don't actually create the link

    Returns:
        Dict with status: "created", "exists", "skipped", or "error"
    """
    result = {
        "item": item_key,
        "target": target_key,
        "direction": "downstream",
        "status": "error",
        "message": "",
    }

    # Resolve IDs
    item_id = get_item_id(jama, item_key)
    if not item_id:
        result["message"] = f"Item '{item_key}' not found"
        return result

    target_id = get_item_id(jama, target_key)
    if not target_id:
        result["message"] = f"Target item '{target_key}' not found"
        return result

    # Check if relationship already exists
    # For downstream: item is from_item, target is to_item
    if relationship_exists(jama, item_id, target_id):
        result["status"] = "exists"
        result["message"] = "Relationship already exists"
        return result

    if dry_run:
        result["status"] = "skipped"
        result["message"] = "Would create link (dry run)"
        return result

    # Create the relationship
    # In Jama: from_item is upstream of to_item
    # So item becomes upstream of target (target is downstream of item)
    try:
        rel_id = jama.post_relationship(from_item=item_id, to_item=target_id)
        result["status"] = "created"
        result["message"] = f"Created relationship (id={rel_id})"
        result["relationship_id"] = rel_id
    except APIException as e:
        result["message"] = f"API error: {e}"

    return result


def create_links_upstream(
    jama: JamaClient,
    item_key: str,
    target_keys: list[str],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Create upstream links from item to multiple targets.

    Args:
        jama: Jama client
        item_key: The item to add links to
        target_keys: List of target document keys (become upstream)
        dry_run: If True, don't actually create links

    Returns:
        List of result dicts for each target
    """
    results = []
    for target_key in target_keys:
        result = create_link_upstream(jama, item_key, target_key, dry_run=dry_run)
        results.append(result)
        if result["status"] == "created":
            rate_limit(0.1)
    return results


def create_links_downstream(
    jama: JamaClient,
    item_key: str,
    target_keys: list[str],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Create downstream links from item to multiple targets.

    Args:
        jama: Jama client
        item_key: The item to add links to
        target_keys: List of target document keys (become downstream)
        dry_run: If True, don't actually create links

    Returns:
        List of result dicts for each target
    """
    results = []
    for target_key in target_keys:
        result = create_link_downstream(jama, item_key, target_key, dry_run=dry_run)
        results.append(result)
        if result["status"] == "created":
            rate_limit(0.1)
    return results


def delete_link(
    jama: JamaClient,
    item_key: str,
    target_key: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Delete a link between two items.

    Searches both directions to find and remove the relationship.

    Args:
        jama: Jama client
        item_key: Document key of one item
        target_key: Document key of the other item
        dry_run: If True, don't actually delete

    Returns:
        Dict with status: "deleted", "not_found", "skipped", or "error"
    """
    result = {
        "item": item_key,
        "target": target_key,
        "status": "error",
        "message": "",
    }

    # Resolve IDs
    item_id = get_item_id(jama, item_key)
    if not item_id:
        result["message"] = f"Item '{item_key}' not found"
        return result

    target_id = get_item_id(jama, target_key)
    if not target_id:
        result["message"] = f"Target item '{target_key}' not found"
        return result

    # Find relationship ID (check both directions)
    rel_id = find_relationship_id(jama, item_id, target_id)
    if rel_id is None:
        rel_id = find_relationship_id(jama, target_id, item_id)

    if rel_id is None:
        result["status"] = "not_found"
        result["message"] = "No relationship found between items"
        return result

    if dry_run:
        result["status"] = "skipped"
        result["message"] = f"Would delete relationship (id={rel_id})"
        result["relationship_id"] = rel_id
        return result

    try:
        jama.delete_relationships(rel_id)
        result["status"] = "deleted"
        result["message"] = f"Deleted relationship (id={rel_id})"
        result["relationship_id"] = rel_id
    except APIException as e:
        result["message"] = f"API error: {e}"

    return result


def delete_links(
    jama: JamaClient,
    item_key: str,
    target_keys: list[str],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Delete multiple links from an item.

    Args:
        jama: Jama client
        item_key: Document key of the item
        target_keys: List of target document keys to unlink
        dry_run: If True, don't actually delete

    Returns:
        List of result dicts for each target
    """
    results = []
    for target_key in target_keys:
        result = delete_link(jama, item_key, target_key, dry_run=dry_run)
        results.append(result)
        if result["status"] == "deleted":
            rate_limit(0.1)
    return results


def delete_all_links(
    jama: JamaClient,
    item_key: str,
    *,
    direction: Literal["upstream", "downstream", "both"] = "both",
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Delete all links in specified direction.

    Args:
        jama: Jama client
        item_key: Document key of the item
        direction: Which links to delete ("upstream", "downstream", or "both")
        dry_run: If True, don't actually delete

    Returns:
        List of result dicts for each deleted relationship
    """
    results = []

    item_id = get_item_id(jama, item_key)
    if not item_id:
        return [{
            "item": item_key,
            "status": "error",
            "message": f"Item '{item_key}' not found",
        }]

    # Collect relationships to delete
    rels_to_delete: list[tuple[int, str, int]] = []  # (rel_id, target_key, target_id)

    if direction in ("upstream", "both"):
        for rel in get_upstream_relationships(jama, item_id):
            rel_id = rel.get("id")
            from_item_id = rel.get("fromItem")
            if rel_id and from_item_id:
                linked = fetch_item_metadata(jama, from_item_id)
                if linked:
                    rels_to_delete.append((rel_id, linked.key, from_item_id))
                rate_limit(0.02)

    if direction in ("downstream", "both"):
        for rel in get_downstream_relationships(jama, item_id):
            rel_id = rel.get("id")
            to_item_id = rel.get("toItem")
            if rel_id and to_item_id:
                linked = fetch_item_metadata(jama, to_item_id)
                if linked:
                    rels_to_delete.append((rel_id, linked.key, to_item_id))
                rate_limit(0.02)

    if not rels_to_delete:
        return [{
            "item": item_key,
            "status": "not_found",
            "message": f"No {direction} links found",
        }]

    for rel_id, target_key, _target_id in rels_to_delete:
        result = {
            "item": item_key,
            "target": target_key,
            "status": "error",
            "message": "",
            "relationship_id": rel_id,
        }

        if dry_run:
            result["status"] = "skipped"
            result["message"] = f"Would delete relationship (id={rel_id})"
        else:
            try:
                jama.delete_relationships(rel_id)
                result["status"] = "deleted"
                result["message"] = f"Deleted relationship (id={rel_id})"
            except APIException as e:
                result["message"] = f"API error: {e}"
            rate_limit(0.1)

        results.append(result)

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
        item = r.get("item") or r.get("source", "?")
        target = r.get("target", "?")
        direction = r.get("direction", "upstream")
        arrow = "->" if direction == "upstream" else "<-"
        print(f"  [{status_icon}] {item} {arrow} {target}: {r['message']}")

    print()
    if dry_run:
        print(f"Summary (dry run): {skipped} would be created, {exists} already exist, {errors} errors")
    else:
        print(f"Summary: {created} created, {exists} already exist, {errors} errors")


def print_delete_results(results: list[dict[str, Any]], *, dry_run: bool = False) -> None:
    """Print link deletion results."""
    deleted = sum(1 for r in results if r["status"] == "deleted")
    not_found = sum(1 for r in results if r["status"] == "not_found")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    for r in results:
        status_icon = {
            "deleted": "-",
            "not_found": "?",
            "skipped": "~",
            "error": "!",
        }.get(r["status"], "?")
        item = r.get("item", "?")
        target = r.get("target", "(all)")
        print(f"  [{status_icon}] {item} <-> {target}: {r['message']}")

    print()
    if dry_run:
        print(f"Summary (dry run): {skipped} would be deleted, {not_found} not found, {errors} errors")
    else:
        print(f"Summary: {deleted} deleted, {not_found} not found, {errors} errors")
