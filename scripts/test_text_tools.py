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
