"""One-off global coverage expansion for LawfulStay.

Walks the world region-by-region and, for each country, asks the Anthropic API
(with web search) for the national STR framework plus the major regulated
cities/regions. Records are de-duplicated by geography and normalized through the
same helpers the daily monitor uses, so this is safe to re-run (idempotent).

Unlike the daily monitor, this does NOT write a changelog entry per record (that
would flood the "Latest changes" panel) — it adds one summary entry at the end.

Run on the droplet:
    set -a; . /etc/lawfulstay/monitor.env; set +a
    ./.venv/bin/python scripts/expand_coverage.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import monitor as M  # noqa: E402
from schema import (  # noqa: E402
    FIELDS, continent_for, load_changelog, load_jurisdictions, validate,
)

FIELD_KEYS = [k for k, _ in FIELDS]

# World coverage in small batches (<=4 countries) so each API response fits well
# within the output-token limit and stays valid JSON.
BATCHES: dict[str, list[str]] = {
    "UK & Ireland": ["United Kingdom", "Ireland"],
    "Western Europe": ["France", "Germany", "Netherlands", "Belgium"],
    "Alpine & Central Europe": ["Austria", "Switzerland", "Czechia", "Poland"],
    "Iberia & Italy": ["Spain", "Portugal", "Italy"],
    "Balkans & Mediterranean": ["Greece", "Croatia", "Malta", "Cyprus"],
    "Nordics": ["Denmark", "Sweden", "Norway", "Finland", "Iceland"],
    "Eastern Europe": ["Hungary", "Romania", "Bulgaria", "Estonia", "Lithuania"],
    "Japan & Korea": ["Japan", "South Korea"],
    "Greater China": ["China", "Taiwan", "Hong Kong"],
    "Southeast Asia 1": ["Thailand", "Singapore", "Malaysia"],
    "Southeast Asia 2": ["Indonesia", "Philippines", "Vietnam"],
    "South Asia": ["India", "Sri Lanka", "Maldives", "Nepal"],
    "Oceania": ["Australia", "New Zealand", "Fiji"],
    "Gulf States": ["United Arab Emirates", "Saudi Arabia", "Qatar"],
    "Middle East": ["Israel", "Turkey", "Jordan"],
    "North Africa": ["Morocco", "Egypt", "Tunisia"],
    "Sub-Saharan Africa": ["South Africa", "Kenya", "Nigeria", "Mauritius"],
    "Canada & Mexico": ["Canada", "Mexico"],
    "Caribbean 1": ["Bahamas", "Jamaica", "Dominican Republic"],
    "Caribbean 2": ["Barbados", "Aruba", "Puerto Rico"],
    "Central America": ["Costa Rica", "Panama", "Belize", "Guatemala"],
    "South America 1": ["Brazil", "Argentina", "Chile"],
    "South America 2": ["Colombia", "Peru", "Uruguay", "Ecuador"],
}


def batch_prompt(region_name: str, countries: list[str]) -> str:
    fl = ", ".join(FIELD_KEYS)
    clist = ", ".join(countries)
    return f"""You are building the LawfulStay global short-term-rental (STR) regulation database.
Today is {M.today()}. Use web search to research current STR / vacation-rental / holiday-let
regulation for this region: {region_name}.

For EACH of these countries: {clist}
Produce:
  1. ONE national-level record (set "city" to "Nationwide", "state" to "").
  2. Up to 2 of the most significant cities or regions that have their OWN distinct STR rules
     (only where they materially differ from the national baseline).
Keep each field concise (a short phrase, not a paragraph).

Favor authoritative sources (national/municipal law, official registries) and reputable
industry trackers. Do not invent specifics — use "Unknown" for any field you cannot source.

Return ONLY a JSON object: {{ "records": [ {{...}}, ... ] }}
Each record must include: "region" (always "International" here), "country", "state", "city",
and these 21 fields: {fl}.
"status" MUST be exactly one of: Active, Restricted, Banned, Pending, None."""


def salvage_records(text: str) -> list[dict]:
    """Extract as many complete record objects as possible from the model output,
    tolerating truncation or trailing prose. Finds the records array and decodes
    objects one at a time, stopping at the first incomplete one."""
    anchor = text.find('"records"')
    start = text.find("[", anchor if anchor != -1 else 0)
    if start == -1:
        return []
    dec = json.JSONDecoder()
    pos, n, out = start + 1, len(text), []
    while pos < n:
        while pos < n and text[pos] in " \t\r\n,":
            pos += 1
        if pos >= n or text[pos] == "]":
            break
        try:
            obj, pos = dec.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            out.append(obj)
    return out


def upsert(data: dict, rec: dict) -> str:
    """Add or fill-in a record by geography. Returns 'added' | 'filled' | 'skip'."""
    state = rec.get("state", "") or ""
    city = rec.get("city", "") or "Nationwide"
    country = rec.get("country", "") or "Unknown"
    existing = M.find_by_geo(data, state, city, country)
    if existing:
        # Only fill gaps — never overwrite curated/sourced values.
        filled = False
        for k in FIELD_KEYS:
            cur = str(existing.get(k, "")).strip().lower()
            new = rec.get(k)
            if cur in ("", "unknown") and new and str(new).strip().lower() not in ("", "unknown"):
                existing[k] = new
                filled = True
        if filled:
            existing["last_checked"] = M.today()
        return "filled" if filled else "skip"

    jid = M.make_id("International", state, city, country)
    if any(j["id"] == jid for j in data["jurisdictions"]):
        return "skip"
    record = {"id": jid, "region": "International",
              "continent": continent_for(country, "International"),
              "country": country, "last_checked": M.today(), "last_changed": M.today()}
    for k in FIELD_KEYS:
        record[k] = rec.get(k) or "Unknown"
    record["state"] = state   # leave blank for national records; UI falls back to country
    record["city"] = city
    record["status"] = M.normalize_status(record.get("status", ""))
    data["jurisdictions"].append(record)
    return "added"


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set.")

    data = load_jurisdictions()
    start_count = len(data["jurisdictions"])
    added = filled = 0

    for region_name, countries in BATCHES.items():
        print(f"[{M.today()}] {region_name}: {len(countries)} countries ...", flush=True)
        try:
            raw = M.call_anthropic(batch_prompt(region_name, countries), api_key,
                                   max_searches=8, max_tokens=16000)
            records = salvage_records(raw)
        except Exception as e:  # keep going on a bad batch
            print(f"  ! batch failed: {type(e).__name__}: {e}", flush=True)
            continue
        a = f = 0
        for rec in records:
            outcome = upsert(data, rec)
            if outcome == "added":
                a += 1; added += 1
            elif outcome == "filled":
                f += 1; filled += 1
        print(f"  -> {len(records)} records: {a} added, {f} filled", flush=True)
        # Persist after each batch so a crash doesn't lose progress.
        data["meta"]["last_full_refresh"] = M.today()
        (ROOT / "data" / "jurisdictions.json").write_text(json.dumps(data, indent=2) + "\n")
        time.sleep(2)

    # One summary changelog entry.
    if added:
        cl = load_changelog()
        cl["entries"].insert(0, {
            "date": M.today(),
            "jurisdiction_id": "coverage-expansion",
            "jurisdiction_label": "Global coverage expansion",
            "change_type": "new",
            "field": "multiple",
            "summary": f"Expanded global coverage: added {added} new jurisdictions "
                       f"(country baselines + major regulated cities across all regions).",
            "old_value": f"{start_count} jurisdictions",
            "new_value": f"{start_count + added} jurisdictions",
            "effective_date": M.today(),
            "source_url": "https://lawfulstay.com",
            "confidence": "medium",
        })
        (ROOT / "data" / "changelog.json").write_text(json.dumps(cl, indent=2) + "\n")

    print(f"\nDONE. {start_count} -> {len(data['jurisdictions'])} jurisdictions "
          f"({added} added, {filled} filled).", flush=True)

    problems = validate()
    if problems:
        print(f"validation issues ({len(problems)}):")
        for p in problems[:20]:
            print("  -", p)

    import build_digest  # noqa: E402
    import export_xlsx  # noqa: E402
    export_xlsx.main(ROOT / "web" / "Global_STR_Regulations_Comprehensive_Database.xlsx")
    for name in ("jurisdictions.json", "timeline.json"):
        (ROOT / "web" / name).write_text((ROOT / "data" / name).read_text())
    print("Rebuilt XLSX + synced web data.", flush=True)


if __name__ == "__main__":
    main()
