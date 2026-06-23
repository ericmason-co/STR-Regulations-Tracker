"""Check which top travel / vacation-rental destinations are missing from the DB."""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
js = json.loads((ROOT / "data" / "jurisdictions.json").read_text())["jurisdictions"]


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# Match against city, state, and country (so city-states like Hong Kong count)
have = [norm(j["city"]) for j in js] + [norm(j["country"]) for j in js]
have_blob = " | ".join(have)


def present(name):
    n = norm(name)
    # match if a record's city equals or contains the destination (or vice versa)
    return any(n == h or n in h or h in n for h in have if h)


# Top global travel + vacation-rental destinations (city, country)
DESTS = [
    # Europe
    ("Paris", "France"), ("Nice", "France"), ("Cannes", "France"), ("Lyon", "France"),
    ("London", "United Kingdom"), ("Edinburgh", "United Kingdom"),
    ("Barcelona", "Spain"), ("Madrid", "Spain"), ("Seville", "Spain"),
    ("Palma de Mallorca", "Spain"), ("Malaga", "Spain"), ("Ibiza", "Spain"),
    ("Rome", "Italy"), ("Venice", "Italy"), ("Florence", "Italy"), ("Milan", "Italy"),
    ("Naples", "Italy"), ("Amalfi Coast", "Italy"),
    ("Lisbon", "Portugal"), ("Porto", "Portugal"), ("Algarve", "Portugal"),
    ("Amsterdam", "Netherlands"), ("Berlin", "Germany"), ("Munich", "Germany"),
    ("Vienna", "Austria"), ("Prague", "Czechia"), ("Budapest", "Hungary"),
    ("Athens", "Greece"), ("Santorini", "Greece"), ("Mykonos", "Greece"),
    ("Dubrovnik", "Croatia"), ("Split", "Croatia"), ("Reykjavik", "Iceland"),
    ("Copenhagen", "Denmark"), ("Stockholm", "Sweden"), ("Zurich", "Switzerland"),
    ("Brussels", "Belgium"), ("Dublin", "Ireland"),
    # Middle East / Africa
    ("Dubai", "United Arab Emirates"), ("Abu Dhabi", "United Arab Emirates"),
    ("Istanbul", "Turkey"), ("Antalya", "Turkey"), ("Tel Aviv", "Israel"),
    ("Doha", "Qatar"), ("Marrakech", "Morocco"), ("Cairo", "Egypt"),
    ("Cape Town", "South Africa"), ("Zanzibar", "Tanzania"), ("Nairobi", "Kenya"),
    # Asia-Pacific
    ("Bangkok", "Thailand"), ("Phuket", "Thailand"), ("Pattaya", "Thailand"),
    ("Singapore", "Singapore"), ("Kuala Lumpur", "Malaysia"), ("Bali", "Indonesia"),
    ("Tokyo", "Japan"), ("Kyoto", "Japan"), ("Osaka", "Japan"), ("Seoul", "South Korea"),
    ("Hong Kong", "Hong Kong"), ("Taipei", "Taiwan"), ("Shanghai", "China"),
    ("Sydney", "Australia"), ("Melbourne", "Australia"), ("Gold Coast", "Australia"),
    ("Auckland", "New Zealand"), ("Queenstown", "New Zealand"),
    ("Goa", "India"), ("Mumbai", "India"), ("Bali Denpasar", "Indonesia"),
    # Americas
    ("New York City", "United States"), ("Los Angeles", "United States"),
    ("Las Vegas", "United States"), ("Miami", "United States"), ("Orlando", "United States"),
    ("San Francisco", "United States"), ("New Orleans", "United States"),
    ("Nashville", "United States"), ("Honolulu", "United States"), ("Maui", "United States"),
    ("San Diego", "United States"), ("Scottsdale", "United States"), ("Austin", "United States"),
    ("Aspen", "United States"), ("Savannah", "United States"), ("Charleston", "United States"),
    ("Gatlinburg", "United States"), ("Lake Tahoe", "United States"),
    ("Myrtle Beach", "United States"), ("Park City", "United States"),
    ("Toronto", "Canada"), ("Vancouver", "Canada"), ("Montreal", "Canada"),
    ("Cancun", "Mexico"), ("Mexico City", "Mexico"), ("Tulum", "Mexico"),
    ("Cabo San Lucas", "Mexico"), ("Puerto Vallarta", "Mexico"),
    ("Punta Cana", "Dominican Republic"), ("Nassau", "Bahamas"), ("Montego Bay", "Jamaica"),
    ("Rio de Janeiro", "Brazil"), ("Buenos Aires", "Argentina"), ("Cartagena", "Colombia"),
    ("Cusco", "Peru"), ("San Juan", "Puerto Rico"),
]

missing = [(c, co) for c, co in DESTS if not present(c)]
present_list = [(c, co) for c, co in DESTS if present(c)]

print(f"Checked {len(DESTS)} top destinations.")
print(f"  Already covered: {len(present_list)}")
print(f"  MISSING: {len(missing)}\n")
print("=== MISSING destinations ===")
by_country = {}
for c, co in missing:
    by_country.setdefault(co, []).append(c)
for co in sorted(by_country):
    print(f"  {co}: {', '.join(by_country[co])}")
