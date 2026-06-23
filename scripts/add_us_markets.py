"""Add major US short-term-rental markets missing from the database.

Targets high-volume STR markets (vacation/beach/ski towns + major metros) across
states and cities not yet covered. Reuses add_destinations.add_list (idempotent).

Run on the droplet:
    set -a; . /etc/lawfulstay/monitor.env; set +a
    ./.venv/bin/python scripts/add_us_markets.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_destinations import add_list  # noqa: E402

# (city, state, country, region)
US = [
    # California
    ("Big Bear Lake", "California"), ("Joshua Tree", "California"),
    ("Mammoth Lakes", "California"), ("Oakland", "California"), ("San Jose", "California"),
    ("Sonoma County", "California"),
    # Florida
    ("Miami", "Florida"), ("Tampa", "Florida"), ("Key West", "Florida"),
    ("Destin", "Florida"), ("Panama City Beach", "Florida"), ("Kissimmee", "Florida"),
    ("Fort Lauderdale", "Florida"), ("Naples", "Florida"),
    # Texas
    ("San Antonio", "Texas"), ("Dallas", "Texas"), ("Galveston", "Texas"),
    ("Fredericksburg", "Texas"), ("Port Aransas", "Texas"),
    # Colorado (ski)
    ("Denver", "Colorado"), ("Breckenridge", "Colorado"), ("Vail", "Colorado"),
    ("Telluride", "Colorado"), ("Steamboat Springs", "Colorado"),
    # Arizona
    ("Sedona", "Arizona"), ("Phoenix", "Arizona"), ("Flagstaff", "Arizona"),
    # Tennessee
    ("Pigeon Forge", "Tennessee"), ("Memphis", "Tennessee"),
    # Utah
    ("Moab", "Utah"), ("Salt Lake City", "Utah"),
    # Hawaii / Nevada
    ("Kauai County", "Hawaii"), ("Reno", "Nevada"),
    # Pacific Northwest
    ("Seattle", "Washington"), ("Portland", "Oregon"), ("Bend", "Oregon"),
    # Northeast / Midwest metros
    ("Boston", "Massachusetts"), ("Barnstable (Cape Cod)", "Massachusetts"),
    ("Chicago", "Illinois"), ("Philadelphia", "Pennsylvania"),
    # South / mountain / beach
    ("Atlanta", "Georgia"), ("Tybee Island", "Georgia"),
    ("Santa Fe", "New Mexico"), ("Bozeman", "Montana"), ("Big Sky", "Montana"),
    ("Jackson", "Wyoming"), ("Bar Harbor", "Maine"), ("Gulf Shores", "Alabama"),
    ("Branson", "Missouri"), ("Hilton Head Island", "South Carolina"),
    ("Dare County (Outer Banks)", "North Carolina"), ("Virginia Beach", "Virginia"),
]
US = [(c, s, "United States", "US") for c, s in US]

if __name__ == "__main__":
    add_list(US, "us-markets-add", "Added major US short-term-rental markets")
