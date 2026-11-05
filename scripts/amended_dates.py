"""Find each law's latest amendment date from page 1 of its PDF.

Law Commission PDFs open with a table of amending acts and their dates
(२०७६।०६।२४). The Nepali words in the text layer are garbled, but the digits are
clean, so the latest date in that table is the law's "amended up to" date.

Usage (needs `pip install pypdfium2`; run after build_index.py, then rerun build_index.py --cached):
  python3 scripts/amended_dates.py

Results are cached in scripts/amended.json by PDF URL, so a rerun only reads new or changed PDFs.
A law with no amendment table gets null (never amended, as far as its PDF says).
"""
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "index.json"
CACHE = Path(__file__).with_name("amended.json")
# Digits are sometimes a mix of Nepali and ASCII: २०83।03।25.
DATE = re.compile(r"([०-९0-9]{4})\s*।\s*([०-९0-9]{1,2})\s*।\s*([०-९0-9]{1,2})")
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
# The table ends where the law itself starts: "२०५० सालको ऐन नं. २", the preamble, or for
# regulations "... ऐनको दफा ७५ ले दिएको अधिकार प्रयोग गरी" and the first chapter.
TABLE_END = re.compile(r"सालको|प्रस्ताव|प्रयोग गरी|परिच्छेद|पररच्छेद")
AMENDED = re.compile(r"सं.ो[धि]")  # संशोधन, garbled as संशोधि, संिोधन or संशोिन


def amended_up_to(pages):
    """Latest date in the amendment table on the first pages, or None if the law lists no amendments."""
    head = ""
    for text in pages:
        head += text
        end = TABLE_END.search(head)
        if end:
            head = head[: end.start()]
            break
    if not AMENDED.search(head):
        return None
    dates = [tuple(int(x.translate(DIGITS)) for x in m) for m in DATE.findall(head)]
    dates = [d for d in dates if 1990 <= d[0] <= 2100 and 1 <= d[1] <= 12 and 1 <= d[2] <= 32]
    return "%04d-%02d-%02d" % max(dates) if dates else None


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=120).read()


def parse(data):
    import pypdfium2

    doc = pypdfium2.PdfDocument(data)
    return amended_up_to(doc[i].get_textpage().get_text_range() for i in range(min(2, len(doc))))


def self_check():
    civil_service = "संशोधि\n१. िेपाल स्वास््य सेवा ऐि, २०५३ २०५३।११।१५\n११. प्रशासकीय अदालत ऐि, २०७६ २०७६।०६।२४\n२०५० सालको ऐि िं. २\nयो ऐि संवत्२०६४"
    assert amended_up_to([civil_service]) == "2076-06-24"
    # Table continues onto page 2.
    assert amended_up_to(["संशोधन गनेऐन\n१. क ऐन २०३१।४।१८\n", "९. ख ऐन, २०७४ २०७४।६।३०\n२०१९ सालको ऐन नं. ४५"]) == "2074-06-30"
    # Never amended: only the act's own dates, no संशोध before the act starts.
    # Regulation: garbled संिोधि, mixed digits, table ends at "अनधकार प्रयोग गरी".
    reg = "प्रकाशित नमनत\n २०५०।0३।२८\nसंिोधि\n१६. क २०७६।0१।३०\n17. ख नियमावली, २०83 २०83।03।25\n ऐि, २०४९ को दफा ७५ लेददएको अनधकार प्रयोग गरी २०९०।१।१"
    assert amended_up_to([reg]) == "2083-03-25"
    assert amended_up_to(["संशोिन गने ऐन\n१. क ऐन, २०४५ २०४५।७।१०\n२०३५ सालको ऐन नं. २१"]) == "2045-07-10"
    assert amended_up_to(["लालमोहर र प्रकाशन मिति\n२०७५।६।२\n२०७५ सालको ऐन नं. १ ... संशोधन २०८०।१।१"]) is None


if __name__ == "__main__":
    self_check()
    laws = json.loads(INDEX.read_text())["laws"]
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [law for law in laws if cache.get(law["id"], {}).get("pdf") != law["pdfUrl"]]
    print(f"{len(todo)} PDFs to read, {len(laws) - len(todo)} cached")

    def work(law):
        try:
            return law, fetch(law["pdfUrl"]), None
        except Exception as e:  # keep going; a failed PDF is retried on the next run
            return law, None, e

    failed = 0
    # Downloads run in parallel; PDFium is not thread-safe, so parsing stays on this thread.
    with ThreadPoolExecutor(4) as pool:
        for n, (law, data, err) in enumerate(pool.map(work, todo), 1):
            try:
                if err:
                    raise err
                cache[law["id"]] = {"pdf": law["pdfUrl"], "amendedUpToBs": parse(data)}
            except Exception as e:
                failed += 1
                print(f"failed {law['id']}: {e}", file=sys.stderr)
            if n % 50 == 0:
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
                print(f"{n}/{len(todo)}", flush=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    dated = sum(1 for v in cache.values() if v["amendedUpToBs"])
    print(f"{CACHE.name}: {len(cache)} laws, {dated} with an amendment date, {failed} failed")
