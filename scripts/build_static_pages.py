"""
build_static_pages.py — LawfulStay static regulation page generator
Phase 2.5 SEO/AEO/GEO: H2 headings, visible FAQ accordions, Speakable schema,
BreadcrumbList + FAQPage + WebPage JSON-LD, At a Glance, answer-first titles,
3-level breadcrumbs, related cities.
"""
import json
import re
import random
from pathlib import Path
from datetime import date

ROOT = Path("/opt/str-tracker")
WEB = ROOT / "web"
REGS_DIR = WEB / "regulations"
DATA = ROOT / "data" / "jurisdictions.json"

data = json.load(open(DATA))
jurisdictions = data["jurisdictions"]
total_count = len(jurisdictions)
today = date.today().isoformat()
YEAR = date.today().year

# Pre-build lookup indexes for related-city links
_by_state   = {}
_by_country = {}
for _j in jurisdictions:
    _s = (_j.get("state") or "").strip()
    _c = (_j.get("country") or "").strip()
    _id = _j.get("id", "")
    if _s:
        _by_state.setdefault(_s, []).append(_j)
    if _c:
        _by_country.setdefault(_c, []).append(_j)

REGS_DIR.mkdir(exist_ok=True)

STATUS_COLORS = {
    "Active":     "#16a34a",
    "Restricted": "#d97706",
    "Banned":     "#dc2626",
    "Pending":    "#7c3aed",
    "None":       "#6b7280",
}
STATUS_BG = {
    "Active":     "#dcfce7",
    "Restricted": "#fef3c7",
    "Banned":     "#fee2e2",
    "Pending":    "#ede9fe",
    "None":       "#f3f4f6",
}
STATUS_EMOJI = {
    "Active":     "✅",
    "Restricted": "⚠️",
    "Banned":     "🚫",
    "Pending":    "🕐",
    "None":       "ℹ️",
}

def esc(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def esc_json(s):
    """Escape for use inside a JSON string value."""
    if not s:
        return ""
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "")

def field_row(label, value):
    if not value or str(value).lower() in ("unknown", "none", "n/a", ""):
        return ""
    return f'''
    <div class="field">
      <div class="field-label">{label}</div>
      <div class="field-value">{esc(str(value))}</div>
    </div>'''

def build_title(city, state, country, status, year):
    """Generate an answer-forward, AEO-optimised title."""
    loc = state or country or ""
    if status == "Banned":
        return f"Is Airbnb Banned in {city}? STR Rules {year} | LawfulStay"
    if status == "Restricted":
        return f"{city} Short-Term Rental Rules {year} — Restrictions & Permits | LawfulStay"
    if status == "Pending":
        return f"{city} STR Regulations {year} — Proposed Changes | LawfulStay"
    # Active / None / default
    loc_part = f", {loc}" if loc and loc != city else ""
    return f"{city}{loc_part} Short-Term Rental Regulations {year} | LawfulStay"

def build_desc(j, city, loc_str, status, year):
    """Generate a unique, answer-first meta description."""
    compliance = (j.get("compliance_notes") or "").strip()
    key = (j.get("key_notes") or "").strip()
    license_req = (j.get("license_required") or "").strip()
    tax = (j.get("tax_rate") or "").strip()

    # Use first sentence of compliance_notes if available and not too long
    first_sentence = ""
    if compliance:
        m = re.match(r"([^.!?]{20,200}[.!?])", compliance)
        if m:
            first_sentence = m.group(1).strip()

    if first_sentence:
        desc = first_sentence
    elif license_req:
        desc = f"{city} STR regulations {year}: {license_req[:140]}."
    else:
        desc = f"{city} short-term rental regulations {year}: Status {status}."

    suffix = f" Find Airbnb rules, permits & tax info on LawfulStay — the global STR compliance database."
    full = desc + suffix
    return full[:300]

def build_glance(j, status, city):
    """Build the At a Glance answer-first summary box with Speakable markup."""
    items = []
    emoji = STATUS_EMOJI.get(status, "ℹ️")

    status_labels = {
        "Active":     "STRs are <strong>permitted</strong> with registration.",
        "Restricted": "STRs are <strong>restricted</strong> — rules apply.",
        "Banned":     "STRs are <strong>prohibited</strong> in most/all zones.",
        "Pending":    "STR regulations are <strong>proposed / pending</strong>.",
        "None":       "No specific STR regulation on record.",
    }
    items.append(f'<li><strong>Status:</strong> {emoji} {status_labels.get(status, status)}</li>')

    if j.get("license_required") and str(j["license_required"]).lower() not in ("unknown", "none", "n/a"):
        v = str(j["license_required"])[:120]
        items.append(f'<li><strong>Permit / License:</strong> {esc(v)}</li>')

    if j.get("tax_rate") and str(j["tax_rate"]).lower() not in ("unknown", "none", "n/a"):
        v = str(j["tax_rate"])[:120]
        items.append(f'<li><strong>Tax Rate:</strong> {esc(v)}</li>')

    if j.get("rental_day_cap") and str(j["rental_day_cap"]).lower() not in ("unknown", "none", "n/a", "no cap", "none specified"):
        v = str(j["rental_day_cap"])[:80]
        items.append(f'<li><strong>Night / Day Cap:</strong> {esc(v)}</li>')

    if j.get("min_stay") and str(j["min_stay"]).lower() not in ("unknown", "none", "n/a", "none specified"):
        v = str(j["min_stay"])[:80]
        items.append(f'<li><strong>Minimum Stay:</strong> {esc(v)}</li>')

    if j.get("fees") and str(j["fees"]).lower() not in ("unknown", "none", "n/a"):
        v = str(j["fees"])[:100]
        items.append(f'<li><strong>Permit Fee:</strong> {esc(v)}</li>')

    if j.get("penalties") and str(j["penalties"]).lower() not in ("unknown", "none", "n/a", "not specified"):
        v = str(j["penalties"])[:100]
        items.append(f'<li><strong>Penalties:</strong> {esc(v)}</li>')

    if not items:
        return ""

    # Speakable CSS selector targets this section id for Google Assistant / voice
    return f'''
    <section id="glance" aria-label="{esc(city)} STR rules at a glance">
      <h2 class="section-h2">At a Glance &mdash; {esc(city)} STR Rules</h2>
      <div class="glance-box">
        <div class="glance-title">⚡ Quick Facts</div>
        <ul class="glance-list">
          {"".join(items)}
        </ul>
      </div>
    </section>'''

def build_faq_html(j, city):
    """Build visible FAQ accordions in HTML body — critical for AI engine extraction."""
    pairs = []
    compliance = (j.get("compliance_notes") or "").strip()
    license_r  = (j.get("license_required")  or "").strip()
    tax_rate   = (j.get("tax_rate")          or "").strip()
    key_notes  = (j.get("key_notes")         or "").strip()
    penalties  = (j.get("penalties")         or "").strip()

    if compliance:
        pairs.append((f"What are the short-term rental rules in {city}?", compliance[:600]))
    if license_r and license_r.lower() not in ("unknown", "none", "n/a"):
        pairs.append((f"Do I need a permit or license to rent on Airbnb in {city}?", license_r[:400]))
    if tax_rate and tax_rate.lower() not in ("unknown", "none", "n/a"):
        pairs.append((f"What taxes apply to short-term rentals in {city}?", tax_rate[:400]))
    if key_notes:
        pairs.append((f"What are the most important STR compliance points in {city}?", key_notes[:500]))
    if penalties and penalties.lower() not in ("not specified", "unknown", "none", "n/a"):
        pairs.append((f"What are the penalties for illegal STR operation in {city}?", penalties[:300]))

    if not pairs:
        return ""

    items = "".join(
        f'''<details class="faq-item">
          <summary class="faq-q">{esc(q)}</summary>
          <div class="faq-a">{esc(a)}</div>
        </details>'''
        for q, a in pairs
    )
    return f'''
    <section id="faq" aria-label="Frequently asked questions about {esc(city)} STR regulations">
      <h2 class="section-h2">Frequently Asked Questions</h2>
      <div class="faq-list">{items}</div>
    </section>'''


def build_related(j, jid):
    """Build a related-cities section for same state or country."""
    state   = (j.get("state")   or "").strip()
    country = (j.get("country") or "").strip()
    city    = (j.get("city")    or "").strip()

    pool = []
    if state and state in _by_state:
        pool = [x for x in _by_state[state] if x.get("id") != jid]
    if len(pool) < 3 and country and country in _by_country:
        pool = [x for x in _by_country[country] if x.get("id") != jid]

    if not pool:
        return ""

    pool_sorted = sorted(pool, key=lambda x: x.get("last_changed", ""), reverse=True)
    sample = pool_sorted[:5]

    scope = f"in {state}" if state else f"in {country}"
    items = "".join(
        f'<li><a href="https://lawfulstay.com/regulations/{x["id"]}/">{esc(x["city"])}</a>'
        f'<span class="rel-status rel-{x.get("status","").lower()}">{esc(x.get("status",""))}</span></li>'
        for x in sample
    )
    return f'''
    <section aria-label="Related jurisdictions">
      <div class="card related-card">
        <h2 class="card-title" style="font-size:0.7rem">Other STR Jurisdictions {esc(scope)}</h2>
        <ul class="related-list">{items}</ul>
      </div>
    </section>'''

def build_jsonld(j, jid, city, state, country, loc_str, status, title, desc,
                 last_changed, last_checked, official_url):
    """Build rich JSON-LD: @graph with WebPage, BreadcrumbList, FAQPage."""
    url = f"https://lawfulstay.com/regulations/{jid}/"

    # BreadcrumbList — 3 levels
    crumbs = [
        {"@type": "ListItem", "position": 1, "name": "LawfulStay",
         "item": "https://lawfulstay.com/"},
        {"@type": "ListItem", "position": 2, "name": "Regulations Database",
         "item": "https://lawfulstay.com/"},
    ]
    if state and state != city:
        crumbs.append({"@type": "ListItem", "position": 3, "name": esc_json(state),
                        "item": "https://lawfulstay.com/"})
        crumbs.append({"@type": "ListItem", "position": 4, "name": esc_json(city),
                        "item": url})
    else:
        crumbs.append({"@type": "ListItem", "position": 3, "name": esc_json(city),
                        "item": url})

    # FAQPage — use compliance_notes + key_notes as Q&A
    faq_pairs = []
    compliance = (j.get("compliance_notes") or "").strip()
    key_notes  = (j.get("key_notes")        or "").strip()
    license_r  = (j.get("license_required") or "").strip()
    tax_rate   = (j.get("tax_rate")         or "").strip()

    if compliance:
        faq_pairs.append({
            "q": f"What are the short-term rental rules in {city}?",
            "a": compliance[:500],
        })
    if license_r and license_r.lower() not in ("unknown", "none", "n/a"):
        faq_pairs.append({
            "q": f"Do you need a permit or license to operate an Airbnb in {city}?",
            "a": license_r[:300],
        })
    if tax_rate and tax_rate.lower() not in ("unknown", "none", "n/a"):
        faq_pairs.append({
            "q": f"What taxes apply to short-term rentals in {city}?",
            "a": tax_rate[:300],
        })
    if key_notes:
        faq_pairs.append({
            "q": f"What are the most important STR compliance points in {city}?",
            "a": key_notes[:400],
        })

    faq_entities = [
        {"@type": "Question",
         "name": esc_json(p["q"]),
         "acceptedAnswer": {"@type": "Answer", "text": esc_json(p["a"])}}
        for p in faq_pairs
    ]

    graph = [
        {
            "@type": "WebPage",
            "@id": url,
            "url": url,
            "name": esc_json(title),
            "description": esc_json(desc),
            "dateModified": last_changed,
            "datePublished": last_checked,
            "inLanguage": "en",
            "isPartOf": {"@id": "https://lawfulstay.com/#website"},
            "about": {
                "@type": "Place",
                "name": esc_json(city),
                "addressRegion": esc_json(state),
                "addressCountry": esc_json(country),
            },
            "publisher": {
                "@type": "Organization",
                "@id": "https://lawfulstay.com/#organization",
                "name": "LawfulStay",
                "url": "https://lawfulstay.com",
                "logo": {
                    "@type": "ImageObject",
                    "url": "https://lawfulstay.com/favicon.svg",
                },
            },
            "breadcrumb": {"@id": f"{url}#breadcrumb"},
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{url}#breadcrumb",
            "itemListElement": crumbs,
        },
    ]

    if faq_entities:
        graph.append({
            "@type": "FAQPage",
            "@id": f"{url}#faq",
            "mainEntity": faq_entities,
        })

    # Speakable — marks the At a Glance section for Google Assistant / voice search
    graph[0]["speakable"] = {
        "@type": "SpeakableSpecification",
        "cssSelector": ["#glance", "h1.city-name"],
    }

    return json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, indent=2)

def build_page(j):
    jid          = j.get("id", "")
    city         = j.get("city", "")
    state        = j.get("state", "")
    country      = j.get("country", "")
    status       = j.get("status", "Unknown")
    region       = j.get("region", "")
    last_changed = j.get("last_changed", today)
    last_checked = j.get("last_checked", today)

    loc_parts = [p for p in [state if state != city else None, country] if p]
    loc_str   = " · ".join(loc_parts)

    title = build_title(city, state, country, status, YEAR)
    desc  = build_desc(j, city, loc_str, status, YEAR)

    status_color = STATUS_COLORS.get(status, "#6b7280")
    status_bg    = STATUS_BG.get(status, "#f3f4f6")

    # Official source URL
    official_url = str(j.get("official_licenses", "") or "").strip()
    if not re.match(r"https?://", official_url):
        official_url = ""
    if not official_url:
        src_field = str(j.get("source", "") or "")
        url_match = re.search(r"https?://[^ ;,\"]+", src_field)
        if url_match:
            official_url = url_match.group(0).rstrip(".")

    # JSON-LD
    jsonld = build_jsonld(j, jid, city, state, country, loc_str, status,
                          title, desc, last_changed, last_checked, official_url)

    # At a Glance (with Speakable section wrapper + H2)
    glance_html = build_glance(j, status, city)

    # Visible FAQ accordions
    faq_html = build_faq_html(j, city)

    # Fields card
    fields  = field_row("Regulatory Status",        status)
    fields += field_row("License / Registration",   j.get("license_required"))
    fields += field_row("Tax Registration",         j.get("tax_registration_required"))
    fields += field_row("Permit Fee",               j.get("fees"))
    fields += field_row("Primary Residence Rule",   j.get("primary_residence_required"))
    fields += field_row("Night / Day Cap",          j.get("rental_day_cap"))
    fields += field_row("Occupancy Limit",          j.get("occupancy_limit"))
    fields += field_row("Tax Rate",                 j.get("tax_rate"))
    fields += field_row("Zoning Restrictions",      j.get("zoning_restrictions"))
    fields += field_row("Minimum Stay",             j.get("min_stay"))
    fields += field_row("Density Rules",            j.get("density_rules"))
    fields += field_row("Insurance Required",       j.get("insurance_required"))
    fields += field_row("Platform Obligations",     j.get("platform_obligations"))
    fields += field_row("Compliance Notes",         j.get("compliance_notes"))
    fields += field_row("Effective Date",           j.get("effective_date"))
    fields += field_row("Key Notes",                j.get("key_notes"))
    fields += field_row("Penalties",                j.get("penalties"))
    fields += field_row("Additional Context",       j.get("additional_context"))

    # Source links
    source = j.get("source", "")
    source_html = ""
    if source:
        parts = source.split(";")
        source_links = []
        for p in parts:
            p = p.strip()
            if p.startswith("http"):
                label = p[:70] + ("…" if len(p) > 70 else "")
                source_links.append(f'<a href="{esc(p)}" target="_blank" rel="nofollow noopener">{esc(label)}</a>')
            else:
                source_links.append(esc(p))
        source_html = f'''
    <div class="field">
      <div class="field-label">Sources</div>
      <div class="field-value sources">{"<br>".join(source_links)}</div>
    </div>'''

    # Official source button (above feedback)
    official_btn = ""
    if official_url:
        official_btn = f'''
    <div class="comply-box">
      <div class="comply-title">&#x1F4CB; Apply / Register with the Official Authority</div>
      <p class="comply-desc">Apply for your STR permit or registration directly through the official government portal.</p>
      <a href="{esc(official_url)}" target="_blank" rel="nofollow noopener" class="comply-btn">
        Official Source &#x2197;
      </a>
    </div>'''

    # Related cities
    related_html = build_related(j, jid)

    import re as _re2
    def _slug(s):
        return _re2.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

    # Breadcrumb HTML (visual, 3-level) — state/country names link to hub pages
    if state and state != city:
        state_slug = _slug(state)
        breadcrumb_html = f'''<a href="https://lawfulstay.com/">LawfulStay</a> &rsaquo;
      <a href="https://lawfulstay.com/">Regulations Database</a> &rsaquo;
      <a href="https://lawfulstay.com/regulations/state/{state_slug}/">{esc(state)}</a> &rsaquo;
      {esc(city)}'''
    else:
        country_slug = _slug(country) if country else ""
        country_link = (
            f'<a href="https://lawfulstay.com/regulations/country/{country_slug}/">{esc(country)}</a>'
            if country_slug else esc(country)
        )
        breadcrumb_html = f'''<a href="https://lawfulstay.com/">LawfulStay</a> &rsaquo;
      <a href="https://lawfulstay.com/">Regulations Database</a> &rsaquo;
      {country_link} &rsaquo;
      {esc(city)}'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}" />
  <meta name="robots" content="index, follow" />
  <link rel="canonical" href="https://lawfulstay.com/regulations/{jid}/" />
  <meta property="og:site_name" content="LawfulStay" />
  <meta property="og:title" content="{esc(title)}" />
  <meta property="og:description" content="{esc(desc)}" />
  <meta property="og:url" content="https://lawfulstay.com/regulations/{jid}/" />
  <meta property="og:type" content="article" />
  <meta property="og:image" content="https://lawfulstay.com/og_preview_card.jpg" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:site" content="@LawfulStay" />
  <meta name="twitter:title" content="{esc(title)}" />
  <meta name="twitter:description" content="{esc(desc)}" />
  <script type="application/ld+json">
  {jsonld}
  </script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #0f172a; line-height: 1.6; }}
    .topbar {{ background: #0B1426; padding: 1rem 2rem; display: flex; align-items: center; justify-content: space-between; }}
    .logo {{ color: #fff; font-size: 1.3rem; font-weight: 800; text-decoration: none; }}
    .logo span {{ color: #2DD4BF; }}
    .topbar-link {{ color: #94a3b8; font-size: 0.85rem; text-decoration: none; }}
    .topbar-link:hover {{ color: #2DD4BF; }}
    .container {{ max-width: 860px; margin: 0 auto; padding: 2rem 1.5rem; }}
    .breadcrumb {{ font-size: 0.8rem; color: #64748b; margin-bottom: 1.5rem; }}
    .breadcrumb a {{ color: #2563eb; text-decoration: none; }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
    .header {{ margin-bottom: 1.5rem; }}
    .city-name {{ font-size: 2.2rem; font-weight: 800; color: #0f172a; letter-spacing: -0.03em; margin-bottom: 0.25rem; }}
    .location {{ font-size: 1rem; color: #64748b; margin-bottom: 1rem; }}
    .status-badge {{ display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.35rem 0.85rem; border-radius: 999px; font-size: 0.85rem; font-weight: 700; letter-spacing: 0.03em; background: {status_bg}; color: {status_color}; border: 1px solid {status_color}40; margin-bottom: 1rem; }}
    .meta {{ font-size: 0.8rem; color: #94a3b8; margin-top: 0.5rem; }}
    /* Section H2s */
    .section-h2 {{ font-size: 1rem; font-weight: 700; color: #0f172a; margin-bottom: 1rem; letter-spacing: -0.01em; }}
    /* At a Glance */
    .glance-box {{ background: #fff; border: 2px solid #2DD4BF40; border-left: 4px solid #2DD4BF; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
    .glance-title {{ font-size: 0.75rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; color: #2DD4BF; margin-bottom: 0.75rem; }}
    .glance-list {{ list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.45rem; }}
    .glance-list li {{ font-size: 0.92rem; color: #1e293b; padding-left: 0.5rem; border-left: 2px solid #e2e8f0; }}
    section {{ margin-bottom: 1.5rem; }}
    /* FAQ accordions */
    .faq-list {{ display: flex; flex-direction: column; gap: 0.5rem; }}
    .faq-item {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
    .faq-q {{ font-size: 0.92rem; font-weight: 600; color: #0f172a; padding: 0.9rem 1.1rem; cursor: pointer; list-style: none; display: flex; justify-content: space-between; align-items: center; }}
    .faq-q::-webkit-details-marker {{ display: none; }}
    .faq-q::after {{ content: "+"; font-size: 1.1rem; color: #2DD4BF; font-weight: 700; flex-shrink: 0; margin-left: 0.75rem; }}
    details[open] .faq-q::after {{ content: "\2212"; }}
    .faq-a {{ font-size: 0.88rem; color: #475569; padding: 0 1.1rem 0.9rem; line-height: 1.65; }}
    /* Cards */
    .card {{ background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
    .card-title {{ font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #2DD4BF; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #e2e8f0; }}
    .field {{ margin-bottom: 1rem; }}
    .field:last-child {{ margin-bottom: 0; }}
    .field-label {{ font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; margin-bottom: 0.25rem; }}
    .field-value {{ font-size: 0.95rem; color: #1e293b; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.6rem 0.8rem; }}
    .sources {{ font-size: 0.82rem; }}
    .sources a {{ color: #2563eb; word-break: break-all; }}
    /* Related */
    .related-card {{ }}
    .related-list {{ list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.5rem; }}
    .related-list li {{ display: flex; align-items: center; justify-content: space-between; font-size: 0.9rem; }}
    .related-list a {{ color: #2563eb; text-decoration: none; }}
    .related-list a:hover {{ text-decoration: underline; }}
    .rel-status {{ font-size: 0.72rem; font-weight: 700; border-radius: 999px; padding: 0.15rem 0.6rem; }}
    .rel-active {{ background: #dcfce7; color: #16a34a; }}
    .rel-restricted {{ background: #fef3c7; color: #d97706; }}
    .rel-banned {{ background: #fee2e2; color: #dc2626; }}
    .rel-pending {{ background: #ede9fe; color: #7c3aed; }}
    /* CTA / comply */
    .cta {{ background: linear-gradient(135deg, #0B1426, #0F1F3D); border-radius: 12px; padding: 2rem; text-align: center; color: #fff; margin-bottom: 1.5rem; }}
    .cta h3 {{ font-size: 1.3rem; font-weight: 700; margin-bottom: 0.5rem; }}
    .cta p {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.25rem; }}
    .cta-btn {{ display: inline-block; background: #2DD4BF; color: #0B1426; font-weight: 700; padding: 0.75rem 1.75rem; border-radius: 8px; text-decoration: none; font-size: 0.95rem; }}
    .cta-btn:hover {{ background: #22c5b0; }}
    .comply-box {{ background: linear-gradient(135deg, #0B1426, #0F1F3D); border: 1px solid #2DD4BF40; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
    .comply-title {{ font-size: 1rem; font-weight: 700; color: #2DD4BF; margin-bottom: 0.4rem; }}
    .comply-desc {{ font-size: 0.88rem; color: #94A3B8; margin-bottom: 1rem; }}
    .comply-btn {{ display: inline-block; background: #2DD4BF; color: #0B1426; font-weight: 700; padding: 0.65rem 1.5rem; border-radius: 8px; text-decoration: none; font-size: 0.9rem; }}
    .comply-btn:hover {{ background: #22c5b0; }}
    /* Feedback */
    .feedback-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 1.5rem; }}
    .feedback-title {{ font-size: 0.88rem; font-weight: 700; color: #475569; margin-bottom: 0.75rem; }}
    .feedback-btn {{ background: #475569; color: #fff; font-weight: 600; padding: 0.5rem 1.25rem; border-radius: 7px; border: none; cursor: pointer; font-size: 0.85rem; }}
    .feedback-btn:hover {{ background: #334155; }}
    .footer {{ text-align: center; font-size: 0.8rem; color: #94a3b8; padding: 2rem 0; border-top: 1px solid #e2e8f0; margin-top: 1rem; }}
    .footer a {{ color: #2563eb; text-decoration: none; }}
    @media (max-width: 600px) {{ .city-name {{ font-size: 1.6rem; }} .container {{ padding: 1rem; }} .topbar {{ padding: 0.75rem 1rem; }} }}
  </style>
</head>
<body>
  <div class="topbar">
    <a href="https://lawfulstay.com/" class="logo">Lawful<span>Stay</span></a>
    <a href="https://lawfulstay.com/" class="topbar-link">&larr; Back to Database</a>
  </div>
  <div class="container">
    <nav class="breadcrumb" aria-label="Breadcrumb">
      {breadcrumb_html}
    </nav>
    <div class="header">
      <h1 class="city-name">{esc(city)}</h1>
      <div class="location">{esc(loc_str)}</div>
      <div class="status-badge">{esc(status)}</div>
      <div class="meta">Last updated: {esc(last_changed)} &nbsp;·&nbsp; Last verified: {esc(last_checked)} &nbsp;·&nbsp; Region: {esc(region)}</div>
    </div>
    {glance_html}
    <section aria-label="Full regulatory details">
      <div class="card">
        <h2 class="section-h2">Full Regulatory Details</h2>
        {fields}
        {source_html}
      </div>
    </section>
    {official_btn}
    {faq_html}
    {related_html}
    <div class="feedback-box">
      <div class="feedback-title">&#x270F; Spot an error or broken link?</div>
      <form id="feedback-form" onsubmit="submitFeedback(event)">
        <input type="hidden" id="fb-jid" value="{jid}" />
        <input type="hidden" id="fb-label" value="{esc(city)}, {esc(country)}" />
        <textarea id="fb-notes" placeholder="Describe what needs correcting (e.g. wrong permit fee, broken link, outdated rule...)" rows="3" style="width:100%;padding:0.6rem;border:1px solid #e2e8f0;border-radius:8px;font-size:0.85rem;resize:vertical;margin-bottom:0.5rem;"></textarea>
        <input type="email" id="fb-email" placeholder="Your email (optional)" style="width:100%;padding:0.6rem;border:1px solid #e2e8f0;border-radius:8px;font-size:0.85rem;margin-bottom:0.5rem;" />
        <button type="submit" class="feedback-btn">Submit Correction</button>
        <div id="fb-msg" style="margin-top:0.5rem;font-size:0.82rem;"></div>
      </form>
    </div>
    <script>
    function submitFeedback(e) {{
      e.preventDefault();
      var notes = document.getElementById('fb-notes').value.trim();
      var email = document.getElementById('fb-email').value.trim();
      var jid = document.getElementById('fb-jid').value;
      var label = document.getElementById('fb-label').value;
      var msg = document.getElementById('fb-msg');
      if (!notes) {{ msg.style.color='#dc2626'; msg.textContent='Please describe the correction needed.'; return; }}
      msg.style.color='#64748b'; msg.textContent='Submitting...';
      fetch('https://lawfulstay.com/api/submit-feedback', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{jurisdiction_id: jid, jurisdiction_label: label, email: email, notes: notes}})
      }}).then(r=>r.json()).then(d=>{{
        if(d.ok){{ msg.style.color='#16a34a'; msg.textContent='Thank you \u2014 we review all corrections within 24 hours.'; document.getElementById('feedback-form').reset(); }}
        else {{ msg.style.color='#dc2626'; msg.textContent=d.error||'Something went wrong. Please try again.'; }}
      }}).catch(()=>{{ msg.style.color='#dc2626'; msg.textContent='Network error. Please try again.'; }});
    }}
    </script>
    <div class="cta">
      <h3>Search {total_count:,}+ STR Jurisdictions</h3>
      <p>LawfulStay tracks STR regulations across {total_count:,}+ cities & countries on 6 continents, updated daily.</p>
      <a href="https://lawfulstay.com/?id={jid}" class="cta-btn">View in Full Database &rarr;</a>
    </div>
    <div class="footer">
      <p>Data sourced from official government sources and verified research. Last verified {esc(last_checked)}.</p>
      <p style="margin-top:0.5rem;"><a href="https://lawfulstay.com/">LawfulStay.com</a> &mdash; The authoritative global STR regulations database. <a href="https://lawfulstay.com/">Browse all {total_count:,} jurisdictions &rarr;</a></p>
    </div>
  </div>
</body>
</html>'''
    return html


# ── Generate all pages ──────────────────────────────────────────────────────
count = 0
errors = 0
for j in jurisdictions:
    jid = j.get("id", "")
    if not jid:
        continue
    try:
        page_dir = REGS_DIR / jid
        page_dir.mkdir(parents=True, exist_ok=True)
        html = build_page(j)
        (page_dir / "index.html").write_text(html, encoding="utf-8")
        count += 1
    except Exception as e:
        print(f"Error on {jid}: {e}")
        errors += 1

print(f"Generated {count} static pages ({errors} errors)")
print(f"Output: {REGS_DIR}")

# ── Compress OG image with Pillow ─────────────────────────────────────
try:
    from PIL import Image
    import os
    og_orig = WEB / "og_preview_card_original.png"
    og_jpg  = WEB / "og_preview_card.jpg"
    # Use original source if available, else backup
    src = og_orig if og_orig.exists() else WEB / "og_preview_card_backup.png"
    if src.exists() and (not og_jpg.exists() or og_jpg.stat().st_size > 150_000):
        img = Image.open(src).convert('RGB')
        img.save(str(og_jpg), 'JPEG', quality=82, optimize=True, progressive=True)
        print(f"OG image (JPEG): {og_jpg.stat().st_size//1024}KB")
    elif og_jpg.exists():
        print(f"OG image already optimized ({og_jpg.stat().st_size//1024}KB)")
except Exception as e:
    print(f"OG image compression skipped: {e}")
