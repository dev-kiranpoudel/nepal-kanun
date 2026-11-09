"""Find a law in data/index.json by name (Nepali, English or with any year style).

Usage: python3 scripts/find_law.py "श्रम ऐन २०७४"     -> prints matching ids, best first
Exit code 1 if nothing matches.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TO_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")


def words(s):
    s = (s or "").lower().translate(TO_ASCII).replace("‍", "")
    return set(re.findall(r"[\wऀ-ॿ]+", s)) - {"the", "of", "and", "act", "ऐन", "को"}


def score(query, law):
    q = words(query)
    title = words(law["titleNe"]) | words(law.get("titleEn"))
    if not q:
        return 0
    year = {w for w in q if w.isdigit() and len(w) == 4}
    q_words = q - year
    if not q_words:
        return 0
    hit = len(q_words & title) / len(q_words)  # the name decides; the year only breaks ties
    # BS = AD + 56 or 57, so "2017" also means 2073/2074.
    years = {str(int(y) + d) for y in year for d in (0, 56, 57)}
    if year and not years & title:
        hit *= 0.5  # wrong year: likely a different law of the same name
    return hit + (0.1 if law["type"] == "act" else 0)  # prefer the act over its regulation


def find(query, laws, n=5):
    ranked = sorted(((score(query, l), l) for l in laws), key=lambda x: -x[0])
    return [(round(s, 2), l) for s, l in ranked[:n] if s >= 0.75]


def main():
    laws = json.loads((ROOT / "data" / "index.json").read_text())["laws"]
    found = find(" ".join(sys.argv[1:]), laws)
    for s, l in found:  # a clear winner scores higher than the rest; a tie means ask the user
        print(f"{s}\t{l['id']}\t{l['type']}\t{l['titleNe']}\t{l.get('titleEn') or ''}\tamended {l.get('amendedUpToBs')}")
    sys.exit(0 if found else 1)


if __name__ == "__main__":
    main()
