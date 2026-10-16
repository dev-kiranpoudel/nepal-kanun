# nepal-kanun

Data for the **नेपालको कानून** app (Android, `com.nepalkokanun.app`): a library of Nepal's acts, regulations, ordinances and policies.

The app downloads the files in `data/` once a day from:

```
https://raw.githubusercontent.com/dev-kiranpoudel/nepal-kanun/main/data/<file>
```

and keeps a bundled copy for the first launch and for when it is offline. A change pushed to `main` reaches users on their next app launch after the daily refresh, with no app update.

## Files

| File | What it is |
|---|---|
| `data/index.json` | Every law: id, Nepali and English title, type, subject, year, link to the official PDF, PDF size, status (`pdf` or `text`). |
| `data/home.json` | What the app's home screen shows: quick links, featured subjects, popular laws, suggested pins. |

Both files must stay valid JSON, and every law id named in `home.json` must exist in `index.json`. The app ignores a download that does not parse and keeps using its last good copy.

## Source

Law titles and PDFs come from the Nepal Law Commission (https://lawcommission.gov.np). This is not a government project; the Nepal Gazette is the authoritative text. English titles are unofficial translations.
