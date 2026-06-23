import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
js = json.loads((ROOT / "data" / "jurisdictions.json").read_text())["jurisdictions"]


def show(name):
    for j in js:
        if j["city"] == name:
            print(f"  city={j['city']!r} state={j['state']!r} "
                  f"country={j['country']!r} region={j['region']}")


for n in ["Berlin", "Brussels", "Cancún / Riviera Maya"]:
    print(n + ":")
    show(n)

print("\n=== records where state == city (redundant) ===")
red = [j for j in js if j.get("state") and j["state"] == j["city"]]
for j in red[:20]:
    print(f"  {j['city']} / {j['state']} ({j['country']})")
print(f"  total state==city: {len(red)}")

print("\n=== US records: city / state ===")
us = [j for j in js if j["region"] == "US"]
for j in us:
    print(f"  city={j['city']!r:26} state={j['state']!r}")
print(f"  ({len(us)} US total)")

print("\n=== records per country (top 10) ===")
for country, n in collections.Counter(j["country"] for j in js).most_common(10):
    print(f"  {country}: {n}")
