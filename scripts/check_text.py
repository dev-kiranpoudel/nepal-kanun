"""Check a law's web text (work/<id>/web.json) against its official PDF.

The PDF text layer garbles Nepali letters (मलित for लिखत) but keeps digits and
numbered clauses intact, so per section (दफा) we compare:
  - the digits, in order (dates, amounts, cross-references, (१) clause numbers),
  - the number of clause lines ("(क)", "(१)" at line start),
  - the length (letters are swapped about one for one, so lengths stay close).
Sections that differ are written to work/<id>/flags.md with their PDF pages,
so they can be read from the page images and fixed.

Usage: python3 scripts/check_text.py <law-id>   (needs pypdfium2; reads work/<id>/law.pdf,
downloading it from index.json's pdfUrl if missing)
"""
import difflib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV = "०१२३४५६७८९"
TO_DEV = str.maketrans("0123456789", DEV)
NUM = f"[{DEV}]+"
SEC_TITLE = re.compile(rf"^दफा\s*({NUM})\s*\(?([क-ह]?)\)?\s*[:ःঃ।.]?\s*(.*)")
LENGTH_SLACK = 0.15
AMEND_MARK = re.compile("[\ue000-\uf8ff¥]")  # the PDF marks amended text with symbol-font glyphs
# Older PDFs (Civil Code) set the body in the Preeti font: ASCII in the text layer, "-!_" for "(१)".
# shortcut: maps only digits, clause brackets, visarga and the section letter, which is all the check reads;
# ASCII 0-9 are Preeti letters (ण ज्ञ द्द ...), so they become letters, not digits. Upgrade to a full
# Preeti converter if a law ever has to take its base text from such a PDF's text layer.
PREETI = str.maketrans({**dict(zip("!@#$%^&*()", "१२३४५६७८९०")), **dict(zip("0123456789", "णजदघदछटठडढ")),
                        "-": "(", "_": ")", "=": ".", ".": "।", "M": "ः"})


def preeti(line):
    if re.search("[\u0900-\u097f]", line):
        return line  # already Unicode (footnotes, some amended lines)
    line = line.translate(PREETI)
    return re.sub(r"([०-९])([svu])(?=\.)", lambda m: m.group(1) + "कखग"["svu".index(m.group(2))], line)


def norm(s):
    s = re.sub("[-]", "", s)  # footnote markers in private-use glyphs
    return s.translate(TO_DEV)


def fix_markers(text):
    """nepallaws writes some clause markers as "१)" or "क)"; the official text uses "(१)"."""
    return re.sub(r"(?m)^\s*([०-९]+|[क-ह]्?[क-ह]?)\)\s*", r"(\1) ", text)


def digits(s):
    return re.findall(NUM, norm(s))


def clause_lines(s):
    return sum(1 for l in s.split("\n") if re.match(r"\s*\(", l))


def sec_key(num):
    """"१९२क" -> (192, "क"), for sorting: nepallaws' menu_order is sometimes out of order."""
    m = re.match(f"({NUM})(.*)", num)
    return int(m.group(1).translate(str.maketrans(DEV, "0123456789"))), m.group(2)


def web_sections(law_id):
    """Flatten the nepallaws tree to [{num, title, text}] in reading order."""
    tree = json.loads((ROOT / "work" / law_id / "web.json").read_text())
    out = []

    def walk(n):
        m = SEC_TITLE.match(norm(n["title"]))
        if m:
            out.append({"num": m.group(1) + m.group(2), "title": m.group(3).strip(), "text": fix_markers(n["text"]), "webId": n["id"]})
        for c in n["children"]:
            walk(c)

    walk(tree)
    # nepallaws sometimes has an empty placeholder next to the real section with the same number.
    filled = {s["num"] for s in out if s["text"].strip()}
    out = [s for s in out if s["text"].strip() or s["num"] not in filled]
    return sorted(out, key=lambda s: sec_key(s["num"]))


def pdf_lines(law_id):
    """Every body line of the PDF as (page, text), without page headers and footnotes."""
    import pypdfium2 as pdfium

    pdf = ROOT / "work" / law_id / "law.pdf"
    if not pdf.exists():
        law = next(l for l in json.loads((ROOT / "data" / "index.json").read_text())["laws"] if l["id"] == law_id)
        pdf.write_bytes(urllib.request.urlopen(law["pdfUrl"], timeout=120).read())
    doc = pdfium.PdfDocument(str(pdf))
    lines = []
    for i in range(len(doc)):  # single-threaded: PDFium segfaults in threads
        page = doc[i].get_textpage().get_text_range().replace("\r", "").split("\n")
        # Footnotes sit under a line holding only spaces; they cite the amending act ("... द्वारा ...").
        cut = len(page)
        for j in range(len(page) - 1, -1, -1):
            if page[j] and not page[j].strip():
                if any("द्वारा" in l for l in page[j + 1:]):
                    cut = j
                break
        for l in page[:cut]:
            if "lawcommission.gov.np" in l or re.fullmatch(r"\s*\d+\s*", l) or not l.strip():
                continue
            lines.append((i + 1, preeti(l)))
    return doc, lines


def pdf_sections(lines, wanted):
    """Split PDF lines into sections, accepting a heading only if it is the next expected दफा."""
    secs, cur, last, wanted_set = {}, None, (0, ""), set(wanted)
    # Some headings lose their dot ("३७ िदम्र्ाद"); only the next expected number counts, so that's safe.
    heading = re.compile(rf"^\s*({NUM}[क-ह]?)\s*\.?\s+(.*)")
    # Page 1 lists the amending acts as "१. ...", so sections start after the preamble.
    start = next((i for i, (_, l) in enumerate(lines) if re.search("प्रस्ता[िव]न|k\\|:tfjgf", l)), 0)
    lines = lines[start:]
    chapter = re.compile(r"^\s*(िाग|भाग|पररच्छेद|परिच्छेद|efu|kl/R5]b)\s*[-–]?\s*[०-९]")
    skip_next = False
    for page, raw in lines:
        l = norm(raw)
        if skip_next:  # the chapter's name, on the line after "पररच्छेद-२"
            skip_next = False
            continue
        if chapter.match(l):
            skip_next = True
            continue
        m = heading.match(l)
        # A heading must be a section we expect, after the last one and at most 3 ahead
        # (the web text can miss or mislabel a section); cross-references rarely fit that.
        if m and m.group(1) in wanted_set and m.group(1) not in secs:
            k = sec_key(m.group(1))
            if k > last and k[0] - last[0] <= 3:
                cur = {"num": m.group(1), "pages": [page], "lines": [m.group(2)], "amended": bool(AMEND_MARK.search(raw))}
                secs[cur["num"]] = cur
                last = k
                continue
        if cur:
            cur["lines"].append(l)
            cur["amended"] = cur["amended"] or bool(AMEND_MARK.search(raw))
            if page not in cur["pages"]:
                cur["pages"].append(page)
    for s in secs.values():
        body = "\n".join(s["lines"])
        head = "\n".join(s["lines"][:3])  # the title can wrap, so its "ः" may be on a later line
        s["body"] = body.split("ः", 1)[1] if "ः" in head else body  # drop the title
    return secs


def main():
    law_id = sys.argv[1]
    web = web_sections(law_id)
    _, lines = pdf_lines(law_id)
    pdf = pdf_sections(lines, [w["num"] for w in web])
    flags = []
    seen = set()
    for w in web:
        if w["num"] in seen:
            flags.append((w, pdf.get(w["num"]), ["duplicate section number on nepallaws"]))
            continue
        seen.add(w["num"])
        p = pdf.get(w["num"])
        if not p:
            flags.append((w, None, ["not found in PDF"]))
            continue
        why = []
        wd, pd = digits(w["text"]), digits(p["body"])
        if wd != pd:
            diff = [d for d in difflib.ndiff(wd, pd) if d[0] in "+-"]
            why.append("digits differ: " + " ".join(diff[:12]))
        if clause_lines(w["text"]) != clause_lines(p["body"]):
            why.append(f"clause lines web {clause_lines(w['text'])} vs PDF {clause_lines(p['body'])}")
        lw, lp = len(re.sub(r"\s", "", w["text"])), len(re.sub(r"\s", "", p["body"]))
        if lp and abs(lw - lp) / lp > LENGTH_SLACK:
            why.append(f"length web {lw} vs PDF {lp}")
        if why:
            flags.append((w, p, why))

    out = ROOT / "work" / law_id / "flags.md"
    with out.open("w") as f:
        f.write(f"# {law_id}: {len(flags)} of {len(web)} sections flagged ({len(pdf)} found in PDF)\n\n")
        for w, p, why in flags:
            pages = ",".join(map(str, p["pages"])) if p else "?"
            f.write(f"## दफा {w['num']} {w['title']} (PDF pages {pages}, web {w['webId']})\n")
            for y in why:
                f.write(f"- {y}\n")
            f.write("\n")
    print(f"{len(web)} web sections, {len(pdf)} matched in PDF, {len(flags)} flagged -> {out}")


if __name__ == "__main__":
    main()
