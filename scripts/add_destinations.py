"""Add specific top travel/STR destinations missing from the database.

Researches each named destination's current STR regulations via the Anthropic API
(web search) and adds a structured record with authoritative geography. Idempotent:
skips destinations already present (by geography). Adds one changelog summary entry.

Run on the droplet:
    set -a; . /etc/lawfulstay/monitor.env; set +a
    ./.venv/bin/python scripts/add_destinations.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import monitor as M  # noqa: E402
from expand_coverage import salvage_records  # noqa: E402
from schema import FIELDS, continent_for, load_changelog, load_jurisdictions, validate  # noqa: E402

FIELD_KEYS = [k for k, _ in FIELDS]

# (city, state/region, country, region-flag)
DESTINATIONS = [
    ("Las Vegas", "Nevada", "United States", "US"),
    ("Orlando", "Florida", "United States", "US"),
    ("Aspen", "Colorado", "United States", "US"),
    ("Savannah", "Georgia", "United States", "US"),
    ("Charleston", "South Carolina", "United States", "US"),
    ("Gatlinburg", "Tennessee", "United States", "US"),
    ("South Lake Tahoe", "California", "United States", "US"),
    ("Myrtle Beach", "South Carolina", "United States", "US"),
    ("Park City", "Utah", "United States", "US"),
    ("Rome", "Lazio", "Italy", "International"),
    ("Venice", "Veneto", "Italy", "International"),
    ("Naples", "Campania", "Italy", "International"),
    ("Amalfi Coast", "Campania", "Italy", "International"),
    ("Seville", "Andalusia", "Spain", "International"),
    ("Palma de Mallorca", "Balearic Islands", "Spain", "International"),
    ("Ibiza", "Balearic Islands", "Spain", "International"),
    ("Nice", "Provence-Alpes-Cote d'Azur", "France", "International"),
    ("Cannes", "Provence-Alpes-Cote d'Azur", "France", "International"),
    ("Lyon", "Auvergne-Rhone-Alpes", "France", "International"),
    ("Santorini", "South Aegean", "Greece", "International"),
    ("Mykonos", "South Aegean", "Greece", "International"),
    ("Tulum", "Quintana Roo", "Mexico", "International"),
    ("Cabo San Lucas", "Baja California Sur", "Mexico", "International"),
    ("Puerto Vallarta", "Jalisco", "Mexico", "International"),
    ("Melbourne", "Victoria", "Australia", "International"),
    ("Gold Coast", "Queensland", "Australia", "International"),
    ("Vancouver", "British Columbia", "Canada", "International"),
    ("Montreal", "Quebec", "Canada", "International"),
    ("Cartagena", "Bolivar", "Colombia", "International"),
    ("Mumbai", "Maharashtra", "India", "International"),
    ("Osaka", "Osaka Prefecture", "Japan", "International"),
    ("Kuala Lumpur", "Federal Territory", "Malaysia", "International"),
    ("Cusco", "Cusco", "Peru", "International"),
    ("Algarve", "Faro", "Portugal", "International"),
    ("Zurich", "Zurich", "Switzerland", "International"),
    ("Zanzibar", "Zanzibar", "Tanzania", "International"),
    ("Pattaya", "Chonburi", "Thailand", "International"),
]


def nkey(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def batch_prompt(items):
    fl = ", ".join(FIELD_KEYS)
    lines = "\n".join(f"- {c}, {st}, {co}" for c, st, co, _ in items)
    return f"""You are building the LawfulStay short-term-rental (STR) regulation database.
Today is {M.today()}. Use web search to research the CURRENT STR / vacation-rental / holiday-let
regulations for each of these specific destinations:
{lines}

Favor authoritative sources (city/regional ordinances, official registries) and reputable industry
trackers. Keep each field concise. Do not invent specifics — use "Unknown" where you cannot source.

Return ONLY a JSON object: {{ "records": [ {{...}}, ... ] }}
One record per destination above, echoing "city" and "country" so it can be matched, plus these 21
fields: {fl}. "status" MUST be exactly one of: Active, Restricted, Banned, Pending, None."""


def add_list(items, label, desc):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set.")

    data = load_jurisdictions()
    start = len(data["jurisdictions"])
    added = 0

    # Skip ones already present by geography
    todo = [d for d in items if not M.find_by_geo(data, d[1], d[0], d[2])]
    print(f"{len(items)} candidates; {len(todo)} to add after dedup.", flush=True)

    for i in range(0, len(todo), 5):
        batch = todo[i:i + 5]
        labels = ", ".join(c for c, *_ in batch)
        print(f"Batch {i//5 + 1}: {labels} ...", flush=True)
        try:
            raw = M.call_anthropic(batch_prompt(batch), api_key, max_searches=8, max_tokens=16000)
            recs = salvage_records(raw)
        except Exception as e:
            print(f"  ! failed: {type(e).__name__}: {e}", flush=True)
            continue

        by_city = {nkey(r.get("city", "")): r for r in recs}
        for city, state, country, region in batch:
            r = by_city.get(nkey(city), {})
            jid = M.make_id(region, state, city, country)
            if any(j["id"] == jid for j in data["jurisdictions"]):
                continue
            rec = {"id": jid, "region": region,
                   "continent": continent_for(country, region),
                   "country": country, "state": state, "city": city,
                   "last_checked": M.today(), "last_changed": M.today()}
            for k in FIELD_KEYS:
                if k in ("state", "city"):
                    continue
                rec[k] = r.get(k) or "Unknown"
            rec["status"] = M.normalize_status(rec.get("status", ""))
            data["jurisdictions"].append(rec)
            added += 1
        print(f"  added so far: {added}", flush=True)
        data["meta"]["last_full_refresh"] = M.today()
        (ROOT / "data" / "jurisdictions.json").write_text(json.dumps(data, indent=2) + "\n")
        time.sleep(2)

    if added:
        cl = load_changelog()
        cl["entries"].insert(0, {
            "date": M.today(), "jurisdiction_id": label,
            "jurisdiction_label": desc,
            "change_type": "new", "field": "multiple",
            "summary": f"{desc} (added {added}).",
            "old_value": f"{start} jurisdictions", "new_value": f"{start + added} jurisdictions",
            "effective_date": M.today(), "source_url": "https://lawfulstay.com", "confidence": "medium",
        })
        (ROOT / "data" / "changelog.json").write_text(json.dumps(cl, indent=2) + "\n")

    print(f"\nDONE. {start} -> {len(data['jurisdictions'])} (+{added}).", flush=True)
    problems = validate()
    if problems:
        print(f"validation issues ({len(problems)}):", *problems[:10], sep="\n  ")

    import build_digest, export_xlsx  # noqa: E402
    export_xlsx.main(ROOT / "web" / "Global_STR_Regulations_Comprehensive_Database.xlsx")
    for name in ("jurisdictions.json", "policy_news.json"):
        (ROOT / "web" / name).write_text((ROOT / "data" / name).read_text())
    print("Rebuilt XLSX + synced web data.", flush=True)


def main():
    add_list(DESTINATIONS, "destinations-add",
             "Added top travel/vacation-rental destinations")


if __name__ == "__main__":
    main()
