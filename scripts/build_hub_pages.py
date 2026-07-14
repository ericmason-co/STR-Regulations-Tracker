"""
build_hub_pages.py — LawfulStay state & country hub page generator
Creates index pages at:
  /regulations/state/{slug}/   — US state hubs  (e.g. /regulations/state/california/)
  /regulations/country/{slug}/ — Country hubs   (e.g. /regulations/country/spain/)
Each page lists all tracked jurisdictions in that state/country with status, summary,
and links — targeting high-volume queries like "California short-term rental laws".
Run after build_static_pages.py during every monitor cycle.
"""
import json
import re
from pathlib import Path
from datetime import date
from collections import defaultdict

ROOT     = Path("/opt/str-tracker")
WEB      = ROOT / "web"
REGS_DIR = WEB / "regulations"
DATA     = ROOT / "data" / "jurisdictions.json"

data          = json.load(open(DATA))
jurisdictions = data["jurisdictions"]
total_count   = len(jurisdictions)
today         = date.today().isoformat()
YEAR          = date.today().year

STATUS_COLORS = {
    "Active":     "#16a34a", "Restricted": "#d97706",
    "Banned":     "#dc2626", "Pending":    "#7c3aed", "None": "#6b7280",
}
STATUS_BG = {
    "Active":     "#dcfce7", "Restricted": "#fef3c7",
    "Banned":     "#fee2e2", "Pending":    "#ede9fe", "None": "#f3f4f6",
}
STATUS_EMOJI = {
    "Active": "✅", "Restricted": "⚠️", "Banned": "🚫",
    "Pending": "🕐", "None": "ℹ️",
}

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def esc(s):
    if not s: return ""
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def esc_json(s):
    if not s: return ""
    return str(s).replace("\\","\\\\").replace('"','\\"').replace("\n"," ")

def status_bar(juris_list):
    """Clean status breakdown pills — no emojis, CSS class styled."""
    from collections import Counter
    c = Counter(j.get("status","None") for j in juris_list)
    parts = []
    for status in ("Active","Restricted","Banned","Pending","None"):
        if c[status]:
            parts.append(f'<span class="sb sb-{status.lower()}">{c[status]} {status}</span>')
    return " ".join(parts)

def build_hub_page(scope_type, scope_name, scope_slug, juris_list, related_scopes):
    """
    scope_type: 'state' | 'country'
    scope_name: 'California' | 'Spain'
    scope_slug: 'california' | 'spain'
    juris_list: list of jurisdiction dicts in this scope
    related_scopes: list of (name, slug, count) for sidebar
    """
    url      = f"https://lawfulstay.com/regulations/{scope_type}/{scope_slug}/"
    count    = len(juris_list)
    last_mod = max((j.get("last_changed") or "2024-01-01") for j in juris_list)

    # Title / description
    if scope_type == "state":
        title = f"{scope_name} Short-Term Rental Laws {YEAR} — All Cities | LawfulStay"
        desc  = (f"Complete guide to short-term rental regulations in {scope_name} {YEAR}. "
                 f"LawfulStay tracks STR laws for {count} {scope_name} cities and jurisdictions — "
                 f"permits, taxes, night caps, and compliance requirements.")
        h1    = f"{scope_name} Short-Term Rental Laws {YEAR}"
        intro = (f"LawfulStay tracks short-term rental (STR / Airbnb / Vrbo) regulations for "
                 f"<strong>{count} jurisdictions</strong> across {scope_name}. "
                 f"Select a city below for current permit requirements, tax rates, and compliance details.")
        bc_label = scope_name
    else:
        title = f"{scope_name} Short-Term Rental Regulations {YEAR} — All Cities | LawfulStay"
        desc  = (f"Short-term rental laws in {scope_name} {YEAR}. "
                 f"LawfulStay tracks STR regulations for {count} {scope_name} cities and regions — "
                 f"Airbnb rules, permits, tourist taxes, and compliance requirements.")
        h1    = f"{scope_name} Short-Term Rental Regulations {YEAR}"
        intro = (f"LawfulStay tracks short-term rental (STR / Airbnb / Vrbo) regulations for "
                 f"<strong>{count} cities and regions</strong> in {scope_name}. "
                 f"Select a location below for current permit requirements, tax obligations, and compliance details.")
        bc_label = scope_name

    # Sort jurisdictions: Banned first (most urgent), then Restricted, Active, Pending, None
    order = {"Banned":0,"Restricted":1,"Active":2,"Pending":3,"None":4}
    sorted_j = sorted(juris_list, key=lambda j: (order.get(j.get("status","None"),5), j.get("city","")))

    # Build jurisdiction rows
    rows = []
    for j in sorted_j:
        jid    = j.get("id","")
        city   = j.get("city","")
        state  = j.get("state","") if scope_type == "country" else ""
        status = j.get("status","None")
        sc     = STATUS_COLORS.get(status,"#6b7280")
        sb     = STATUS_BG.get(status,"#f3f4f6")
        emoji  = STATUS_EMOJI.get(status,"ℹ️")
        summ   = (j.get("compliance_notes") or j.get("key_notes") or "")[:160]
        if summ and len(summ) == 160:
            summ += "…"
        loc_sub = f'<span class="row-sub">{esc(state)}</span>' if state else ""
        rows.append(f'''
      <a class="jrow" href="https://lawfulstay.com/regulations/{esc(jid)}/">
        <div class="jrow-left">
          <div class="jrow-city">{esc(city)}{loc_sub}</div>
          <div class="jrow-summ">{esc(summ)}</div>
        </div>
        <span class="jrow-badge badge-{status.lower()}">{esc(status)}</span>
      </a>''')

    rows_html = "\n".join(rows)

    # Status breakdown bar
    sbar = status_bar(juris_list)

    # Related scope links
    related_html = ""
    if related_scopes:
        rel_items = "".join(
            f'<li><a href="https://lawfulstay.com/regulations/{scope_type}/{r_slug}/">'
            f'{esc(r_name)}</a> <span class="rel-count">{r_count}</span></li>'
            for r_name, r_slug, r_count in related_scopes[:12]
        )
        related_label = "Other States" if scope_type == "state" else "Other Countries"
        related_html = f'''
    <div class="sidebar-card">
      <div class="sidebar-title">{related_label}</div>
      <ul class="rel-list">{rel_items}</ul>
    </div>'''

    # JSON-LD
    item_list = [
        {"@type":"ListItem","position":i+1,
         "url": f"https://lawfulstay.com/regulations/{j['id']}/",
         "name": esc_json(f"{j['city']} STR Regulations")}
        for i,j in enumerate(sorted_j)
    ]
    crumbs = [
        {"@type":"ListItem","position":1,"name":"LawfulStay","item":"https://lawfulstay.com/"},
        {"@type":"ListItem","position":2,"name":"Regulations Database","item":"https://lawfulstay.com/"},
        {"@type":"ListItem","position":3,"name":esc_json(bc_label),"item":url},
    ]
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {"@type":"CollectionPage","@id":url,"url":url,
             "name":esc_json(title),"description":esc_json(desc),
             "dateModified":last_mod,"inLanguage":"en",
             "isPartOf":{"@id":"https://lawfulstay.com/#website"},
             "hasPart":item_list[:50],
             "publisher":{"@id":"https://lawfulstay.com/#organization"}},
            {"@type":"BreadcrumbList","@id":f"{url}#breadcrumb","itemListElement":crumbs},
        ]
    }, ensure_ascii=False, indent=2)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}" />
  <meta name="robots" content="index, follow" />
  <link rel="canonical" href="{url}" />
  <meta property="og:site_name" content="LawfulStay" />
  <meta property="og:title" content="{esc(title)}" />
  <meta property="og:description" content="{esc(desc)}" />
  <meta property="og:url" content="{url}" />
  <meta property="og:type" content="website" />
  <meta property="og:image" content="https://lawfulstay.com/og_preview_card.jpg" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:site" content="@LawfulStay" />
  <meta name="twitter:title" content="{esc(title)}" />
  <meta name="twitter:description" content="{esc(desc)}" />
  <meta name="twitter:image" content="https://lawfulstay.com/og_preview_card.jpg" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script type="application/ld+json">
  {jsonld}
  </script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #0f172a; line-height: 1.6; }}
    /* ── Top bar ── */
    .topbar {{ background: #fff; padding: .85rem 2rem; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; }}
    .logo-group {{ display: flex; align-items: center; gap: .65rem; text-decoration: none; color: #0f172a; }}
    .logo-icon-box {{ width: 32px; height: 32px; border-radius: 7px;
                      background: rgba(37,99,235,.08); border: 1px solid #2563eb;
                      box-shadow: 0 0 10px rgba(37,99,235,.2);
                      display: flex; align-items: center; justify-content: center; }}
    .logo-icon {{ color: #2563eb; font-size: 1rem; }}
    .logo-text {{ font-family: "Outfit", sans-serif; font-size: 1.25rem; font-weight: 800; letter-spacing: -0.01em; color: #0f172a; }}
    .logo-text .brand-accent {{ color: #2563eb; }}
    .topbar-link {{ color: #64748b; font-size: .85rem; text-decoration: none; transition: color .15s; }}
    .topbar-link:hover {{ color: #2563eb; }}
    /* ── Layout ── */
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; display: grid; grid-template-columns: 1fr 240px; gap: 2rem; align-items: start; }}
    .main {{ min-width: 0; }}
    /* ── Breadcrumb ── */
    .breadcrumb {{ font-size: .8rem; color: #64748b; margin-bottom: 1.5rem; }}
    .breadcrumb a {{ color: #2563eb; text-decoration: none; }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
    /* ── Header ── */
    h1 {{ font-family: "Outfit", sans-serif; font-size: 2rem; font-weight: 800; color: #0f172a; letter-spacing: -.03em; margin-bottom: .5rem; }}
    .intro {{ color: #475569; font-size: .95rem; margin-bottom: 1.25rem; line-height: 1.65; }}
    /* ── Status summary pills ── */
    .sbar {{ display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: 1.5rem; }}
    .sb {{ font-size: .72rem; font-weight: 700; padding: .25rem .75rem; border-radius: 999px; display: inline-flex; align-items: center; color: #fff; }}
    .sb-active     {{ background: #10b981; }}
    .sb-restricted {{ background: #f59e0b; }}
    .sb-banned     {{ background: #ef4444; }}
    .sb-pending    {{ background: #eab308; color: #1c1917; }}
    .sb-none       {{ background: #475569; }}
    /* ── Jurisdiction rows ── */
    .jrow {{ display: flex; align-items: center; justify-content: space-between; gap: 1rem;
             background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
             padding: 1rem 1.25rem; margin-bottom: .625rem; text-decoration: none;
             color: inherit; box-shadow: 0 1px 3px rgba(0,0,0,.05);
             transition: box-shadow .15s, border-color .15s, transform .1s; }}
    .jrow:hover {{ box-shadow: 0 4px 16px rgba(37,99,235,.1); border-color: #2563eb; transform: translateY(-1px); }}
    .jrow-left {{ flex: 1; min-width: 0; }}
    .jrow-city {{ font-size: 1rem; font-weight: 700; color: #0f172a; display: flex; align-items: baseline; gap: .5rem; }}
    .row-sub {{ font-size: .78rem; font-weight: 400; color: #94a3b8; }}
    .jrow-summ {{ font-size: .82rem; color: #64748b; margin-top: .2rem;
                  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    .jrow-badge {{ flex-shrink: 0; font-size: .75rem; font-weight: 700; padding: .3rem .85rem;
                   border-radius: 999px; white-space: nowrap; color: #fff; }}
    .badge-active     {{ background: #10b981; }}
    .badge-restricted {{ background: #f59e0b; }}
    .badge-banned     {{ background: #ef4444; }}
    .badge-pending    {{ background: #eab308; color: #1c1917; }}
    .badge-none       {{ background: #475569; }}
    /* ── Sidebar ── */
    .sidebar-card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.25rem;
                     margin-bottom: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,.05); }}
    .sidebar-title {{ font-size: .68rem; font-weight: 800; text-transform: uppercase; letter-spacing: .08em;
                      color: #2563eb; margin-bottom: .75rem; padding-bottom: .5rem; border-bottom: 1px solid #f1f5f9; }}
    .rel-list {{ list-style: none; padding: 0; margin: 0; }}
    .rel-list li {{ display: flex; justify-content: space-between; align-items: center;
                    padding: .35rem 0; border-bottom: 1px solid #f1f5f9; font-size: .87rem; }}
    .rel-list li:last-child {{ border: none; }}
    .rel-list a {{ color: #2563eb; text-decoration: none; font-weight: 500; }}
    .rel-list a:hover {{ color: #1d4ed8; }}
    .rel-count {{ font-size: .72rem; color: #94a3b8; font-weight: 600;
                  background: #f1f5f9; padding: .1rem .4rem; border-radius: 4px; }}
    /* ── CTA ── */
    .cta {{ background: linear-gradient(135deg, #0B1426, #0F1F3D); border-radius: 12px; padding: 1.5rem;
            text-align: center; color: #fff; margin-top: 1.5rem; }}
    .cta h3 {{ font-size: 1.1rem; font-weight: 700; margin-bottom: .4rem; }}
    .cta p {{ color: #94a3b8; font-size: .88rem; margin-bottom: 1rem; }}
    .cta-btn {{ display: inline-block; background: #2563eb; color: #fff; font-weight: 700;
                padding: .65rem 1.5rem; border-radius: 8px; text-decoration: none; font-size: .9rem; }}
    .cta-btn:hover {{ background: #1d4ed8; }}
    /* ── Footer ── */
    .footer {{ text-align: center; font-size: .78rem; color: #94a3b8; padding: 2rem;
               border-top: 1px solid #e2e8f0; margin-top: 2rem; }}
    .footer a {{ color: #2563eb; text-decoration: none; }}
    .footer a:hover {{ text-decoration: underline; }}
    @media (max-width: 700px) {{
      .wrap {{ grid-template-columns: 1fr; padding: 1rem; }}
      h1 {{ font-size: 1.5rem; }}
      .sidebar {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class="topbar">
    <a href="https://lawfulstay.com/" class="logo-group">
      <div class="logo-icon-box"><i class="fa-solid fa-scale-balanced logo-icon"></i></div>
      <span class="logo-text">Lawful<span class="brand-accent">Stay</span></span>
    </a>
    <a href="https://lawfulstay.com/" class="topbar-link">&larr; Full Database</a>
  </div>
  <div class="wrap">
    <main class="main">
      <nav class="breadcrumb" aria-label="Breadcrumb">
        <a href="https://lawfulstay.com/">LawfulStay</a> &rsaquo;
        <a href="https://lawfulstay.com/">Regulations Database</a> &rsaquo;
        {esc(bc_label)}
      </nav>
      <h1>{esc(h1)}</h1>
      <p class="intro">{intro}</p>
      <div class="sbar">{sbar}</div>
      {rows_html}
    </main>
    <aside class="sidebar">
      {related_html}
      <div class="cta">
        <h3>Full Global Database</h3>
        <p>Search {total_count:,}+ STR jurisdictions worldwide.</p>
        <a href="https://lawfulstay.com/" class="cta-btn">Browse All &rarr;</a>
      </div>
    </aside>
  </div>
  <div class="footer">
    <p>Data updated daily from official government sources. &nbsp;&middot;&nbsp;
       <a href="https://lawfulstay.com/">LawfulStay.com</a> &mdash;
       The authoritative global STR regulations database. &nbsp;&middot;&nbsp;
       <a href="https://lawfulstay.com/methodology/">Data Methodology</a></p>
  </div>
</body>
</html>'''
    return html, last_mod


# ── Group jurisdictions ──────────────────────────────────────────────────────
us_by_state   = defaultdict(list)
intl_by_country = defaultdict(list)

for j in jurisdictions:
    if j.get("_canary"):          # skip canary entries
        continue
    region  = j.get("region","")
    state   = (j.get("state")   or "").strip()
    country = (j.get("country") or "").strip()
    if region == "US" and state:
        us_by_state[state].append(j)
    elif country and country not in ("United States",):
        intl_by_country[country].append(j)

# ── Generate state hub pages ─────────────────────────────────────────────────
state_count = 0
state_pages = []   # (slug, last_mod) for sitemap

# Build related-states list (sorted by count desc)
all_states_sorted = sorted(us_by_state.items(), key=lambda x: -len(x[1]))

for state_name, j_list in all_states_sorted:
    if len(j_list) < 1:
        continue
    slug = slugify(state_name)
    related = [(s, slugify(s), len(jl)) for s, jl in all_states_sorted if s != state_name][:12]
    html, last_mod = build_hub_page("state", state_name, slug, j_list, related)
    out_dir = REGS_DIR / "state" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    state_pages.append((slug, last_mod))
    state_count += 1

print(f"Generated {state_count} state hub pages")

# ── Generate country hub pages ───────────────────────────────────────────────
country_count = 0
country_pages = []

all_countries_sorted = sorted(intl_by_country.items(), key=lambda x: -len(x[1]))

for country_name, j_list in all_countries_sorted:
    if len(j_list) < 1:
        continue
    slug = slugify(country_name)
    related = [(c, slugify(c), len(jl)) for c, jl in all_countries_sorted if c != country_name][:12]
    html, last_mod = build_hub_page("country", country_name, slug, j_list, related)
    out_dir = REGS_DIR / "country" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    country_pages.append((slug, last_mod))
    country_count += 1

print(f"Generated {country_count} country hub pages")

# ── Persist hub page metadata for sitemap generator ─────────────────────────
hub_meta = {
    "state_pages":   state_pages,
    "country_pages": country_pages,
    "generated":     today,
}
import json as _json
(ROOT / "data" / "hub_pages.json").write_text(_json.dumps(hub_meta, indent=2))
print(f"Hub metadata written to data/hub_pages.json")
print(f"Total hub pages: {state_count + country_count}")
