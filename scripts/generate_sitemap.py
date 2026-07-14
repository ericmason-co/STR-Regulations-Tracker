"""
generate_sitemap.py — LawfulStay XML sitemap generator
Reads jurisdictions.json and hub_pages.json, emits sitemap.xml containing:
  - Homepage (priority 1.0)
  - State hub pages  /regulations/state/{slug}/    (priority 0.9)
  - Country hub pages /regulations/country/{slug}/ (priority 0.9)
  - All /regulations/{id}/ city pages              (priority 0.8)
Called by monitor.py after build_static_pages.py and build_hub_pages.py.
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date

ROOT = Path("/opt/str-tracker")
WEB  = ROOT / "web"
DATA = ROOT / "data" / "jurisdictions.json"
HUB_META = ROOT / "data" / "hub_pages.json"

data = json.load(open(DATA))
jurisdictions = data["jurisdictions"]
today = date.today().isoformat()

SITE = "https://lawfulstay.com"

urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

def add_url(loc, lastmod, priority, changefreq="weekly"):
    url = ET.SubElement(urlset, "url")
    ET.SubElement(url, "loc").text = loc
    ET.SubElement(url, "lastmod").text = lastmod
    ET.SubElement(url, "changefreq").text = changefreq
    ET.SubElement(url, "priority").text = str(priority)

# Homepage
add_url(f"{SITE}/", today, 1.0, "daily")

# Methodology / E-E-A-T page
add_url(f"{SITE}/methodology/", today, 0.9, "monthly")

# Hub pages (state + country) — higher priority than city pages
if HUB_META.exists():
    hub = json.load(open(HUB_META))
    for slug, last_mod in hub.get("state_pages", []):
        add_url(f"{SITE}/regulations/state/{slug}/", last_mod or today, 0.9)
    for slug, last_mod in hub.get("country_pages", []):
        add_url(f"{SITE}/regulations/country/{slug}/", last_mod or today, 0.9)

# City regulation pages
for j in jurisdictions:
    jid = j.get("id", "")
    if not jid:
        continue
    lastmod = j.get("last_changed") or today
    add_url(f"{SITE}/regulations/{jid}/", lastmod, 0.8)

tree = ET.ElementTree(urlset)
ET.indent(tree, space="  ")
out = WEB / "sitemap.xml"
with open(out, "wb") as f:
    tree.write(f, xml_declaration=True, encoding="UTF-8")

count = len(urlset)
print(f"Sitemap written: {out} ({count} URLs)")
