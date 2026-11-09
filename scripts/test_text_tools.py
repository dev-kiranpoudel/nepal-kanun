"""Self-check for the law-text helpers. Run: python3 scripts/test_text_tools.py"""
from check_text import SEC_TITLE, digits, fix_markers, sec_key
from to_app_json import build, split_heading


def num(title):
    m = SEC_TITLE.match(title)
    return m.group(1) + m.group(2)


assert num("दफा ३९: कसूरको गम्भीरता") == "३९"
assert num("दफा २२७ (क): मिलापत्र") == "२२७क"
assert num("दफा १९२क : तेजाब") == "१९२क"
assert num("दफा ५ः विशेष ऐन") == "५"
assert sorted(["९५", "८९", "१९२क", "१९२"], key=sec_key) == ["८९", "९५", "१९२", "१९२क"]
assert fix_markers("१) यस ऐनको\nक) अदालत\n(२) यो") == "(१) यस ऐनको\n(क) अदालत\n(२) यो"
assert digits("२०७9।03।31") == ["२०७९", "०३", "३१"]
assert split_heading("परिच्छेद-७क. आतङ्ककारी कार्य") == ("परिच्छेद-७क", "आतङ्ककारी कार्य")

# A placeholder (empty, same number) elsewhere in the tree is dropped; sections sort by number.
tree = {"title": "ऐन", "text": "", "children": [
    {"title": "भाग-१ सामान्य", "text": "", "children": [
        {"title": "परिच्छेद-१ क", "text": "", "children": [
            {"title": "दफा २: दुई", "text": "२ को पाठ", "children": []},
            {"title": "दफा १: एक", "text": "१) पहिलो\n(२) दोस्रो", "children": []},
            {"title": "दफा ३: तीन", "text": "", "children": []}]},
        {"title": "परिच्छेद-२ ख", "text": "", "children": [
            {"title": "दफा ३: तीन", "text": "३ को पाठ", "children": []}]}]}]}
out = build(tree, {"२": {"title": "दुई (सच्याइएको)"}})
assert [h["title"] for h in out["homeList"]] == ["भाग-१, परिच्छेद-१", "भाग-१, परिच्छेद-२"]
first = out["detailList"][0]["list"]
assert [s["title"] for s in first] == ["१. एक", "२. दुई (सच्याइएको)"]
assert first[0]["description"] == "(१) पहिलो\n\n(२) दोस्रो"
assert [s["title"] for s in out["detailList"][1]["list"]] == ["३. तीन"]
print("ok")

# ---- English ----
from english_sources import en_num, numbers, parse_pdf_lines
from merge_english import merge
from to_app_json import en_label

assert en_num("१४६क") == "146A" and en_num("२") == "2"
assert not numbers("(१) दफा १४६क र २७६") - numbers("(1) Sections 146A and 276")
assert numbers("(१) दफा १४६क") - numbers("(1) Section 167")  # a changed cross-reference shows up
assert en_label("भाग-२, परिच्छेद-७क") == ("Part-2, Chapter-7A", "2-7A")

pdf = """1
Revised
Preamble:
Whereas, it is expedient to provide
for a code;
Part -1
General Provisions
Chpater-1
Preliminary
1. Short title and commencement: (1) This Act may be
cited as the Code.
(2) It shall commence on 17 August 2018.
2
2. Extra-territorial application of
the Act: Any person who commits
(a) any offence,
Provided that this applies.
5. Unexpected: not a section we expect
""".split("\n")
p = parse_pdf_lines(pdf, {"1", "2"})
assert p["preamble"] == "Whereas, it is expedient to provide for a code;"
assert p["chapters"] == {"1": "General Provisions", "1-1": "Preliminary"}
assert p["sections"]["1"] == {"title": "Short title and commencement",
                              "text": "(1) This Act may be cited as the Code.\n(2) It shall commence on 17 August 2018."}
assert p["sections"]["2"]["title"] == "Extra-territorial application of the Act"
assert p["sections"]["2"]["text"].split("\n") == ["Any person who commits", "(a) any offence,",
                                                    "Provided that this applies. 5. Unexpected: not a section we expect"]

labels = {"१": "official", "२": "updated", "२क": "ai"}
base = {"source": "x.pdf", "preamble": "P", "chapters": {"1-1": "Preliminary"},
        "sections": {"1": {"title": "A", "text": "a"}, "2": {"title": "B", "text": "old"}}}
m = merge(labels, base, [{"sections": {"२": {"title": "B", "text": "new"}, "२क": {"title": "C", "text": "c"}},
                          "chapters": {"1-2": "More"}}])
assert m["englishSource"] == "mixed" and m["sections"]["२"]["text"] == "new" and m["chapters"]["1-2"] == "More"
try:
    merge(labels, base, [])
    raise SystemExit("merge should fail when an updated section has no English")
except AssertionError:
    pass

out = build(tree, {}, {"englishSource": "mixed", "preamble": "", "chapters": {"1-1": "Prelim"},
                       "sections": {"१": {"title": "One", "text": "(1) First", "source": "official"},
                                    "२": {"title": "Two", "text": "Second", "source": "ai"}}})
assert out["homeList"][0]["englishTitle"] == "Part-1, Chapter-1" and out["homeList"][0]["englishDescription"] == "Prelim"
assert out["detailList"][0]["list"][0]["englishTitle"] == "1. One"
assert out["detailList"][1]["list"][0]["englishTitle"] == "३. तीन"  # no English yet: mirrors the Nepali
assert out["nonOfficialEnglish"] == ["२"]
assert parse_pdf_lines(["1. Age: above seventy\ufffe", "five years, sub\ufffesection (1)"], {"1"})["sections"]["1"]["text"] \
    == "above seventy-five years, sub-section (1)"
print("english ok")
