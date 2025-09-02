#!/usr/bin/env python3
"""
jamaclean.py

Downloads Jama items (by document key or folder), fetches their raw HTML descriptions,
cleans them (removes <span> wrappers and inline styles, preserves &nbsp;),
updates the Jama item description in-place, and outputs each item's key, title, and both old and cleaned HTML.

Usage:
    python jamaclean.py [--recursive] JAMA_KEY [JAMA_KEY ...]
Options:
    -r, --recursive   Recursively fetch items in subfolders for folder keys.
"""
import sys
import os
import argparse
from typing import Optional, List, Set
from py_jama_rest_client.client import JamaClient
from bs4 import BeautifulSoup

# ———————————————— Configuration ————————————————

# ———————————————— HTML Cleaning ————————————————
def clean_html(html: str) -> str:
    """Remove all style attrs and unwrap <span> tags, preserve &nbsp;."""
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(attrs={'style': True}):
        del tag['style']
    for span in soup.find_all('span'):
        span.unwrap()
    return str(soup).replace('\xa0', '&nbsp;')

# ———————————————— Jama Helpers ————————————————
def get_item_id(jama_client, doc_key: str) -> Optional[int]:
    items = jama_client.get_abstract_items(contains=doc_key)
    for itm in items:
        if itm.get("documentKey") == doc_key:
            return itm.get("id")
    return None


def find_field_key(fields: dict, prefix: str) -> Optional[str]:
    for key in fields:
        if key.lower().startswith(prefix.lower()):
            return key
    return None


def fetch_and_update_item(jama_client, doc_key: str) -> Optional[str]:
    """
    Fetches a Jama item, cleans its HTML description, patches the item
    if changed, and returns formatted output.
    """
    item_id = get_item_id(jama_client, doc_key)
    if not item_id:
        print(f"Error: item '{doc_key}' not found", file=sys.stderr)
        return None

    try:
        item = jama_client.get_item(item_id)
    except Exception as e:
        print(f"Error retrieving '{doc_key}': {e}", file=sys.stderr)
        return None

    fields = item.get("fields", {})
    title = fields.get("name", doc_key).strip()
    desc_key = find_field_key(fields, "description")
    raw_html = fields.get(desc_key, "") if desc_key else ""
    cleaned_html = clean_html(raw_html)

    output = [
        f"Document Key: {doc_key}",
        f"Document Title: {title}",
        "Old HTML:",
        raw_html,
        "New HTML:",
        cleaned_html
    ]

    # Update description if changed
    if desc_key and raw_html != cleaned_html:
        print(f"Updating description for {doc_key}...")
        patch = [{
            "op": "replace",
            "path": f"/fields/{desc_key}",
            "value": cleaned_html
        }]
        try:
            jama_client.patch_item(item_id, patch)
            print(f"Successfully updated description for {doc_key}")
        except Exception as e:
            print(f"Failed to update description for {doc_key}: {e}", file=sys.stderr)
    else:
        print(f"No changes needed for {doc_key}")

    return "\n".join(output) + "\n"


def collect_keys_from_folder(
    jama_client,
    folder_id: int,
    recursive: bool = False,
    seen: Set[int]  = None
) -> List[str]:
    if seen is None:
        seen = set()
    keys: List[str] = []
    try:
        children = jama_client.get_item_children(folder_id)
    except Exception as e:
        print(f"Error fetching folder {folder_id}: {e}", file=sys.stderr)
        return keys

    for child in children:
        cid = child.get("id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        flds = child.get("fields", {})
        dk = flds.get("documentKey")
        if dk:
            keys.append(dk)
        elif recursive:
            keys += collect_keys_from_folder(jama_client, cid, recursive, seen)
    return keys

# ———————————————— CLI Entrypoint ————————————————
def main():
    parser = argparse.ArgumentParser(description="Fetch, clean, and update Jama HTML descriptions.")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Recurse into folder keys.")
    parser.add_argument("keys", nargs="+", metavar="JAMA_KEY",
                        help="Jama document or folder key (e.g. ABSD-SWVER-257 or FLD...).")
    args = parser.parse_args()

    # Load configuration after parsing arguments (so --help works)
    JAMA_URL      = os.getenv("JAMA_URL")
    CLIENT_ID     = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    if not all([JAMA_URL, CLIENT_ID, CLIENT_SECRET]):
        sys.exit("Error: Missing one or more required environment variables: JAMA_URL, CLIENT_ID, CLIENT_SECRET")

    # Initialize Jama client
    jama = JamaClient(
        host_domain=JAMA_URL,
        oauth=True,
        credentials=(CLIENT_ID, CLIENT_SECRET)
    )

    doc_keys: List[str] = []
    for key in args.keys:
        if "FLD" in key.upper():
            fid = get_item_id(jama, key)
            if not fid:
                print(f"Error: folder '{key}' not found", file=sys.stderr)
                continue
            found = collect_keys_from_folder(jama, fid, recursive=args.recursive)
            if not found:
                print(f"No items in folder '{key}'", file=sys.stderr)
            else:
                doc_keys.extend(found)
        else:
            doc_keys.append(key)

    if not doc_keys:
        sys.exit(1)

    for dk in doc_keys:
        result = fetch_and_update_item(jama, dk)
        if result:
            print(result)

if __name__ == "__main__":
    main()

