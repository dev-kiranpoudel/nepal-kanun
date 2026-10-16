"""Build data/index.json (the law list the app downloads) from lawcommission.gov.np.

Usage:
  python3 scripts/build_index.py            # crawl, then build
  python3 scripts/build_index.py --cached   # rebuild from the last crawl (scripts/raw.json)

Also checks data/home.json against the new index. Commit and push data/ to publish.

shortcut: pdfUrl points at the official CDN; mirror the PDFs on our storage before release.
"""
import html
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "index.json"
RAW = Path(__file__).with_name("raw.json")
TITLES_EN = Path(__file__).with_name("titles_en.json")  # hand-written English titles, by law id
SITE = "https://lawcommission.gov.np"

# The 17 subject volumes (खण्ड) the Law Commission uses for both acts and regulations.
CATEGORIES = [
    (1, "संवैधानिक निकाय तथा सुशासन", "Constitutional Bodies and Good Governance", "governance"),
    (2, "अदालत तथा न्याय प्रशासन", "Courts and Justice", "court"),
    (3, "सङ्घीय संसद, राजनीतिक दल तथा निर्वाचन", "Parliament, Political Parties and Elections", "election"),
    (4, "आन्तरिक प्रशासन", "Internal Administration", "admin"),
    (5, "सुरक्षा प्रशासन", "Security", "security"),
    (6, "राजस्व तथा आर्थिक प्रशासन", "Revenue and Finance", "revenue"),
    (7, "मुद्रा, बैङ्किङ, बीमा, वित्तीय संस्था तथा धितोपत्र", "Banking, Insurance and Securities", "bank"),
    (8, "उद्योग, वाणिज्य तथा आपूर्ति", "Industry, Commerce and Supply", "industry"),
    (9, "पर्यटन, श्रम तथा यातायात", "Tourism, Labour and Transport", "labour"),
    (10, "सञ्चार तथा विज्ञान र प्रविधि", "Communication, Science and Technology", "communication"),
    (11, "योजना, विकास तथा निर्माण", "Planning, Development and Construction", "construction"),
    (12, "खाद्य, कृषि, सहकारी तथा भूमि प्रशासन", "Food, Agriculture, Cooperatives and Land", "agriculture"),
    (13, "वन, वातावरण तथा जलस्रोत", "Forest, Environment and Water", "environment"),
    (14, "परराष्ट्र, शिक्षा तथा खेलकुद", "Foreign Affairs, Education and Sports", "education"),
    (15, "स्वास्थ्य", "Health", "health"),
    (16, "महिला, बालबालिका, समाज कल्याण तथा संस्कृति", "Women, Children, Social Welfare and Culture", "family"),
    (17, "स्थानीय विकास", "Local Development", "local"),
]

TYPES = [
    ("constitution", "संविधान", "Constitution"),
    ("act", "ऐन", "Acts"),
    ("regulation", "नियमावली", "Regulations"),
    ("ordinance", "अध्यादेश", "Ordinances"),
    ("policy", "नीति", "Policies"),
]

# Listing pages to crawl: (type, volume or None, url)
ACT_VOLUME_IDS = [1762, 1763, 1764, 1765, 1766, 1767, 1768, 1769, 1783, 1784,
                  1785, 1786, 1787, 1788, 1789, 1790, 1791]
REGULATION_VOLUMES = {
    1: "volume-1-good-governance",
    7: "volume-7-banking-insurance-financial-institution-and-money-laundering",
    8: "volume-8-industry-corporate-and-import",
    10: "volume-10-information-and-communication",
    11: "volume-11-road-drinking-water-building-infrastructure",
    12: "volume-12-food-agriculture-cooperatives-and-land-administration",
    14: "volume-14-education-and-foreign-affair",
    15: "volume-15-regulation-health",
    16: "volume-16-women-children-and-culture",
    17: "volume-17-local-level",
}
SOURCES = (
    [("act", i + 1, f"{SITE}/category/{cid}/") for i, cid in enumerate(ACT_VOLUME_IDS)]
    + [("regulation", v, f"{SITE}/category/{slug}/") for v, slug in REGULATION_VOLUMES.items()]
    + [
        ("constitution", None, f"{SITE}/category/1807/"),
        ("act", None, f"{SITE}/category/2166/"),  # acts outside the volumes (Muluki codes etc.)
        ("act", None, f"{SITE}/category/2163/"),  # recent acts
        ("ordinance", None, f"{SITE}/category/1809/"),
        ("policy", None, f"{SITE}/category/1812/"),
    ]
)

BS_MONTHS = {"बैशाख": 1, "वैशाख": 1, "जेठ": 2, "असार": 3, "साउन": 4, "श्रावण": 4, "भदौ": 5,
             "असोज": 6, "कात्तिक": 7, "कार्तिक": 7, "मंसिर": 8, "पुस": 9, "पुष": 9, "पौष": 9, "माघ": 10,
             "फागुन": 11, "चैत": 12, "चैत्र": 12}
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def bs_date(published):
    """'भदौ २८, २०८१, शुक्रबार १३:२९' -> '2081-05-28' (Bikram Sambat)."""
    m = re.match(r"\s*(\S+)\s+([०-९\d]+),\s*([०-९\d]{4})", published)
    if not m or m.group(1) not in BS_MONTHS:
        return None
    day, year = int(m.group(2).translate(DIGITS)), int(m.group(3).translate(DIGITS))
    return f"{year:04d}-{BS_MONTHS[m.group(1)]:02d}-{day:02d}"


def year_from_title(title):
    years = re.findall(r"[०-९]{4}", title)
    return int(years[-1].translate(DIGITS)) if years else None


def get(url):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
        except Exception:
            time.sleep(2 + attempt * 3)
    return ""  # a page past the last one errors out; treated as the end of the list


def crawl_listing(url):
    rows = []
    for page in range(1, 30):
        text = get(f"{url}?page={page}")
        body = text[text.find("<tbody"):text.find("</tbody>")]
        added = 0
        for tr in re.findall(r"<tr>(.*?)</tr>", body, flags=re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
            pdf = re.search(r'href="([^"]+\.pdf)"', tr, flags=re.I)
            page_link = re.search(r'href="\s*(/content/(\d+)/[^"]*?)\s*"', tr)
            if len(tds) < 4 or not pdf or not page_link:
                continue
            row = {
                "title": html.unescape(re.sub(r"<[^>]+>", "", tds[1])).strip(),
                "published": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", tds[2]))).strip(),
                "pdf": pdf.group(1),
                "page": SITE + page_link.group(1),
                "contentId": page_link.group(2),
            }
            if row not in rows:
                rows.append(row)
                added += 1
        if not added:
            break
    return rows


def pdf_size(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            return int(urllib.request.urlopen(req, timeout=30).headers.get("Content-Length") or 0) or None
        except Exception:
            time.sleep(1 + attempt)
    return None


def crawl():
    with ThreadPoolExecutor(3) as pool:  # the site drops requests above ~3 at a time
        listings = list(pool.map(lambda s: crawl_listing(s[2]), SOURCES))
    raw = [dict(row, type=t, volume=v) for (t, v, _), rows in zip(SOURCES, listings) for row in rows]
    with ThreadPoolExecutor(6) as pool:
        for row, size in zip(raw, pool.map(lambda r: pdf_size(r["pdf"]), raw)):
            row["pdfBytes"] = size
    RAW.write_text(json.dumps(raw, ensure_ascii=False, indent=1))
    return raw


def build(raw):
    titles_en = json.loads(TITLES_EN.read_text())
    laws, seen = [], set()
    for r in raw:
        law_id = f"lc-{r['contentId']}"
        if law_id in seen:
            continue
        seen.add(law_id)
        laws.append({
            "id": law_id,
            "titleNe": r["title"],
            "titleEn": titles_en.get(law_id),
            "type": r["type"],
            "categoryId": f"v{r['volume']}" if r["volume"] else ("muluki" if r["title"].startswith("मुलुकी") else None),
            "yearBs": year_from_title(r["title"]),
            "status": "pdf",
            "pdfUrl": r["pdf"],
            "pdfBytes": r.get("pdfBytes"),
            "sourceUrl": r["page"],
            "publishedOnBs": bs_date(r["published"]),
            "textUrl": None,
            "amendedUpToBs": None,
            "version": 1,
        })
    categories = [{"id": "muluki", "nameNe": "मुलुकी ऐन (संहिता)", "nameEn": "Muluki Codes", "icon": "scale", "volume": None}]
    categories += [{"id": f"v{n}", "nameNe": name, "nameEn": name_en, "icon": icon, "volume": n} for n, name, name_en, icon in CATEGORIES]
    return {
        "schemaVersion": 1,
        "generatedOn": date.today().isoformat(),
        "source": SITE,
        "types": [{"id": i, "nameNe": ne, "nameEn": en} for i, ne, en in TYPES],
        "categories": categories,
        "laws": laws,
    }


def self_check(index):
    assert bs_date("भदौ २८, २०८१, शुक्रबार १३:२९") == "2081-05-28"
    assert bs_date("मंसिर १, २०२१, सोमबार ११:१५") == "2021-08-01"
    assert year_from_title("श्रम ऐन, २०७४") == 2074
    ids = [law["id"] for law in index["laws"]]
    assert len(ids) == len(set(ids)), "duplicate law ids"
    assert all(law["pdfUrl"] and law["publishedOnBs"] for law in index["laws"]), "law missing pdf or date"
    category_ids = {c["id"] for c in index["categories"]}
    assert all(law["categoryId"] in category_ids | {None} for law in index["laws"])
    home = json.loads((OUT.parent / "home.json").read_text())
    pinned = home["popular"] + [i for ids in home["personaPins"].values() for i in ids]
    missing = set(pinned) - set(ids)
    assert not missing, f"home.json names unknown laws: {missing}"
    assert set(home["featuredCategoryIds"]) <= category_ids
    for link in home["quickLinks"]:
        assert link.get("lawId") in ids or link.get("categoryId") in category_ids, f"bad quick link {link}"
    unknown = set(json.loads(TITLES_EN.read_text())) - set(ids)
    assert not unknown, f"titles_en.json names unknown laws: {unknown}"


if __name__ == "__main__":
    raw = json.loads(RAW.read_text()) if "--cached" in sys.argv else crawl()
    index = build(raw)
    self_check(index)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n")
    counts = {}
    for law in index["laws"]:
        counts[law["type"]] = counts.get(law["type"], 0) + 1
    print(f"{OUT.relative_to(ROOT)}: {len(index['laws'])} laws {counts}")
    untitled = [law["id"] for law in index["laws"] if not law["titleEn"]]
    if untitled:
        print(f"missing English title ({len(untitled)}), add to {TITLES_EN.name}: {' '.join(untitled)}")
