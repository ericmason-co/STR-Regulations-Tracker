"""One-off QA audit of jurisdictions.json for formatting anomalies."""
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
js = json.loads((ROOT / "data" / "jurisdictions.json").read_text())["jurisdictions"]

FIELDS = ["status", "license_required", "tax_registration_required", "fees",
          "primary_residence_required", "rental_day_cap", "occupancy_limit", "tax_rate",
          "zoning_restrictions", "min_stay", "density_rules", "insurance_required",
          "platform_obligations", "compliance_notes", "effective_date", "key_notes",
          "penalties", "additional_context", "source"]


def lab(j):
    return f"{j['city']}/{j['country']}"


print("=== 1. Unknown-heavy records (>12 of 19 fields Unknown) ===")
heavy = []
for j in js:
    u = sum(1 for f in FIELDS if str(j.get(f, "")).strip() in ("", "Unknown"))
    if u > 12:
        heavy.append((u, lab(j)))
for u, l in sorted(heavy, reverse=True)[:15]:
    print(f"  {u}/19 Unknown: {l}")
print(f"  total Unknown-heavy: {len(heavy)}")

print("\n=== 2. Overly long field values (>200 chars) ===")
longs = 0
for j in js:
    for f in FIELDS:
        v = str(j.get(f, ""))
        if len(v) > 200:
            longs += 1
            if longs <= 8:
                print(f"  {len(v)}ch {lab(j)} [{f}]: {v[:80]}...")
print(f"  total >200ch values: {longs}")

print("\n=== 3. Whitespace / lowercase-yesno anomalies ===")
anom = 0
for j in js:
    for f in FIELDS + ["city", "state", "country"]:
        v = j.get(f, "")
        if isinstance(v, str) and (v != v.strip() or "  " in v or v in ("none", "n/a", "yes", "no")):
            anom += 1
            if anom <= 12:
                print(f"  {lab(j)} [{f}]: {v!r}")
print(f"  total whitespace/casing anomalies: {anom}")

print("\n=== 4. Markdown/source noise in values (asterisks, links, leading dash) ===")
noise = 0
for j in js:
    for f in FIELDS:
        if f == "source":
            continue
        v = str(j.get(f, ""))
        if "**" in v or "](" in v or "http" in v or v.startswith("- "):
            noise += 1
            if noise <= 12:
                print(f"  {lab(j)} [{f}]: {v[:80]}")
print(f"  total markdown-noise values: {noise}")

print("\n=== 5. Value distributions ===")
print("  statuses:", dict(collections.Counter(j["status"] for j in js)))
print("  continents:", dict(collections.Counter(j["continent"] for j in js)))

print("\n=== 6. Duplicate (country, state, city) ===")
pairs = collections.Counter(
    (j.get("country", "").lower(), j.get("state", "").lower(), j.get("city", "").lower()) for j in js)
dupes = {k: v for k, v in pairs.items() if v > 1}
print("  dupes:", dupes if dupes else "none")
