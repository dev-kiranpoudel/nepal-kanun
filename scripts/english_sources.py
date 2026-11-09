"""Score English versions of a law against its Nepali text and label every section.

Usage:
  python3 scripts/english_sources.py <law-id> <candidate> [<candidate> ...]
A candidate is a PDF path, or "nepallaws:<doc-id>" for an English tree on nepallaws.com.

For each candidate it splits the English into numbered sections and measures:
  coverage  share of the Nepali section numbers it has (१४६क = 146A),
  current   share of sections whose numbers (cross-references, clause numbers, dates)
            include every number in the current Nepali section.
The best candidate (coverage, then current) becomes the base, and each Nepali section is
labelled: official (use as is), updated (amended since, or numbers differ), ai (missing).
An exact match is a candidate with full coverage where every section is official.

Writes work/<id>/en/sources.json (the table and labels) and work/<id>/en/base.json
(the chosen English: preamble, chapter names, sections).
"""
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

import check_text as ct

ROOT = Path(__file__).resolve().parent.parent
LETTER = dict(zip("कखगघङ", "ABCDE"))
TO_ASCII = str.maketrans(ct.DEV, "0123456789")
CLAUSE_START = re.compile(r"^\s*(\(\w{1,4}\)|Provided\b|Explanation\b|Note\b)")


def en_num(ne):
    """"१४६क" -> "146A"."""
    m = re.match(f"({ct.NUM})(.*)", ne)
    return m.group(1).translate(TO_ASCII) + "".join(LETTER.get(c, c) for c in m.group(2))


def numbers(text):
    return collections.Counter(re.findall(r"\d+", ct.norm(text).translate(TO_ASCII)))


def clean(text):
    """PDF text marks a hyphen at a line break as U+FFFE ("sub\ufffesection"); make it a hyphen."""
    return text.replace("\ufffe", "-")


def paragraphs(lines):
    """Rejoin PDF-wrapped lines; a new paragraph starts at (1), (a), Provided, Explanation."""
    out = []
    for l in (l.strip() for l in lines):
        if not l:
            continue
        if not out or CLAUSE_START.match(l):
            out.append(l)
        else:
            out[-1] += ("" if out[-1].endswith("\ufffe") else " ") + l  # a word split by a hyphen
    return clean("\n".join(out))


# ---------- Nepali side ----------

def nepali_sections(law_id):
    """{num: {"text", "amended"}} from data/text/<id>.json if converted, else the PDF text layer."""
    text_file = ROOT / "data" / "text" / f"{law_id}.json"
    secs = {}
    if text_file.exists():
        for d in json.loads(text_file.read_text())["detailList"]:
            for s in d["list"]:
                m = re.match(f"({ct.NUM}[क-ह]?)\\.", s["title"])
                if m:
                    secs[m.group(1)] = {"text": s["description"], "amended": False}
        wanted = list(secs)
    else:
        wanted = [f"{n}{suf}".translate(str.maketrans("0123456789", ct.DEV))
                  for n in range(1, 1000) for suf in ("", "क", "ख", "ग")]
    _, lines = ct.pdf_lines(law_id)
    for num, p in ct.pdf_sections(lines, wanted).items():
        s = secs.setdefault(num, {"text": p["body"], "amended": False})
        s["amended"] = p["amended"]
    return dict(sorted(secs.items(), key=lambda kv: ct.sec_key(kv[0])))


# ---------- English side ----------

def parse_pdf_lines(lines, expected):
    """Split English lines into preamble, chapter names and sections (expected numbers only)."""
    heading = re.compile(r"^\s*(\d+[A-Z]?)\.\s+(.*)")
    part = re.compile(r"^\s*Part\s*[-–]?\s*(\d+)\s*$", re.I)
    # The official Penal Code PDF misspells it "Chpater" twice.
    chapter = re.compile(r"^\s*Ch(?:apter|pater)\s*[-–]?\s*(\d+[A-Z]?)\s*\.?\s*(.*)$", re.I)
    secs, chapters, preamble, cur, last = {}, {}, [], None, (0, "")
    cur_part, pending = None, None  # pending: a Part/Chapter heading waiting for its name line
    in_preamble = False
    for l in lines:
        s = l.strip()
        if not s or re.fullmatch(r"\d+|Revised", s):
            continue
        if pending:
            kind, key = pending
            chapters[key] = clean(s) if kind == "chapter" else chapters.get(key, clean(s))
            pending = None
            continue
        if m := part.match(s):
            cur_part, in_preamble = m.group(1), False
            pending = ("part", f"{cur_part}")
            continue
        if m := chapter.match(s):
            key = f"{cur_part}-{m.group(1)}"
            if m.group(2):
                chapters[key] = m.group(2)
            else:
                pending = ("chapter", key)
            continue
        if s.lower().startswith("preamble"):
            in_preamble = True
            preamble.append(s.split(":", 1)[-1])
            continue
        m = heading.match(s)
        if m and m.group(1) in expected and m.group(1) not in secs:
            k = ct.sec_key(m.group(1).translate(str.maketrans("0123456789", ct.DEV)))
            if k > last and k[0] - last[0] <= 3:
                cur = {"head": [m.group(2)], "lines": []}
                secs[m.group(1)] = cur
                last, in_preamble = k, False
                continue
        if in_preamble:
            preamble.append(s)
        elif cur is not None:
            # the title runs up to the first ":"; it can wrap over two or three lines
            if ":" not in " ".join(cur["head"]) and len(cur["head"]) < 3 and not cur["lines"]:
                cur["head"].append(s)
            else:
                cur["lines"].append(s)
    out = {}
    for num, c in secs.items():
        head = " ".join(c["head"])
        title, _, first = head.partition(":")
        out[num] = {"title": clean(title.strip()), "text": paragraphs([first] + c["lines"])}
    return {"preamble": paragraphs(preamble), "chapters": chapters, "sections": out}


def load_pdf(path, expected):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    lines = []
    for i in range(len(doc)):  # single-threaded: PDFium segfaults in threads
        lines += doc[i].get_textpage().get_text_range().replace("\r", "").split("\n")
    return parse_pdf_lines(lines, expected)


def load_nepallaws(doc_id, law_id, expected):
    import fetch_nepallaws as fn

    cache = ROOT / "work" / law_id / "en" / f"nepallaws-{doc_id}.json"
    if cache.exists():
        tree = json.loads(cache.read_text())
    else:
        root = fn.get(f"{fn.API}/{doc_id}?_fields=title")
        tree = fn.node(doc_id, root["title"]["rendered"], 0)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(tree, ensure_ascii=False))
    out = {"preamble": "", "chapters": {}, "sections": {}}

    def walk(n, part):
        t = n["title"]
        if m := re.match(r"Section\s*(\d+)\s*\(?([A-Za-z]?)\)?\s*[:.]?\s*(.*)", t):
            num = m.group(1) + m.group(2).upper()
            if num in expected and (n["text"].strip() or num not in out["sections"]):
                out["sections"][num] = {"title": m.group(3).strip(), "text": ct.fix_markers(n["text"])}
        elif t.lower().startswith("preamble"):
            out["preamble"] = n["text"]
        elif m := re.match(r"Part\s*[-–]?\s*(\d+)", t, re.I):
            part = m.group(1)
        elif m := re.match(r"Chapter\s*[-–]?\s*(\d+[A-Z]?)\.?\s*(.*)", t, re.I):
            out["chapters"][f"{part}-{m.group(1)}"] = m.group(2).strip()
        for c in n["children"]:
            walk(c, part)

    walk(tree, None)
    return out


# ---------- scoring ----------

def score(ne, en):
    nums = {k: en_num(k) for k in ne}
    have = [k for k in ne if nums[k] in en["sections"]]
    current = [k for k in have if not numbers(ne[k]["text"]) - numbers(en["sections"][nums[k]]["text"])]
    return {"coverage": round(len(have) / len(ne), 3), "current": round(len(current) / max(len(have), 1), 3),
            "sections": len(en["sections"]), "have": have, "currentSet": current}


def main():
    law_id, cands = sys.argv[1], sys.argv[2:]
    ne = nepali_sections(law_id)
    expected = {en_num(k) for k in ne}
    results, seen = [], {}
    for c in cands:
        if c.startswith("nepallaws:"):
            en = load_nepallaws(int(c.split(":")[1]), law_id, expected)
            digest = hashlib.sha1(json.dumps(en["sections"], sort_keys=True).encode()).hexdigest()
        else:
            digest = hashlib.sha1(Path(c).read_bytes()).hexdigest()
            if digest in seen:
                print(f"{c}: same file as {seen[digest]}, skipped")
                continue
            en = load_pdf(c, expected)
        seen[digest] = c
        results.append((c, en, score(ne, en)))

    results.sort(key=lambda r: (r[2]["coverage"], r[2]["current"]), reverse=True)
    print(f"{law_id}: {len(ne)} Nepali sections, {sum(s['amended'] for s in ne.values())} amended")
    print(f"{'candidate':60} {'sections':>8} {'coverage':>8} {'current':>8}")
    for c, en, s in results:
        print(f"{c[-60:]:60} {s['sections']:>8} {s['coverage']:>8} {s['current']:>8}")
    if not results:
        sys.exit("no candidates")

    best, base, s = results[0]
    labels = {}
    for k, v in ne.items():
        if k not in s["have"]:
            labels[k] = "ai"
        elif v["amended"] or k not in s["currentSet"]:
            labels[k] = "updated"
        else:
            labels[k] = "official"
    exact = all(l == "official" for l in labels.values())
    count = collections.Counter(labels.values())
    print(f"best: {best}; {'EXACT MATCH' if exact else 'not exact'}; {dict(count)}")

    out = ROOT / "work" / law_id / "en"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sources.json").write_text(json.dumps({
        "best": best, "exact": exact,
        "candidates": [{"source": c, **{k: v for k, v in s.items() if k not in ("have", "currentSet")}}
                       for c, _, s in results],
        "labels": labels}, ensure_ascii=False, indent=1))
    base["source"] = best
    (out / "base.json").write_text(json.dumps(base, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
