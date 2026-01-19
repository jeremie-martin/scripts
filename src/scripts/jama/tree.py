#!/usr/bin/env python3
"""Hierarchical container traversal utilities for Jama."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py_jama_rest_client.client import JamaClient


@dataclass
class ItemNode:
    """Represents an item or container in the tree."""

    doc_key: str | None
    name: str
    item_id: int
    path: list[str]
    is_container: bool
    children: list["ItemNode"]

    @property
    def path_str(self) -> str:
        """Get path as a string."""
        if not self.path:
            return ""
        return " / ".join(self.path)


def build_tree(
    jama: "JamaClient",
    container_id: int,
    container_name: str,
    container_doc_key: str,
    path: list[str],
    seen_ids: set[int] | None = None,
) -> ItemNode:
    """
    Recursively build a tree structure from a container.

    Args:
        jama: Jama client
        container_id: Container item ID
        container_name: Container name
        container_doc_key: Container document key
        path: Current path in the tree
        seen_ids: Set of visited container IDs (for cycle detection)

    Returns:
        ItemNode representing the container tree
    """
    from scripts.jama.common import get_document_key_from_stub, is_container_stub

    if seen_ids is None:
        seen_ids = set()

    if container_id in seen_ids:
        return ItemNode(doc_key=container_doc_key, name=container_name, item_id=container_id, path=path, is_container=True, children=[])

    seen_ids.add(container_id)
    current_path = [*path, container_name]

    try:
        children = jama.get_item_children(container_id)
    except Exception:
        return ItemNode(doc_key=container_doc_key, name=container_name, item_id=container_id, path=path, is_container=True, children=[])

    child_nodes = []
    for child in children:
        if not isinstance(child, dict):
            continue

        child_id = child.get("id")
        child_doc_key = get_document_key_from_stub(child)

        if is_container_stub(jama, child):
            if child_id and child_id not in seen_ids:
                try:
                    child_item = jama.get_item(child_id)
                    child_name = child_item.get("name") or child_item.get("fields", {}).get("name") or child.get("documentKey", "")
                except Exception:
                    child_name = child.get("documentKey", "")
                child_doc_key = child_doc_key or child.get("documentKey", "")
                sub_tree = build_tree(jama, child_id, child_name, child_doc_key, current_path, seen_ids)
                child_nodes.append(sub_tree)
        elif child_doc_key:
            child_name = child.get("name", child_doc_key)
            child_nodes.append(
                ItemNode(
                    doc_key=child_doc_key,
                    name=child_name,
                    item_id=child_id or 0,
                    path=current_path,
                    is_container=False,
                    children=[],
                )
            )

    return ItemNode(
        doc_key=container_doc_key,
        name=container_name,
        item_id=container_id,
        path=path,
        is_container=True,
        children=child_nodes,
    )
