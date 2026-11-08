# nepal-kanun

Data for the **नेपालको कानून** app (Android, `com.nepalkokanun.app`): a library of Nepal's acts, regulations, ordinances and policies.

The app downloads the files in `data/` once a day from:

```
https://raw.githubusercontent.com/dev-kiranpoudel/nepal-kanun/main/data/<file>
```

and keeps the last good download on the phone, so it works offline after its first launch (which needs internet). The app ships with no copy of this data. A change pushed to `main` reaches users on their next app launch after the daily refresh, with no app update.

## Files

| File | What it is |
|---|---|
| `data/index.json` | Every law: id, Nepali and English title, type, subject, year, `pdfUrl` (our copy of the PDF), `officialPdfUrl` (the Law Commission link), PDF size, status (`pdf` or `text`). |
| `data/home.json` | What the app's home screen shows: quick links, featured subjects, popular laws, suggested pins. |

Both files must stay valid JSON, and every law id named in `home.json` must exist in `index.json`. The app ignores a download that does not parse and keeps using its last good copy.

## Source

Law titles and PDFs come from the Nepal Law Commission (https://lawcommission.gov.np). This is not a government project; the Nepal Gazette is the authoritative text. English titles are unofficial translations.

The app downloads PDFs from our copies in the GitHub Release [`pdfs-v1`](https://github.com/dev-kiranpoudel/nepal-kanun/releases/tag/pdfs-v1), not from the government file server (giwmscdnone.gov.np), which went down on 2026-11-07. `scripts/mirrored.json` records, for each law, the official link its copy stands in for, the size, and where it came from: `lawcommission.gov.np` and `web.archive.org` are byte-for-byte copies of the official file; `moljpa.gov.np` copies are the Ministry of Law's edition, checked to carry the same amendments.

## Updating the data

```
python3 scripts/build_index.py            # 1. crawl the Law Commission site (~5 min)
python3 scripts/mirror_pdfs.py --dry-run  # 2. see which laws are new or have a new PDF (amended)
python3 scripts/mirror_pdfs.py            # 3. copy those PDFs to the Release (gh must have push access)
python3 scripts/build_index.py --cached   # 4. point those laws at their new copies
python3 scripts/amended_dates.py          # 5. read the new PDFs' "amended up to" dates (needs pypdfium2)
python3 scripts/build_index.py --cached   # 6. write the dates into data/index.json
```

Commit and push only after step 3 has uploaded the files, or the app gets links to files that do not exist yet. A law whose download failed in step 3 keeps its previous copy; run step 3 again later. `--prune` (step 3) first deletes Release files that an earlier run replaced, so the Release stays under its 1000-file limit; files replaced in the current run stay until the next run, because phones on yesterday's index still ask for them.

The weekly GitHub Action (`.github/workflows/update-laws.yml`, Sundays, or run it from the Actions tab) does all six steps, commits and pushes if anything changed, and opens an issue listing new and updated laws. If the crawl looks incomplete (more than 2% fewer laws) or a check fails, the run fails without pushing and GitHub emails the repo owner.

- English titles: edit `scripts/titles_en.json` (law id to title). After a crawl the script lists new laws that still need one.
- Home screen: edit `data/home.json`; the script checks that every id in it exists.
- The script checks its output before writing. Commit and push `data/` and `scripts/mirrored.json` to publish.
