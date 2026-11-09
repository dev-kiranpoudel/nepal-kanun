"""Write batch files for the English subagents (only sections labelled updated or ai).

Usage: python3 scripts/prep_english.py <law-id> [--batches N]
Needs work/<id>/en/sources.json and base.json from english_sources.py.
Writes work/<id>/en/batch-N.json and renders the Nepali PDF pages those sections are on
into work/<id>/pages/pNNN.png. Batch 1 also carries chapter names that have no English.
"""
import json
import sys
from pathlib import Path

import check_text as ct
from english_sources import en_num, nepali_sections

ROOT = Path(__file__).resolve().parent.parent


def main():
    law_id = sys.argv[1]
    n = int(sys.argv[sys.argv.index("--batches") + 1]) if "--batches" in sys.argv else 3
    wd = ROOT / "work" / law_id
    labels = json.loads((wd / "en" / "sources.json").read_text())["labels"]
    base = json.loads((wd / "en" / "base.json").read_text())
    ne = nepali_sections(law_id)
    titles = {}
    text_file = ROOT / "data" / "text" / f"{law_id}.json"
    if text_file.exists():
        doc = json.loads(text_file.read_text())
        for d in doc["detailList"]:
            for s in d["list"]:
                titles[s["title"].split(".")[0]] = s["title"].split(".", 1)[-1].strip()
    _, lines = ct.pdf_lines(law_id)
    pages = {k: v["pages"] for k, v in ct.pdf_sections(lines, list(ne)).items()}

    items = []
    for num, label in labels.items():
        if label == "official":
            continue
        en = base["sections"].get(en_num(num))
        items.append({"num": num, "enNum": en_num(num), "label": label,
                      "nepaliTitle": titles.get(num, ""), "nepaliText": ne[num]["text"],
                      "officialEnglish": en, "pages": pages.get(num, [])})
    size = -(-len(items) // n)
    batches = [items[i * size:(i + 1) * size] for i in range(n) if items[i * size:(i + 1) * size]]

    # Chapter names with no English (e.g. a chapter an amendment added) go to batch 1.
    missing = []
    if text_file.exists():
        for h in doc["homeList"]:
            key = ct.norm(h["title"]).translate(str.maketrans(ct.DEV, "0123456789"))
            parts = [p.split("-")[-1] for p in key.replace(" ", "").split(",") if "-" in p]
            if len(parts) == 2:
                ck = f"{parts[0]}-{''.join({'क': 'A', 'ख': 'B'}.get(c, c) for c in parts[1])}"
                if ck not in base["chapters"]:
                    missing.append({"key": ck, "nepali": h["description"]})

    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(wd / "law.pdf"))
    (wd / "pages").mkdir(exist_ok=True)
    for i, b in enumerate(batches, 1):
        for it in b:
            for p in it["pages"]:
                f = wd / "pages" / f"p{p:03d}.png"
                if not f.exists():
                    pdf[p - 1].render(scale=2.2).to_pil().save(f)
        body = {"items": b, "missingChapters": missing if i == 1 else []}
        (wd / "en" / f"batch-{i}.json").write_text(json.dumps(body, ensure_ascii=False, indent=1))
        print(f"batch-{i}.json: {len(b)} sections ({b[0]['num']} - {b[-1]['num']})"
              + (f", {len(missing)} chapter names" if i == 1 and missing else ""))


if __name__ == "__main__":
    main()
