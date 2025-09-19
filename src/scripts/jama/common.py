#!/usr/bin/env python3

from __future__ import annotations

import os
import time
from collections.abc import Callable
from functools import lru_cache

from dotenv import load_dotenv
from py_jama_rest_client.client import APIException, JamaClient

__all__ = [
    "collect_keys_from_folder",
    "find_field_key",
    "get_field_names_from_schema",
    "get_item_id",
    "get_item_id_cached",
    "jama_url_for_item",
    "load_jama",
    "rate_limit",
    "relationship_exists",
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


def collect_keys_from_folder(jama: JamaClient, folder_id: int, recursive: bool = False, seen: set[int] | None = None) -> list[str]:
    seen = seen or set()
    keys: list[str] = []
    try:
        children = jama.get_item_children(folder_id)
    except APIException:
        return keys
    for child in children:
        cid = child.get("id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        doc_key = child.get("fields", {}).get("documentKey")
        if doc_key:
            keys.append(doc_key)
        elif recursive:
            keys += collect_keys_from_folder(jama, cid, recursive, seen)
    return keys


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
            if "$" in field_name:
                base_name = field_name.split("$")[0]
            else:
                base_name = field_name

            # Map base name to actual field name
            field_map[base_name] = field_name

        return field_map
    except APIException:
        return {}


def with_retries(fn: Callable[[], any], *, tries: int = 3, backoff: float = 0.5):
    """Call a function with simple exponential backoff on APIException."""
    for i in range(tries):
        try:
            return fn()
        except APIException:
            if i == tries - 1:
                raise
            time.sleep(backoff * (2**i))


def jama_url_for_item(item_id: int) -> str:
    host = os.getenv("JAMA_URL", "").rstrip("/")
    if not host:
        return f"/perspective.req?docId={item_id}"
    return f"{host}/perspective.req?docId={item_id}"


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
