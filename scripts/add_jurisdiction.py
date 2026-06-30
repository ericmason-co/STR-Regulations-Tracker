#!/usr/bin/env python3
"""
add_jurisdiction.py — Canonical way to add a new jurisdiction to LawfulStay.

Usage:
    python3 scripts/add_jurisdiction.py

The script will:
  1. Accept jurisdiction data (edit the NEW_JURISDICTION dict below)
  2. Validate required fields
  3. Add to data/jurisdictions.json  →  jurisdictions array
  4. Prepend to data/jurisdictions.json  →  timeline array  (Recently Added bar)
  5. Sync both server locations via SFTP
  6. Optionally git commit & push

NEVER add a jurisdiction by hand-editing jurisdictions.json — always use this
script so the timeline entry is always created and the Recently Added bar stays
in sync.
"""

import json
import sys
import os
import datetime
import paramiko

# ─────────────────────────────────────────────────────────────────────────────
# EDIT THIS BLOCK for each new jurisdiction
# ─────────────────────────────────────────────────────────────────────────────
NEW_JURISDICTION = {
    # Required — used as the unique key (format: us-state-city or country-city)
    "id": "us-fl-example-city",

    # Geographic info
    "region": "US",                   # "US", "Europe", "Middle East", etc.
    "country": "United States",
    "state": "Florida",               # State/province — leave "" if N/A
    "city": "Example City",
    "continent": "North America",     # North America / Europe / Asia / etc.

    # Regulation status
    "status": "Restricted",           # Active | Restricted | Banned | Pending | None

    # License
    "license_required": "Yes — city permit required",
    "tax_registration_required": "Yes",
    "fees": "Unknown",

    # Rules
    "primary_residence_required": "Unknown",
    "rental_day_cap": "Unknown",
    "occupancy_limit": "Unknown",
    "min_stay": "Unknown",
    "density_rules": "N/A",
    "insurance_required": "Unknown",
    "platform_obligations": "Unknown",

    # Tax
    "tax_rate": "Unknown",
    "zoning_restrictions": "Unknown",

    # Notes
    "compliance_notes": "Describe the main compliance requirements here.",
    "effective_date": "Unknown",
    "key_notes": "One-sentence summary for the detail modal.",
    "penalties": "Unknown",
    "additional_context": "",

    # Source — use the official government URL
    "source": "https://example.gov/str-regulations",
    "official_licenses": "https://example.gov/str-regulations",

    # Dates — use today's date for new entries
    "last_checked": str(datetime.date.today()),
    "last_changed": str(datetime.date.today()),

    "active_listings": None,
}

# Timeline entry — shown in the Recently Added bar
# Autofilled from NEW_JURISDICTION but you can override here
TIMELINE_SUMMARY = ""  # Leave "" to auto-generate from key_notes

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
DATA_FILE = "data/jurisdictions.json"
SERVER_HOST = "64.23.242.186"
SERVER_KEY = os.path.expanduser("~/.ssh/str_tracker_ed25519")
SERVER_PATHS = [
    "/opt/str-tracker/data/jurisdictions.json",
    "/opt/str-tracker/web/jurisdictions.json",
]

REQUIRED_FIELDS = ["id", "city", "country", "continent", "status",
                   "license_required", "source", "last_changed"]

STATUS_OPTIONS = {"Active", "Restricted", "Banned", "Pending", "None"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def validate(j: dict):
    errors = []
    for f in REQUIRED_FIELDS:
        if not j.get(f):
            errors.append(f"Missing required field: {f}")
    if j.get("status") not in STATUS_OPTIONS:
        errors.append(f"Invalid status '{j.get('status')}' — must be one of {STATUS_OPTIONS}")
    if errors:
        print("❌ Validation errors:")
        for e in errors:
            print(f"   • {e}")
        sys.exit(1)


def make_timeline_entry(j: dict, summary: str) -> dict:
    if not summary:
        summary = j.get("key_notes") or f"New entry added for {j['city']}, {j.get('state', j['country'])}."
    label = f"{j['city']}, {j.get('state') or j['country']}"
    return {
        "date": str(datetime.date.today()),
        "jurisdiction_id": j["id"],
        "jurisdiction_label": label,
        "change_type": "new_entry",
        "field": "multiple",
        "summary": summary,
        "old_value": "Not in database",
        "new_value": f"{j['status']} — {j.get('key_notes', '')}",
        "effective_date": j.get("effective_date", ""),
        "source_url": j.get("official_licenses") or j.get("source", ""),
        "confidence": "high",
    }


def deploy_to_server(local_path: str):
    print(f"\nConnecting to {SERVER_HOST}...")
    key = paramiko.Ed25519Key.from_private_key_file(SERVER_KEY)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SERVER_HOST, port=22, username="root", pkey=key, timeout=15)
    sftp = client.open_sftp()
    for remote in SERVER_PATHS:
        sftp.put(local_path, remote)
        print(f"  ✓ Deployed → {remote}")
    sftp.close()
    client.close()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  LawfulStay — Add Jurisdiction")
    print("=" * 60)

    # 1. Validate
    validate(NEW_JURISDICTION)
    print(f"\n✓ Validated: {NEW_JURISDICTION['city']}, "
          f"{NEW_JURISDICTION.get('state') or NEW_JURISDICTION['country']}")

    # 2. Load data
    with open(DATA_FILE) as f:
        data = json.load(f)

    jurisdictions = data["jurisdictions"]
    timeline = data["timeline"]

    # 3. Check for duplicates
    existing_ids = {j["id"] for j in jurisdictions}
    if NEW_JURISDICTION["id"] in existing_ids:
        print(f"⚠️  ID '{NEW_JURISDICTION['id']}' already exists — aborting.")
        sys.exit(1)

    # 4. Add jurisdiction
    jurisdictions.append(NEW_JURISDICTION)
    print(f"✓ Added to jurisdictions array (total: {len(jurisdictions)})")

    # 5. Add timeline entry (prepend — most recent first)
    entry = make_timeline_entry(NEW_JURISDICTION, TIMELINE_SUMMARY)
    timeline.insert(0, entry)
    print(f"✓ Prepended to timeline (total: {len(timeline)})")
    print(f"  Label: {entry['jurisdiction_label']}")

    # 6. Update meta
    data["meta"]["last_full_refresh"] = str(datetime.date.today())
    if "total_jurisdictions" in data["meta"]:
        data["meta"]["total_jurisdictions"] = len(jurisdictions)

    # 7. Write back
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✓ Saved {DATA_FILE}")

    # 8. Deploy to server
    deploy = input("\nDeploy to server now? [Y/n] ").strip().lower()
    if deploy in ("", "y", "yes"):
        deploy_to_server(DATA_FILE)
    else:
        print("Skipped server deploy — run the deploy script manually.")

    # 9. Git commit
    commit = input("\nGit commit & push? [Y/n] ").strip().lower()
    if commit in ("", "y", "yes"):
        city = NEW_JURISDICTION["city"]
        state = NEW_JURISDICTION.get("state") or NEW_JURISDICTION["country"]
        msg = f"Add {city}, {state}: {NEW_JURISDICTION['status']} — {NEW_JURISDICTION.get('key_notes', '')[:60]}"
        os.system(f'git add {DATA_FILE} && git commit -m "{msg}" && git push origin main')
    else:
        print("Skipped git commit.")

    print("\n✅ Done! Refresh lawfulstay.com to see the new entry in:")
    print("   • Regulations DB table")
    print("   • Recently Added bar (first pill)")


if __name__ == "__main__":
    main()
