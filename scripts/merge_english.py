"""Merge the official English and the subagents' fixes into work/<id>/en.json.

Usage: python3 scripts/merge_english.py <law-id>
Reads en/sources.json (labels), en/base.json (official English) and en/en-*-fixes.json.
Fails if a fix names an unknown section, or an updated/ai section has no fix.
"""
import json
import sys
from pathlib import Path

from english_sources import clean, en_num

ROOT = Path(__file__).resolve().parent.parent


def merge(labels, base, fixes):
    sections, chapters = {}, dict(base["chapters"])
    fixed = {}
    for f in fixes:
        for num, v in f.get("sections", {}).items():
            assert num in labels, f"fix for unknown section {num}"
            assert num not in fixed, f"two fixes for section {num}"
            fixed[num] = v
        chapters.update(f.get("chapters", {}))
    for num, label in labels.items():
        if label == "official":
            sections[num] = {**base["sections"][en_num(num)], "source": "official"}
        else:
            assert num in fixed, f"section {num} ({label}) has no English yet"
            sections[num] = {"title": clean(fixed[num]["title"]), "text": clean(fixed[num]["text"]), "source": label}
    kinds = {s["source"] for s in sections.values()}
    return {"from": base.get("source"),
            "englishSource": "official" if kinds == {"official"} else "ai" if kinds == {"ai"} else "mixed",
            "preamble": base.get("preamble", ""), "chapters": chapters, "sections": sections}


def main():
    law_id = sys.argv[1]
    en = ROOT / "work" / law_id / "en"
    labels = json.loads((en / "sources.json").read_text())["labels"]
    base = json.loads((en / "base.json").read_text())
    fixes = [json.loads(p.read_text()) for p in sorted(en.glob("en-*-fixes.json"))]
    out = merge(labels, base, fixes)
    (ROOT / "work" / law_id / "en.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    n = {k: sum(s["source"] == k for s in out["sections"].values()) for k in ("official", "updated", "ai")}
    print(f"{law_id}: {out['englishSource']} English, {n}, {len(out['chapters'])} chapter names")


if __name__ == "__main__":
    main()
