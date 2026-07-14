"""
generate_sitemap.py — LawfulStay XML sitemap generator
Reads jurisdictions.json and emits sitemap.xml containing:
  - Homepage (priority 1.0)
  - All /regulations/{id}/ pages (priority 0.8, lastmod from last_changed)
Called by monitor.py after build_static_pages.py.
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date

ROOT = Path("/opt/str-tracker")
WEB  = ROOT / "web"
DATA = ROOT / "data" / "jurisdictions.json"

data = json.load(open(DATA))
jurisdictions = data["jurisdictions"]
today = date.today().isoformat()

SITE = "https://lawfulstay.com"

# Build XML
urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

def add_url(loc, lastmod, priority, changefreq="weekly"):
    url = ET.SubElement(urlset, "url")
    ET.SubElement(url, "loc").text = loc
    ET.SubElement(url, "lastmod").text = lastmod
    ET.SubElement(url, "changefreq").text = changefreq
    ET.SubElement(url, "priority").text = str(priority)

# Homepage
add_url(f"{SITE}/", today, 1.0, "daily")

# All regulation pages — use last_changed as lastmod
for j in jurisdictions:
    jid = j.get("id", "")
    if not jid:
        continue
    lastmod = j.get("last_changed") or today
    add_url(f"{SITE}/regulations/{jid}/", lastmod, 0.8)

# Write with XML declaration
tree = ET.ElementTree(urlset)
ET.indent(tree, space="  ")
out = WEB / "sitemap.xml"
with open(out, "wb") as f:
    tree.write(f, xml_declaration=True, encoding="UTF-8")

count = len(urlset)
print(f"Sitemap written: {out} ({count} URLs)")
