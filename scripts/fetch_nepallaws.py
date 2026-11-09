"""Download one law's Nepali text from nepallaws.com into work/<law-id>/web.json.

nepallaws.com keeps each law as a tree of WordPress "docs": law -> भाग / परिच्छेद -> दफा.
This walks that tree through the public REST API and keeps every node's title and plain text.
The text is only an input: scripts/check_text.py checks it against the official PDF.

Usage: python3 scripts/fetch_nepallaws.py <law-id> <nepallaws-doc-id>
  e.g. python3 scripts/fetch_nepallaws.py lc-13454 46420   (मुलुकी अपराध संहिता, २०७४)
"""
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://nepallaws.com/wp-json/wp/v2/docs"
WORK = Path(__file__).resolve().parent.parent / "work"


CACHE = WORK / "nepallaws-cache"  # one file per request, so a rerun after an error resumes


def get(url):
    cached = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    if cached.exists():
        return json.loads(cached.read_text())
    for attempt in range(4):
        time.sleep(1 + attempt * 10)  # be gentle with their server; back off on errors
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nepal-kanun-builder"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            break
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3:
                raise
            print(f"retry after {e}", flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data, ensure_ascii=False))
    return data


def plain(rendered):
    """HTML -> text, one paragraph per line."""
    t = re.sub(r"(?i)<br\s*/?>|</(p|h\d|li|div|tr)>", "\n", rendered)
    t = re.sub(r"(?i)</t[dh]>", "\t", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n")]
    return "\n".join(l for l in lines if l)


def node(doc_id, title, order):
    d = get(f"{API}/{doc_id}?_fields=content")
    kids = []
    page = 1
    while True:
        batch = get(f"{API}?parent={doc_id}&per_page=100&page={page}&_fields=id,title,menu_order")
        kids += batch
        if len(batch) < 100:
            break
        page += 1
    kids.sort(key=lambda k: k["menu_order"])
    print(f"{doc_id} {title[:50]} ({len(kids)})", flush=True)
    return {
        "id": doc_id,
        "title": html.unescape(title).strip(),
        "order": order,
        "text": plain(d["content"]["rendered"]),
        "children": [node(k["id"], k["title"]["rendered"], k["menu_order"]) for k in kids],
    }


def main():
    law_id, doc_id = sys.argv[1], int(sys.argv[2])
    root = get(f"{API}/{doc_id}?_fields=title")
    tree = node(doc_id, root["title"]["rendered"], 0)
    out = WORK / law_id / "web.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tree, ensure_ascii=False, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
