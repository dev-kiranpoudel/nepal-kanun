"""Copy new or changed official PDFs to our GitHub Release, so the app never depends on the gov CDN.

Run after a crawl (build_index.py) and before rebuilding the index (build_index.py --cached):
  python3 scripts/mirror_pdfs.py --dry-run   # list new and updated laws, change nothing
  python3 scripts/mirror_pdfs.py             # download, check, upload, record in mirrored.json
  python3 scripts/mirror_pdfs.py --prune     # first delete Release files replaced in an earlier run

A law needs copying when its official PDF link (scripts/raw.json, from the crawl) differs from
the one in scripts/mirrored.json: Law Commission gives every upload a new file name, so a new
link means a new file (usually an amendment). Each copy gets a name of its own (<law id>_<hash>.pdf)
so phones that saved the old version download the new one.

If a download fails (e.g. the gov CDN is down) the law keeps its previous copy and is retried next run.
Uploading needs `gh` logged in as an account with push access to the repo.
"""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
import zlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
RAW = SCRIPTS / "raw.json"
MIRRORED = SCRIPTS / "mirrored.json"
REPO = "dev-kiranpoudel/nepal-kanun"
TAG = "pdfs-v1"


def asset_name(law_id, official_url):
    """A Release file name unique to this official PDF, so a new version gets a new link."""
    return f"{law_id}_{zlib.crc32(official_url.encode()):08x}.pdf"


def asset_of(law_id, entry):
    # The first 731 copies (2026-11-07/08) were uploaded as <law id>.pdf.
    return entry.get("asset", f"{law_id}.pdf")


def pending(raw, mirrored):
    """(law id, official url, expected bytes, is_new) for every law whose official PDF we have not copied."""
    out, seen = [], set()
    for r in raw:
        law_id = f"lc-{r['contentId']}"
        if law_id in seen:
            continue
        seen.add(law_id)
        if mirrored.get(law_id, {}).get("pdf") != r["pdf"]:
            out.append((law_id, r["pdf"], r.get("pdfBytes"), law_id not in mirrored))
    return out


def download(url, expected):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nepal-kanun-mirror"})
            data = urllib.request.urlopen(req, timeout=120).read()
            break
        except Exception as e:
            error = e
            time.sleep(5 * (attempt + 1))
    else:
        raise error
    if data[:5] != b"%PDF-":
        raise ValueError("not a PDF")
    if expected and len(data) != expected:
        raise ValueError(f"incomplete: {len(data)} of {expected} bytes")
    return data


def gh(*args):
    return subprocess.run(["gh", *args, "--repo", REPO], check=True, capture_output=True, text=True).stdout


def self_check():
    a = asset_name("lc-1", "https://x/a.pdf")
    assert a == asset_name("lc-1", "https://x/a.pdf") and a != asset_name("lc-1", "https://x/b.pdf")
    assert a.startswith("lc-1_") and a.endswith(".pdf")
    assert asset_of("lc-1", {"pdf": "u"}) == "lc-1.pdf" and asset_of("lc-1", {"asset": a}) == a
    raw = [{"contentId": "1", "pdf": "old"}, {"contentId": "1", "pdf": "dup"}, {"contentId": "2", "pdf": "new"},
           {"contentId": "3", "pdf": "x"}]
    mirrored = {"lc-1": {"pdf": "old"}, "lc-2": {"pdf": "older"}}
    assert pending(raw, mirrored) == [("lc-2", "new", None, False), ("lc-3", "x", None, True)]


def main():
    self_check()
    dry, prune = "--dry-run" in sys.argv, "--prune" in sys.argv
    raw = json.loads(RAW.read_text())
    mirrored = json.loads(MIRRORED.read_text())
    if prune and not dry:
        # Before uploading, so only files replaced in an earlier run go: phones on the index pushed
        # before this run still ask for the files this run replaces.
        used = {asset_of(i, e) for i, e in mirrored.items()}
        assets = json.loads(gh("release", "view", TAG, "--json", "assets"))["assets"]
        for name in sorted(a["name"] for a in assets if a["name"] not in used):
            gh("release", "delete-asset", TAG, name, "--yes")
            print(f"  deleted unused {name}")
    todo = pending(raw, mirrored)
    print(f"{len(todo)} to copy: {sum(t[3] for t in todo)} new laws, {sum(not t[3] for t in todo)} updated")
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        for law_id, url, expected, is_new in todo:
            print(f"  {'new' if is_new else 'updated'} {law_id} {url}", flush=True)
            if dry:
                continue
            try:
                data = download(url, expected)
            except Exception as e:
                failed.append(law_id)
                print(f"    failed, keeps its previous copy: {e}")
                continue
            name = asset_name(law_id, url)
            path = Path(tmp) / name
            path.write_bytes(data)
            gh("release", "upload", TAG, str(path), "--clobber")
            mirrored[law_id] = {"pdf": url, "bytes": len(data), "source": "lawcommission.gov.np", "asset": name}
            # Save after each upload, so an interrupted run never loses a copy it made.
            MIRRORED.write_text(json.dumps(mirrored, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
            time.sleep(0.5)  # one at a time; the gov site drops bursts
    if failed:
        print(f"{len(failed)} failed (retry later): {' '.join(failed)}")
    if not dry:
        print("Next: build_index.py --cached, amended_dates.py, then build_index.py --cached again")


if __name__ == "__main__":
    main()
