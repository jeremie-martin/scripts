#!/usr/bin/env python3

from __future__ import annotations

import os
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from markdownify import markdownify as _markdownify
from py_jama_rest_client.client import APIException, JamaClient

__all__ = [
    "clean_html_content",
    "collect_keys_from_folder",
    "expand_container_by_id",
    "expand_keys",
    "find_field_key",
    "get_document_key_from_stub",
    "get_field_names_from_schema",
    "get_item_id",
    "get_item_id_cached",
    "get_item_type_info_cached",
    "html_to_markdown",
    "is_container_stub",
    "jama_url_for_item",
    "load_jama",
    "load_keys_from_file_or_args",
    "rate_limit",
    "relationship_exists",
    "safe_copy_to_clipboard",
    "with_retries",
]

load_dotenv()  # once, centrally


class JamaEnvError(RuntimeError):
    pass


def load_jama() -> JamaClient:
    JAMA_URL = os.getenv("JAMA_URL")
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    if not all([JAMA_URL, CLIENT_ID, CLIENT_SECRET]):
        raise JamaEnvError("Missing JAMA_URL/CLIENT_ID/CLIENT_SECRET in environment")
    return JamaClient(host_domain=JAMA_URL, oauth=True, credentials=(CLIENT_ID, CLIENT_SECRET))


def get_item_id(jama: JamaClient, document_key: str) -> int | None:
    try:
        for item in jama.get_abstract_items(contains=document_key):
            if item.get("documentKey") == document_key:
                return item.get("id")
    except APIException:
        pass
    return None


@lru_cache(maxsize=4096)
def get_item_id_cached(host: str, client_id: str, document_key: str) -> int | None:
    """LRU-cached variant of get_item_id keyed by host/client_id/doc_key.

    Call as: get_item_id_cached(os.getenv("JAMA_URL",""), os.getenv("CLIENT_ID",""), key)
    Note: requires an active Jama client constructed with current env.
    """
    jama = load_jama()
    return get_item_id(jama, document_key)


def get_document_key_from_stub(item: dict[str, Any]) -> str | None:
    """Return documentKey from a Jama item stub (child record) if present."""
    doc_key = item.get("documentKey")
    if doc_key:
        return doc_key
    fields = item.get("fields")
    if isinstance(fields, dict):
        field_key = fields.get("documentKey")
        if isinstance(field_key, str):
            return field_key
    return None


@lru_cache(maxsize=512)
def get_item_type_info_cached(host: str, client_id: str, item_type_id: int) -> dict[str, Any]:
    """Cached lookup of item type metadata."""
    _ = host, client_id  # ensure arguments participate in cache key
    jama = load_jama()
    try:
        result = jama.get_item_type(item_type_id)
        return result or {}
    except APIException:
        return {}


def clean_html_content(html: str) -> str:
    """Strip inline styles and span wrappers while preserving non-breaking spaces."""
    if not html:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(attrs={"style": True}):
        del tag["style"]
    for span in soup.find_all("span"):
        span.unwrap()
    return str(soup).replace("\xa0", "&nbsp;")


def html_to_markdown(html: str, *, clean: bool = True) -> str:
    """Convert HTML to Markdown, optionally cleaning first."""
    source = clean_html_content(html) if clean else html
    # markdownify returns str; ensure consistent whitespace trimming
    return _markdownify(source or "", escape_asterisks=False, escape_underscores=False, escape_misc=False).strip()


def _looks_like_container_type(type_info: dict[str, Any]) -> bool:
    """Decide container by Jama item type metadata."""
    type_key = str(type_info.get("typeKey", "")).upper()
    if type_key in {"FOLDER", "SET", "COMPONENT", "PROJECT", "CMP"}:
        return True
    name = str(type_info.get("name", "")).lower()
    return any(token in name for token in ("folder", "set", "component", "project", "cmp"))


def is_container_stub(jama: JamaClient, stub: dict[str, Any]) -> bool:
    """
    Decide if a child stub from get_item_children() represents a container.

    This function uses cascading heuristics because Jama's API returns data inconsistently:
    - itemType can be a string (e.g., "Folder")
    - itemType can be a dict with typeKey and name
    - itemType can be an int ID requiring lookup
    - documentKey may be present or missing
    - hasChildren flag may or may not be set

    Each heuristic handles a different representation from the API.
    Heuristics adapted from gate_traceability.py.

    Args:
        jama: Jama client
        stub: Child stub dictionary from get_item_children()

    Returns:
        True if the stub represents a container (folder/set/component), False otherwise
    """
    doc_key = get_document_key_from_stub(stub)
    if doc_key and "FLD" in doc_key.upper():
        return True

    item_type_raw = stub.get("itemType")

    if isinstance(item_type_raw, str):
        lowered = item_type_raw.lower()
        if any(tok in lowered for tok in ("folder", "set", "component", "project", "container", "cmp")):
            return True

    # Jama SDK sometimes provides a dict with type info
    if isinstance(item_type_raw, dict):
        if _looks_like_container_type(item_type_raw):
            return True
        type_id = item_type_raw.get("id")
        if isinstance(type_id, int):
            item_type_raw = type_id

    if isinstance(item_type_raw, int):
        info = get_item_type_info_cached(os.getenv("JAMA_URL", ""), os.getenv("CLIENT_ID", ""), item_type_raw)
        if info and _looks_like_container_type(info):
            return True

    # When no documentKey is present but we have some type info, treat as container
    if not doc_key and item_type_raw:
        return True

    # Fallback to child metadata flag
    has_children = stub.get("hasChildren")
    if isinstance(has_children, bool):
        return has_children

    return False


def expand_container_by_id(
    jama: JamaClient,
    container_id: int,
    seen_ids: set[int] | None = None,
) -> list[str]:
    """Expand a container item id into non-container document keys (always recursive)."""
    if seen_ids is None:
        seen_ids = set()

    if container_id in seen_ids:
        return []
    seen_ids.add(container_id)

    try:
        children = jama.get_item_children(container_id)
    except APIException:
        return []

    expanded: list[str] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        child_id = child.get("id")
        doc_key = get_document_key_from_stub(child)
        if is_container_stub(jama, child):
            if child_id and child_id not in seen_ids:
                expanded.extend(expand_container_by_id(jama, child_id, seen_ids))
            continue
        if doc_key:
            expanded.append(doc_key)
    return expanded


def expand_keys(
    jama: JamaClient,
    keys: list[str],
    *,
    on_missing: Callable[[str], None] | None = None,
    on_empty_container: Callable[[str], None] | None = None,
) -> list[str]:
    """
    Resolve a mixed list of document or container keys into concrete document keys.
    Container keys (folders, sets, components) are automatically expanded recursively.
    Deduplicates while preserving order. Optionally invoke ``on_missing`` for keys that
    cannot be resolved to an item id and ``on_empty_container`` for containers that
    expand to no leaf items.
    """
    resolved: list[str] = []
    seen_keys: set[str] = set()
    seen_container_ids: set[int] = set()

    for key in keys:
        if not key:
            continue

        item_id = get_item_id(jama, key)
        if not item_id:
            if on_missing:
                on_missing(key)
            continue

        try:
            item = jama.get_item(item_id)
        except APIException:
            continue

        if is_container_stub(jama, item):
            expanded = expand_container_by_id(jama, item_id, seen_container_ids)
            if not expanded and on_empty_container:
                on_empty_container(key)
            for doc_key in expanded:
                if doc_key and doc_key not in seen_keys:
                    seen_keys.add(doc_key)
                    resolved.append(doc_key)
        else:
            doc_key = get_document_key_from_stub(item) or key
            if doc_key not in seen_keys:
                seen_keys.add(doc_key)
                resolved.append(doc_key)

    return resolved


def load_keys_from_file_or_args(args_list: list[str]) -> list[str]:
    """If the single argument is a file path, load one key per non-empty line; otherwise return the list."""
    if len(args_list) == 1:
        path = args_list[0]
        if os.path.isfile(path):
            with open(path) as handle:
                return [line.strip() for line in handle if line.strip()]
    return args_list


def collect_keys_from_folder(
    jama: JamaClient,
    folder_id: int,
    seen: set[int] | None = None,
) -> list[str]:
    """Alias for expand_container_by_id (always recursive)."""
    return expand_container_by_id(jama, folder_id, seen)


def rate_limit(seconds: float = 0.1):
    time.sleep(seconds)


def find_field_key(fields: dict, prefix: str) -> str | None:
    """Find a case-insensitive field key by prefix in a Jama item's fields dict."""
    pref = prefix.lower()
    for k in fields:
        if k.lower().startswith(pref):
            return k
    return None


@lru_cache(maxsize=256)
def get_field_names_from_schema(host: str, client_id: str, item_type_id: int) -> dict[str, str]:
    """Get field name mappings from item type schema, cached by host/client_id/item_type_id.

    Returns a dict mapping base field names (like 'initial_conditions') to their
    actual schema names (like 'initial_conditions$199').

    Call as: get_field_names_from_schema(os.getenv("JAMA_URL",""), os.getenv("CLIENT_ID",""), item_type_id)
    """
    jama = load_jama()
    try:
        item_type = jama.get_item_type(item_type_id)
        field_defs = item_type.get("fields", [])

        field_map = {}
        for field_def in field_defs:
            field_name = field_def.get("name", "")
            if not field_name:
                continue

            # Extract base name by removing suffix (everything after $)
            base_name = field_name.split("$")[0] if "$" in field_name else field_name

            # Map base name to actual field name
            field_map[base_name] = field_name

        return field_map
    except APIException:
        return {}


def with_retries(fn: Callable[[], Any], *, tries: int = 3, backoff: float = 0.5):
    """Call a function with simple exponential backoff on APIException."""
    for i in range(tries):
        try:
            return fn()
        except APIException:
            if i == tries - 1:
                raise
            time.sleep(backoff * (2**i))


def jama_url_for_item(item_id: int, project_id: int | None = None) -> str:
    """
    Construct a proper Jama Cloud item URL for use in Markdown links.

    Example:
        https://wyss-prod.jamacloud.com/perspective.req#/items/7501878?projectId=65
    """
    host = os.getenv("JAMA_URL", "").rstrip("/")
    if not host:
        raise JamaEnvError("Missing JAMA_URL in environment")

    # Default projectId fallback from environment if defined
    if project_id is None:
        try:
            project_id = int(os.getenv("JAMA_PROJECT_ID", "0"))
        except ValueError:
            project_id = 0

    if project_id:
        return f"{host}/perspective.req#/items/{item_id}?projectId={project_id}"
    return f"{host}/perspective.req#/items/{item_id}"


def relationship_exists(jama: JamaClient, from_item_id: int, to_item_id: int) -> bool:
    """Check if a relationship already exists between two items (both directions)."""
    try:
        downstream = jama.get_items_downstream_relationships(from_item_id)
        for rel in downstream:
            if rel.get("toItem") == to_item_id:
                return True
        upstream = jama.get_items_upstream_relationships(to_item_id)
        for rel in upstream:
            if rel.get("fromItem") == from_item_id:
                return True
    except APIException:
        return False
    return False


def _copy_to_linux_clipboard(text: str) -> None:
    """Copy text to Linux PRIMARY and CLIPBOARD selections."""
    import shutil
    import subprocess

    if shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        subprocess.run(["xclip", "-selection", "primary"], input=text.encode(), check=True)
    elif shutil.which("xsel"):
        subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode(), check=True)
        subprocess.run(["xsel", "--primary", "--input"], input=text.encode(), check=True)
    elif shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=text.encode(), check=True)
        subprocess.run(["wl-copy", "--primary"], input=text.encode(), check=True)
    else:
        raise RuntimeError("No Linux clipboard backend found (xclip, xsel, or wl-copy)")


def copy_to_all_clipboards(text: str) -> None:
    """Copy text to all available clipboards (PRIMARY and CLIPBOARD on Linux)."""
    import platform

    if platform.system() == "Linux":
        _copy_to_linux_clipboard(text)
    else:
        import pyperclip

        pyperclip.copy(text)


def safe_copy_to_clipboard(text: str, message: str = "Output copied to clipboard.") -> None:
    """Copy text to clipboard with error handling."""
    import sys

    try:
        copy_to_all_clipboards(text)
        print(message)
    except Exception as e:
        print(f"Failed to copy to clipboard: {e}", file=sys.stderr)
