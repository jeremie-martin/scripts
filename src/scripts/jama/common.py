from __future__ import annotations
import os, time
from typing import Optional, Set, List
from dotenv import load_dotenv
from py_jama_rest_client.client import JamaClient, APIException

__all__ = ["load_jama", "get_item_id", "collect_keys_from_folder", "rate_limit"]

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

def get_item_id(jama: JamaClient, document_key: str) -> Optional[int]:
    try:
        for item in jama.get_abstract_items(contains=document_key):
            if item.get("documentKey") == document_key:
                return item.get("id")
    except APIException:
        pass
    return None

def collect_keys_from_folder(jama: JamaClient, folder_id: int, recursive: bool=False, seen: Set[int]|None=None) -> List[str]:
    seen = seen or set()
    keys: List[str] = []
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
