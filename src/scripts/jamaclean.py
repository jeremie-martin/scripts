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

import argparse
import sys

from bs4 import BeautifulSoup

from scripts.jama.common import (
    collect_keys_from_folder,
    find_field_key,
    get_item_id,
    load_jama,
    with_retries,
)


# ———————————————— HTML Cleaning ————————————————
def clean_html(html: str) -> str:
    """Remove all style attrs and unwrap <span> tags, preserve &nbsp;."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(attrs={"style": True}):
        del tag["style"]
    for span in soup.find_all("span"):
        span.unwrap()
    return str(soup).replace("\xa0", "&nbsp;")



def fetch_and_update_item(jama_client, doc_key: str) -> str | None:
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

    output = [f"Document Key: {doc_key}", f"Document Title: {title}", "Old HTML:", raw_html, "New HTML:", cleaned_html]

    # Update description if changed
    if desc_key and raw_html != cleaned_html:
        print(f"Updating description for {doc_key}...")
        patch = [{"op": "replace", "path": f"/fields/{desc_key}", "value": cleaned_html}]
        try:
            with_retries(lambda: jama_client.patch_item(item_id, patch))
            print(f"Successfully updated description for {doc_key}")
        except Exception as e:
            print(f"Failed to update description for {doc_key}: {e}", file=sys.stderr)
    else:
        print(f"No changes needed for {doc_key}")

    return "\n".join(output) + "\n"


# ———————————————— CLI Entrypoint ————————————————
def main():
    parser = argparse.ArgumentParser(description="Fetch, clean, and update Jama HTML descriptions.")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into folder keys.")
    parser.add_argument("keys", nargs="+", metavar="JAMA_KEY", help="Jama document or folder key (e.g. ABSD-SWVER-257 or FLD...).")
    args = parser.parse_args()

    # Load Jama client using shared helper
    try:
        jama = load_jama()
    except Exception as e:
        sys.exit(f"Error: {e}")

    doc_keys: list[str] = []
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
