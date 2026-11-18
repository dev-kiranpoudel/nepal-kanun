"""Build work/<law-id>/web.json from flat source files, for laws nepallaws.com doesn't have.

Another website's text, or a transcription of the PDF page images, is written as
work/<law-id>/src-1.json, src-2.json, ... : each a list of {"title", "text"} in reading order.
The title says what the item is: "भाग-१ ...", "परिच्छेद-२ ...", "दफा ३: ..." or anything else
(प्रस्तावना, अनुसूची-१ ...). This nests them into the same tree fetch_nepallaws.py writes,
so check_text.py and to_app_json.py work unchanged.

Usage: python3 scripts/build_web.py <law-id>
"""
import json
import re
import sys
from pathlib import Path

from check_text import SEC_TITLE, norm

ROOT = Path(__file__).resolve().parent.parent


def tree_from_items(items, title):
    root = {"id": 0, "title": title, "order": 0, "text": "", "children": []}
    bhag = chapter = None
    for i, it in enumerate(items, 1):
        t = norm(it["title"]).strip()
        n = {"id": i, "title": t, "order": i, "text": it.get("text", "").strip(), "children": []}
        if re.match(r"भाग\s*[-–]?\s*[०-९]", t):
            root["children"].append(n)
            bhag, chapter = n, None
        elif re.match(r"परिच्छेद\s*[-–]?\s*[०-९]", t):
            (bhag or root)["children"].append(n)
            chapter = n
        elif SEC_TITLE.match(t):
            (chapter or bhag or root)["children"].append(n)
        else:  # preamble, schedule: a part of its own
            root["children"].append(n)
            bhag = chapter = None
    return root


def main():
    law_id = sys.argv[1]
    work = ROOT / "work" / law_id
    files = sorted(work.glob("src-*.json"), key=lambda p: int(re.search(r"\d+", p.stem).group()))
    assert files, f"no src-*.json in {work}"
    items = [it for f in files for it in json.loads(f.read_text())]
    nums = [SEC_TITLE.match(norm(it["title"]).strip()) for it in items]
    nums = [m.group(1) + m.group(2) for m in nums if m]
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    if dupes:  # usually a section copied by two neighbouring chunks
        print("duplicate sections:", ", ".join(dupes))
    title = next(l["titleNe"] for l in json.loads((ROOT / "data" / "index.json").read_text())["laws"] if l["id"] == law_id)
    (work / "web.json").write_text(json.dumps(tree_from_items(items, title), ensure_ascii=False, indent=1))
    print(f"{len(files)} files, {len(items)} items, {len(nums)} sections -> {work / 'web.json'}")


if __name__ == "__main__":
    main()
