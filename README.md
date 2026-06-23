# Global STR Regulation Tracker

A self-updating database of short-term rental (STR) regulations across jurisdictions
worldwide. Owned by Eric Mason / VRInsider / the VRP Group (21K members).

This repo turns the old Word + Excel tracker into a maintainable pipeline:
**one structured data file → spreadsheet, searchable web app, and an automated
weekly monitor that detects regulatory changes and drafts an email digest +
LinkedIn post.**

## Architecture

```
data/jurisdictions.json   Single source of truth (21-field schema per jurisdiction)
data/changelog.json       Append-only history of detected changes
scripts/schema.py         Schema definition + validation (run to check data)
scripts/export_xlsx.py    JSON  -> master spreadsheet (3 sheets + changelog)
scripts/build_digest.py   changelog -> out/digest_email.md + out/linkedin_post.md
web/                      Static searchable/filterable site (Vercel-deployable)
AGENT.md                  Runbook the scheduled monitor agent follows each cycle
vercel.json               Build config: rebuilds XLSX + syncs data on deploy
```

The 21 content fields plus bookkeeping (`id`, `region`, `country`, `last_checked`,
`last_changed`) are defined once in `scripts/schema.py` and reused everywhere.

## Setup

```bash
pip3 install openpyxl        # only dependency
```

## Common commands

```bash
python3 scripts/schema.py                 # validate the database
python3 scripts/export_xlsx.py            # rebuild the master XLSX
python3 scripts/build_digest.py --days 7  # build email digest + LinkedIn draft
cp data/jurisdictions.json web/           # sync data into the web app
```

## Run the web app locally

```bash
cd web && python3 -m http.server 8000     # then open http://localhost:8000
```

Deploy to Vercel by pointing it at this repo — `vercel.json` rebuilds the
spreadsheet and syncs the data file into `web/` at deploy time.

## The automation

A **scheduled cloud agent** runs `AGENT.md` weekly. Each cycle it:
1. web-searches every tracked jurisdiction for regulatory changes,
2. updates `jurisdictions.json` and appends to `changelog.json`,
3. validates, rebuilds the XLSX, and syncs the web data,
4. emails the digest to `ericmason.co@gmail.com`, and
5. drafts a VRP-Group-ready LinkedIn post (review before posting).

To change cadence or pause it, edit the scheduled task (see the schedule skill /
routines). The runbook in `AGENT.md` is the contract for what each run does.

## Data coverage

Seeded from the December 2025 master spreadsheet — currently 33 structured
jurisdictions (24 US, 9 international) with the most detail, expanding toward the
full 240+ as the monitor runs. Add jurisdictions by following the `id` and field
conventions in `AGENT.md`.
