"""Write data/text/<law-id>.json from work/<law-id>/web.json plus checked fixes.

Output is the Constitution's format (homeList + detailList) that the app's LawText.fromJson
reads. Each part is a परिच्छेद (with its भाग in the number), or any other group of sections;
the preamble and schedules become parts of their own.

Fixes: work/<law-id>/fixes.json maps a section number to its corrected text, or to
{"title": ..., "text": ...} (both optional), read from the official PDF. The PDF always wins.

English: if work/<law-id>/en.json exists (from merge_english.py), the English fields come from it
and the file records englishSource and nonOfficialEnglish (sections whose English is updated or
AI-translated). Otherwise the English fields mirror the Nepali: Sambidhan's reader has no fallback.

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


def en_label(number):
    """"भाग-२, परिच्छेद-७क" -> ("Part-2, Chapter-7A", "2-7A")."""
    d = norm(number).translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    d = "".join({"क": "A", "ख": "B", "ग": "C"}.get(c, c) for c in d)
    nums = re.findall(r"\d+[A-C]?", d)
    if "परिच्छेद" in number and len(nums) == 2:
        return f"Part-{nums[0]}, Chapter-{nums[1]}", f"{nums[0]}-{nums[1]}"
    if "परिच्छेद" in number and nums:
        return f"Chapter-{nums[-1]}", f"None-{nums[-1]}"
    if "अनुसूची" in number and nums:
        return f"Schedule-{nums[0]}", f"schedule-{nums[0]}"
    return number, ""


def build(tree, fixes, en=None):
    parts = []

    def section(n):
        m = SEC_TITLE.match(norm(n["title"]))
        num, title = m.group(1) + m.group(2), m.group(3).strip(" .:ः")
        fix = fixes.get(num, {})
        if isinstance(fix, str):
            fix = {"text": fix}
        title, text = fix.get("title", title), fix.get("text", n["text"])
        out = {"title": f"{num}. {title}", "description": body(text)}
        e = en and en["sections"].get(num)
        if e:
            from english_sources import en_num
            out.update(titleEn=f"{en_num(num)}. {e['title']}", descEn=body(e["text"]))
        return out

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
            part = {"number": number, "name": name, "sections": [section(k) for k in secs]}
            if en:
                part["numberEn"], key = en_label(number)
                part["nameEn"] = en["chapters"].get(key, name)
            parts.append(part)
        elif not kids and n is not tree:  # a leaf that isn't a section: preamble, schedule
            number, name = split_heading(n["title"])
            sec = {"title": name or n["title"], "description": body(n["text"])}
            part = {"number": number, "name": name or n["title"], "sections": [sec]}
            if en and norm(n["title"]).startswith("प्रस्तावना") and en.get("preamble"):
                part.update(numberEn="", nameEn="Preamble")
                sec.update(titleEn="Preamble", descEn=body(en["preamble"]))
            parts.append(part)
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
        # Without English, mirror the Nepali: Sambidhan's reader has no fallback.
        home.append({"id": i, "title": p["number"], "description": p["name"],
                     "englishTitle": p.get("numberEn", p["number"]), "englishDescription": p.get("nameEn", p["name"])})
        detail.append({"id": i, "list": [
            {"id": j, "title": s["title"], "description": s["description"],
             "englishTitle": s.get("titleEn", s["title"]), "englishDescription": s.get("descEn", s["description"])}
            for j, s in enumerate(p["sections"], 1)]})
    out = {"homeList": home, "detailList": detail}
    if en:
        out["englishSource"] = en["englishSource"]
        out["nonOfficialEnglish"] = sorted((k for k, v in en["sections"].items() if v["source"] != "official"),
                                           key=sec_key)
    return out


def main():
    law_id = sys.argv[1]
    work = ROOT / "work" / law_id
    tree = json.loads((work / "web.json").read_text())
    fixes_file = work / "fixes.json"
    fixes = json.loads(fixes_file.read_text()) if fixes_file.exists() else {}
    en_file = work / "en.json"
    en = json.loads(en_file.read_text()) if en_file.exists() else None
    out = build(tree, fixes, en)
    nsec = sum(len(d["list"]) for d in out["detailList"])
    assert out["homeList"] and len(out["homeList"]) == len(out["detailList"]), "parts do not match"
    path = ROOT / "data" / "text" / f"{law_id}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(out['homeList'])} parts, {nsec} sections, {len(fixes)} fixes, "
          f"English: {out.get('englishSource', 'mirrors Nepali')} -> {path}")


if __name__ == "__main__":
    main()
