"""Page images and proofread chunks for one law.

  render <law-id>          PDF pages -> work/<id>/pages/p001.png ... (skips pages already there)
  split <law-id> [size]    web.json sections -> work/<id>/proof-N.json, about <size> (48) sections
                           each, with their PDF pages, for one proofread subagent per chunk
  merge <law-id>           proof-*-fixes.json -> fixes.json (stops if two chunks fix one section)

Usage: python3 scripts/proof_chunks.py <command> <law-id> [size]
"""
import json
import sys
from pathlib import Path

from check_text import pdf_lines, pdf_sections, web_sections

ROOT = Path(__file__).resolve().parent.parent
SCALE = 2.2  # about 1300 px wide for A4: small Nepali matras stay readable


def render(law_id):
    doc, _ = pdf_lines(law_id)  # also downloads law.pdf if missing
    out = ROOT / "work" / law_id / "pages"
    out.mkdir(exist_ok=True)
    for i in range(len(doc)):
        p = out / f"p{i + 1:03}.png"
        if not p.exists():
            doc[i].render(scale=SCALE).to_pil().save(p)
    print(f"{len(doc)} pages -> {out}")


def split(law_id, size=48):
    web = web_sections(law_id)
    _, lines = pdf_lines(law_id)
    pdf = pdf_sections(lines, [w["num"] for w in web])
    rows = [{"num": w["num"], "pages": pdf[w["num"]]["pages"] if w["num"] in pdf else [],
             "title": w["title"], "webText": w["text"]} for w in web]
    old = list((ROOT / "work" / law_id).glob("proof-*.json"))
    assert not old, f"proof files already exist in work/{law_id}; delete them to split again"
    chunks = [rows[i:i + size] for i in range(0, len(rows), size)]
    for n, c in enumerate(chunks, 1):
        (ROOT / "work" / law_id / f"proof-{n}.json").write_text(json.dumps(c, ensure_ascii=False, indent=1))
        pages = [p for r in c for p in r["pages"]]
        print(f"proof-{n}.json: {len(c)} sections, pages {min(pages, default='?')}-{max(pages, default='?')}")
    missing = [r["num"] for r in rows if not r["pages"]]
    if missing:
        print("no PDF pages found (read them by position):", ", ".join(missing))


def merge(law_id):
    work = ROOT / "work" / law_id
    fixes = {}
    for f in sorted(work.glob("proof-*-fixes.json")):
        for k, v in json.loads(f.read_text()).items():
            assert k not in fixes, f"section {k} fixed twice ({f.name})"
            fixes[k] = v
    (work / "fixes.json").write_text(json.dumps(fixes, ensure_ascii=False, indent=1))
    print(f"{len(fixes)} fixes -> {work / 'fixes.json'}")


if __name__ == "__main__":
    cmd, law_id = sys.argv[1], sys.argv[2]
    {"render": render, "split": lambda i: split(i, int(sys.argv[3]) if len(sys.argv) > 3 else 48),
     "merge": merge}[cmd](law_id)
