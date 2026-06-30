# STR Tracker — Monitoring Agent Runbook

This is the prompt the **scheduled cloud agent** runs each cycle (default: **daily**).
It is the "automation" engine. Its mission is to find **new, proposed, or modified**
short-term-rental regulations and restrictions **anywhere in the world** — at any
level (country, state/province, county, region, city, town, or village) — then
update the database, record a changelog, refresh the spreadsheet, and produce the
email digest + LinkedIn post draft.

Working directory: `/Users/williammason/Documents/str-tracker`

> **Scope reality:** there are tens of thousands of jurisdictions worldwide; a
> single daily run cannot enumerate every one. Instead each run does a global
> *discovery* sweep for what changed in the last ~48 hours (this is what surfaces
> brand-new jurisdictions), plus a rotating regional deep-dive, plus re-verification
> of stale tracked records. Breadth compounds over days and weeks.

## Each run, do exactly this

1. **Load the database.** Read `data/jurisdictions.json`. For each jurisdiction,
   note its `id`, label, current `status`, key fields, and `last_checked`. Build a
   set of existing `id`s and labels so you can de-duplicate before adding anything.

2. **Discovery sweep (global, every run).** Run broad, recency-focused searches to
   catch anything new/proposed/modified in the last ~48 hours, regardless of whether
   we already track that place. Use queries like:
   - `short-term rental regulation new OR proposed OR amended 2026`
   - `"vacation rental" OR Airbnb ordinance ban restriction this week`
   - `STR licensing rule change registry cap moratorium 2026`
   - `holiday let / villa rental law passed OR proposed 2026`
   Cast wide across countries and languages. Anything credible that we don't already
   track becomes a **new** jurisdiction record (step 4–5).

3. **Rotating regional deep-dive (focus by weekday).** In addition to the global
   sweep, do a deeper pass on one region per day so the whole world gets focused
   coverage each week:
   - **Mon** — United States & Canada (states, counties, cities, towns)
   - **Tue** — Europe & UK (national, regional, municipal)
   - **Wed** — Asia-Pacific (Japan, Australia, NZ, SE Asia, etc.)
   - **Thu** — Latin America & Caribbean
   - **Fri** — Africa & Middle East
   - **Sat/Sun** — Re-verify existing tracked records with the oldest `last_checked`
   For the day's region, search for newly enacted, proposed, or modified STR rules at
   national, state/province, county, and municipal levels — including small towns and
   villages where credible local reporting or an official notice exists.
   Favor primary/authoritative sources: government gazettes, council/ordinance pages,
   state/national bills, official registries, and reputable industry trackers
   (Rent Responsibly, iGMS, Awning, AirDNA). Ignore marketing blogs and listings.

3. **Apply updates** only when a credible source shows a *material* change to one
   of the 21 schema fields (see `scripts/schema.py` for the field list):
   - Update the changed field(s) in the jurisdiction record.
   - Set `last_changed` to today and `last_checked` to today.
   - For jurisdictions with no change, just set `last_checked` to today.
   - To add a brand-new jurisdiction, create a record with a kebab-case `id`
     (`us-<state>-<city>` or `intl-<country>-<city>`) and fill all 21 fields
     (use `"Unknown"` where a value can't be sourced).

4. **Record every change** by appending an entry to `data/changelog.json`
   (`entries`, newest first) with: `date` (today), `jurisdiction_id`,
   `jurisdiction_label`, `change_type` (new|update|status_change|repeal|proposed),
   `field`, `summary`, `old_value`, `new_value`, `effective_date`, `source_url`,
   and `confidence` (high|medium|low).

5. **Validate, export, build outputs:**
   ```bash
   python3 scripts/schema.py            # must print OK before continuing
   python3 scripts/export_xlsx.py       # refresh master spreadsheet
   cp data/jurisdictions.json web/jurisdictions.json   # sync web app data
   python3 scripts/build_digest.py --days 2            # email + LinkedIn drafts
   ```

6. **Deliver:**
   - **Email digest:** if this run recorded **one or more** changelog entries, email
     the contents of `out/digest_email.md` to `ericmason.co@gmail.com`
     (subject: `STR Tracker — Daily Digest <date>`). On a **quiet day with zero
     changes, do NOT send an email** (avoid daily inbox noise) — just finish the run.
     Exception: always send the digest on **Mondays** so Eric gets a confirmed
     weekly heartbeat even if the prior days were quiet.
   - **LinkedIn post:** present `out/linkedin_post.md` as a ready-to-post draft.
     Per Eric's posting rules, only frame items from the **past 24 hours** as
     "news"; older items are framed as "tracking" context. Do **not** auto-post —
     leave it as a draft for Eric to review.

## Guardrails
- Never invent regulations. If a source is ambiguous, set `confidence: "low"` and
  say so in the summary rather than overstating.
- Preserve existing data you can't re-verify — only overwrite on a credible source.
- Keep `last_full_refresh` in `jurisdictions.json` meta updated when a run touches
  the majority of jurisdictions.
- No emojis in any output (Eric's standing preference).

## ⚠️ RULE: Always use add_jurisdiction.py to add new jurisdictions

**NEVER** add a jurisdiction by hand-editing `data/jurisdictions.json` directly.

Always use `scripts/add_jurisdiction.py`. It atomically:
1. Adds the entry to the `jurisdictions` array
2. Prepends a `timeline` entry — which populates the "Recently Added" bar on the site
3. Validates required fields before writing
4. Deploys to the server

If adding jurisdictions programmatically (not interactively), call the helper
functions in the script directly rather than duplicating logic:

```python
from scripts.add_jurisdiction import validate, make_timeline_entry

# Then append to jurisdictions and insert(0, ...) on timeline manually
# but ALWAYS do both steps — never one without the other.
```

The invariant: **every jurisdiction in `jurisdictions[]` must have a corresponding
entry in `timeline[]`**. If you break this, the Recently Added bar silently drops
that city.
