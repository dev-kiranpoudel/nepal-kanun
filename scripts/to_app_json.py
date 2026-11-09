"""Write data/text/<law-id>.json from work/<law-id>/web.json plus checked fixes.

Output is the Constitution's format (homeList + detailList) that the app's LawText.fromJson
reads. Each part is a परिच्छेद (with its भाग in the number), or any other group of sections;
the preamble and schedules become parts of their own.

Fixes: work/<law-id>/fixes.json maps a section number to its corrected text, or to
{"title": ..., "text": ...} (both optional), read from the official PDF. The PDF always wins.

Usage: python3 scripts/to_app_json.py <law-id>
"""
import json
import re
import sys
from pathlib import Path

from check_text import SEC_TITLE, fix_markers, norm, sec_key

ROOT = Path(__file__).resolve().parent.parent


def split_heading(title):
    """"परिच्छेद-१ प्रारम्भिक" -> ("परिच्छेद-१", "प्रारम्भिक")."""
    m = re.match(r"^((?:भाग|परिच्छेद|अनुसूची)\s*[-–]?\s*[०-९0-9]+[क-ह]?)\s*[:ःঃ.]?\s*(.*)$", norm(title))
    return (m.group(1).replace(" ", ""), m.group(2).strip()) if m else ("", title.strip())


def body(text):
    # Clauses on their own paragraph, as in the Constitution text.
    return "\n\n".join(l.strip() for l in fix_markers(text).split("\n") if l.strip())


def sec_num(n):
    m = SEC_TITLE.match(norm(n["title"]))
    return m.group(1) + m.group(2)


def build(tree, fixes):
    parts = []

    def section(n):
        m = SEC_TITLE.match(norm(n["title"]))
        num, title = m.group(1) + m.group(2), m.group(3).strip(" .:ः")
        fix = fixes.get(num, {})
        if isinstance(fix, str):
            fix = {"text": fix}
        title, text = fix.get("title", title), fix.get("text", n["text"])
        return {"title": f"{num}. {title}", "description": body(text)}

    def walk(n, bhag):
        kids = n["children"]
        secs = [k for k in kids if SEC_TITLE.match(norm(k["title"]))]
        # Drop nepallaws' empty placeholders (the real section of that number is elsewhere in the tree),
        # and order by number: their menu_order is sometimes wrong.
        secs = sorted((k for k in secs if k["text"].strip() or sec_num(k) not in filled),
                      key=lambda k: sec_key(sec_num(k)))
        if secs:  # a group of sections: one part
            number, name = split_heading(n["title"])
            if bhag and number.startswith("परिच्छेद"):
                number = f"{bhag}, {number}"
            parts.append({"number": number, "name": name, "sections": [section(k) for k in secs]})
        elif not kids and n is not tree:  # a leaf that isn't a section: preamble, schedule
            number, name = split_heading(n["title"])
            parts.append({"number": number, "name": name or n["title"],
                          "sections": [{"title": name or n["title"], "description": body(n["text"])}]})
        for k in kids:
            if SEC_TITLE.match(norm(k["title"])):
                continue  # sections are handled above (placeholders are dropped there)
            walk(k, split_heading(k["title"])[0] if norm(k["title"]).startswith("भाग") else bhag)

    filled = set()

    def collect(n):
        if SEC_TITLE.match(norm(n["title"])) and n["text"].strip():
            filled.add(sec_num(n))
        for k in n["children"]:
            collect(k)

    collect(tree)
    walk(tree, "")
    home, detail = [], []
    for i, p in enumerate(parts, 1):
        # English mirrors the Nepali until an English text exists: Sambidhan's reader has no fallback.
        home.append({"id": i, "title": p["number"], "description": p["name"],
                     "englishTitle": p["number"], "englishDescription": p["name"]})
        detail.append({"id": i, "list": [
            {"id": j, "title": s["title"], "description": s["description"],
             "englishTitle": s["title"], "englishDescription": s["description"]}
            for j, s in enumerate(p["sections"], 1)]})
    return {"homeList": home, "detailList": detail}


def main():
    law_id = sys.argv[1]
    work = ROOT / "work" / law_id
    tree = json.loads((work / "web.json").read_text())
    fixes_file = work / "fixes.json"
    fixes = json.loads(fixes_file.read_text()) if fixes_file.exists() else {}
    out = build(tree, fixes)
    nsec = sum(len(d["list"]) for d in out["detailList"])
    assert out["homeList"] and len(out["homeList"]) == len(out["detailList"]), "parts do not match"
    path = ROOT / "data" / "text" / f"{law_id}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(out['homeList'])} parts, {nsec} sections, {len(fixes)} fixes -> {path}")


if __name__ == "__main__":
    main()
