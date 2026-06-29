"""Schema definition and validation for the Global STR Regulation Tracker.

Single source of truth for the 21-field jurisdiction schema. Used by the export
script, the digest builder, and the monitor agent to validate data before it is
written back to data/jurisdictions.json.

Run directly to validate the current data files:
    python3 scripts/schema.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JURISDICTIONS_FILE = DATA_DIR / "jurisdictions.json"
CHANGELOG_FILE = DATA_DIR / "policy_news.json"

# The 21 fields, in canonical order, mapped to their spreadsheet column headers.
# Order here drives the column order in the exported XLSX.
FIELDS = [
    ("state", "State"),
    ("city", "City/Jurisdiction"),
    ("status", "Regulatory Status"),
    ("license_required", "License/Registration Required"),
    ("tax_registration_required", "Tax Registration Required"),
    ("fees", "Fees"),
    ("primary_residence_required", "Primary Residence Required"),
    ("rental_day_cap", "Annual Rental Day Cap"),
    ("occupancy_limit", "Occupancy Limit"),
    ("tax_rate", "Tax Rate"),
    ("zoning_restrictions", "Zoning Restrictions"),
    ("min_stay", "Minimum Stay Requirement"),
    ("density_rules", "Density/Spacing Rules"),
    ("insurance_required", "Insurance Required"),
    ("platform_obligations", "Platform Obligations"),
    ("compliance_notes", "Compliance Notes"),
    ("effective_date", "Effective Date / Last Updated"),
    ("key_notes", "Key Notes"),
    ("penalties", "Penalties"),
    ("additional_context", "Additional Context"),
    ("source", "Source"),
]

# Bookkeeping fields the tracker adds on top of the 21 content fields.
META_FIELDS = ["id", "region", "continent", "country", "last_checked", "last_changed"]

# Continent / world-region grouping for filtering. Broader than country, finer
# than the US/International "region" flag (which the monitor still uses internally).
CONTINENTS = [
    "North America", "Central America & Caribbean", "South America",
    "Europe", "Africa", "Middle East", "Asia", "Oceania",
]
_CONTINENT_BY_COUNTRY = {
    # North America
    "United States": "North America", "Canada": "North America", "Mexico": "North America",
    # Central America & Caribbean
    "Belize": "Central America & Caribbean", "Costa Rica": "Central America & Caribbean",
    "Guatemala": "Central America & Caribbean", "Panama": "Central America & Caribbean",
    "Bahamas": "Central America & Caribbean", "Barbados": "Central America & Caribbean",
    "Aruba": "Central America & Caribbean", "Jamaica": "Central America & Caribbean",
    "Dominican Republic": "Central America & Caribbean", "Puerto Rico": "Central America & Caribbean",
    # South America
    "Argentina": "South America", "Brazil": "South America", "Chile": "South America",
    "Colombia": "South America", "Ecuador": "South America", "Peru": "South America",
    "Uruguay": "South America",
    # Europe
    "Austria": "Europe", "Belgium": "Europe", "Bulgaria": "Europe", "Croatia": "Europe",
    "Cyprus": "Europe", "Czechia": "Europe", "Denmark": "Europe", "Estonia": "Europe",
    "European Union": "Europe", "Finland": "Europe", "France": "Europe", "Germany": "Europe",
    "Greece": "Europe", "Hungary": "Europe", "Iceland": "Europe", "Ireland": "Europe",
    "Italy": "Europe", "Lithuania": "Europe", "Malta": "Europe", "Netherlands": "Europe",
    "Norway": "Europe", "Poland": "Europe", "Portugal": "Europe", "Romania": "Europe",
    "Spain": "Europe", "Sweden": "Europe", "Switzerland": "Europe", "United Kingdom": "Europe",
    # Africa
    "Egypt": "Africa", "Kenya": "Africa", "Mauritius": "Africa", "Morocco": "Africa",
    "Nigeria": "Africa", "South Africa": "Africa", "Tunisia": "Africa",
    # Middle East
    "Israel": "Middle East", "Jordan": "Middle East", "Qatar": "Middle East",
    "Saudi Arabia": "Middle East", "Turkey": "Middle East", "United Arab Emirates": "Middle East",
    # Asia
    "China": "Asia", "Hong Kong": "Asia", "India": "Asia", "Indonesia": "Asia", "Japan": "Asia",
    "Malaysia": "Asia", "Maldives": "Asia", "Nepal": "Asia", "Philippines": "Asia",
    "Singapore": "Asia", "South Korea": "Asia", "Sri Lanka": "Asia", "Taiwan": "Asia",
    "Thailand": "Asia", "Vietnam": "Asia",
    # Oceania
    "Australia": "Oceania", "New Zealand": "Oceania", "Fiji": "Oceania",
}


def continent_for(country: str, region: str = "") -> str:
    """Map a country (or US region) to its continent/world-region bucket."""
    if region == "US":
        return "North America"
    return _CONTINENT_BY_COUNTRY.get((country or "").strip(), "Other")

VALID_STATUSES = {"Active", "Restricted", "Banned", "Pending", "None"}
VALID_CHANGE_TYPES = {"new", "update", "status_change", "repeal", "proposed"}


def load_jurisdictions() -> dict:
    return json.loads(JURISDICTIONS_FILE.read_text())


def load_changelog() -> dict:
    return json.loads(CHANGELOG_FILE.read_text())


def validate() -> list[str]:
    """Return a list of validation problems. Empty list means the data is clean."""
    problems: list[str] = []
    field_keys = {key for key, _ in FIELDS}

    data = load_jurisdictions()
    seen_ids: set[str] = set()
    for i, j in enumerate(data.get("jurisdictions", [])):
        label = j.get("id") or f"index {i}"
        if not j.get("id"):
            problems.append(f"[{label}] missing 'id'")
        elif j["id"] in seen_ids:
            problems.append(f"[{label}] duplicate id")
        else:
            seen_ids.add(j["id"])

        for key in field_keys:
            if key not in j:
                problems.append(f"[{label}] missing field '{key}'")
        for key in META_FIELDS:
            if key not in j:
                problems.append(f"[{label}] missing meta field '{key}'")

        status = j.get("status")
        if status and status not in VALID_STATUSES:
            problems.append(
                f"[{label}] status '{status}' not in {sorted(VALID_STATUSES)}"
            )

    changelog = load_changelog()
    for i, e in enumerate(changelog.get("entries", [])):
        ct = e.get("change_type")
        if ct and ct not in VALID_CHANGE_TYPES:
            problems.append(
                f"[changelog #{i}] change_type '{ct}' not in {sorted(VALID_CHANGE_TYPES)}"
            )
    return problems


if __name__ == "__main__":
    issues = validate()
    if issues:
        print(f"FAILED validation with {len(issues)} issue(s):")
        for issue in issues:
            print("  -", issue)
        sys.exit(1)
    j = load_jurisdictions()
    print(f"OK: {len(j['jurisdictions'])} jurisdictions, schema valid.")
