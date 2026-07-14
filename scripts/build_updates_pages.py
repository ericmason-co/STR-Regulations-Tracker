"""
build_updates_pages.py — LawfulStay Regulatory Updates page generator

Generates:
  /regulatory-updates/                    — rolling index of all digests
  /regulatory-updates/YYYY-MM-DD/         — individual digest pages

Each digest page carries:
  • NewsArticle + BreadcrumbList + ItemList JSON-LD
  • Meta description built from top changes
  • Change-type badge colour-coding
  • Links to individual jurisdiction pages
  • IndexNow ping after generation
"""
import json
import re
import requests
from pathlib import Path
from datetime import datetime, date

ROOT       = Path("/opt/str-tracker")
WEB        = ROOT / "web"
DATA_DIR   = ROOT / "data" / "regulatory-updates"
UPDATES_DIR = WEB / "regulatory-updates"
SITE_URL   = "https://lawfulstay.com"
YEAR       = date.today().year

BADGE_COLORS = {
    "New Regulation":  ("#dcfce7", "#166534", "#16a34a"),
    "New Restriction": ("#fee2e2", "#991b1b", "#dc2626"),
    "Court Ruling":    ("#eff6ff", "#1e40af", "#2563eb"),
    "Status Update":   ("#fef9c3", "#854d0e", "#ca8a04"),
    "Proposed":        ("#f3e8ff", "#6b21a8", "#9333ea"),
}
DEFAULT_BADGE = ("#f1f5f9", "#334155", "#64748b")

STATUS_EMOJI = {
    "Active": "✅", "Restricted": "🟡", "Banned": "🚫",
    "Pending": "⏳", "None": "ℹ️",
}

def esc(s):
    return (str(s)
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def esc_json(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

def badge_html(change_type):
    bg, txt, bdr = BADGE_COLORS.get(change_type, DEFAULT_BADGE)
    return (f'<span style="background:{bg};color:{txt};border:1px solid {bdr};'
            f'padding:2px 10px;border-radius:20px;font-size:0.72rem;'
            f'font-weight:700;letter-spacing:0.04em;white-space:nowrap;">'
            f'{esc(change_type)}</span>')

def format_date(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%B %-d, %Y")
    except Exception:
        return d

def build_digest_page(digest):
    """Build one /regulatory-updates/YYYY-MM-DD/index.html page."""
    slug        = digest["date"]
    title_str   = digest.get("title", f"STR Regulatory Update — {slug}")
    subtitle    = digest.get("subtitle", "")
    changes     = digest.get("changes", [])
    n           = len(changes)
    total_j     = digest.get("total_jurisdictions", "")
    url         = f"{SITE_URL}/regulatory-updates/{slug}/"
    date_pub    = slug  # ISO 8601

    # Build meta description from top 3 changes
    top3 = [c["headline"] for c in changes[:3]]
    meta_desc = f"{n} STR regulatory changes this week: " + "; ".join(top3[:2]) + "."
    meta_desc = meta_desc[:310]

    # Build keywords
    cities = ", ".join(f"{c['city']} {c['state']}" for c in changes[:6])
    keywords = f"short-term rental regulations {slug[:4]}, vacation rental law changes, {cities}, STR news, Airbnb regulatory update, holiday let rules"

    # ── JSON-LD ──────────────────────────────────────────────────────────
    item_list = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "name": esc_json(c["headline"]),
            "url": f"{SITE_URL}/regulations/{c['jurisdiction_id']}/",
        }
        for i, c in enumerate(changes)
    ]

    graph = [
        {
            "@type": "NewsArticle",
            "@id": url,
            "headline": esc_json(title_str),
            "description": esc_json(meta_desc),
            "datePublished": date_pub,
            "dateModified": date_pub,
            "url": url,
            "inLanguage": "en",
            "author": {
                "@type": "Organization",
                "name": "LawfulStay",
                "url": SITE_URL,
            },
            "publisher": {
                "@type": "Organization",
                "@id": f"{SITE_URL}/#organization",
                "name": "LawfulStay",
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{SITE_URL}/favicon.svg",
                },
            },
            "about": [
                {"@type": "Thing", "name": "Short-Term Rental Regulations"},
                {"@type": "Thing", "name": "Vacation Rental Laws"},
                {"@type": "Thing", "name": "Holiday Let Regulations"},
                {"@type": "Thing", "name": "Airbnb Rules"},
            ],
            "keywords": keywords,
            "isPartOf": {"@id": f"{SITE_URL}/#website"},
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{url}#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "LawfulStay",
                 "item": f"{SITE_URL}/"},
                {"@type": "ListItem", "position": 2, "name": "Regulatory Updates",
                 "item": f"{SITE_URL}/regulatory-updates/"},
                {"@type": "ListItem", "position": 3, "name": title_str,
                 "item": url},
            ],
        },
        {
            "@type": "ItemList",
            "@id": f"{url}#changes",
            "name": esc_json(title_str),
            "numberOfItems": n,
            "itemListElement": item_list,
        },
    ]
    jsonld = json.dumps({"@context": "https://schema.org", "@graph": graph},
                        ensure_ascii=False, indent=2)

    # ── Change cards HTML ────────────────────────────────────────────────
    cards_html = ""
    for c in changes:
        jid       = c.get("jurisdiction_id", "")
        city      = c.get("city", "")
        state     = c.get("state", "")
        headline  = c.get("headline", "")
        summary   = c.get("summary", "")
        ctype     = c.get("change_type", "Update")
        eff       = c.get("effective_date", "")
        src       = c.get("source_url", "")
        conf      = c.get("confidence", "")
        status_n  = c.get("status_new", "")
        emoji     = STATUS_EMOJI.get(status_n, "ℹ️")
        city_url  = f"{SITE_URL}/regulations/{jid}/" if jid else ""

        conf_color = {"high": "#16a34a", "medium": "#ca8a04", "low": "#dc2626"}.get(conf, "#64748b")

        cards_html += f"""
    <article class="change-card" id="{esc(jid)}">
      <div class="card-top">
        <div class="card-meta">
          {badge_html(ctype)}
          <span class="card-confidence" style="color:{conf_color};" title="Data confidence">
            {'★' * {'high':3,'medium':2,'low':1}.get(conf,2)}{'☆' * (3-{'high':3,'medium':2,'low':1}.get(conf,2))} {esc(conf.title()) if conf else ''}
          </span>
        </div>
        <div class="card-location">
          {emoji}
          {'<a class="city-link" href="' + esc(city_url) + '">' + esc(city) + ', ' + esc(state) + '</a>' if city_url else esc(city) + ', ' + esc(state)}
        </div>
      </div>
      <h2 class="card-headline">
        {'<a href="' + esc(city_url) + '">' + esc(headline) + '</a>' if city_url else esc(headline)}
      </h2>
      <p class="card-summary">{esc(summary)}</p>
      <div class="card-footer">
        {('<span class="eff-date">📅 Effective: ' + esc(format_date(eff)) + '</span>') if eff else ''}
        {('<a class="src-link" href="' + esc(src) + '" target="_blank" rel="nofollow noopener">View Source ↗</a>') if src else ''}
      </div>
    </article>"""

    # ── Full HTML ────────────────────────────────────────────────────────
    formatted_date = format_date(slug)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{esc(title_str)} | LawfulStay</title>
  <link rel="canonical" href="{url}" />
  <meta name="description" content="{esc(meta_desc)}" />
  <meta name="keywords" content="{esc(keywords)}" />
  <meta name="robots" content="index, follow" />

  <!-- Open Graph -->
  <meta property="og:site_name" content="LawfulStay" />
  <meta property="og:type" content="article" />
  <meta property="og:title" content="{esc(title_str)}" />
  <meta property="og:description" content="{esc(meta_desc)}" />
  <meta property="og:url" content="{url}" />
  <meta property="og:image" content="{SITE_URL}/og_preview_card.jpg" />
  <meta property="article:published_time" content="{date_pub}" />

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{esc(title_str)}" />
  <meta name="twitter:description" content="{esc(meta_desc)}" />

  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@700;800&display=swap" rel="stylesheet">

  <script type="application/ld+json">
  {jsonld}
  </script>

  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f8fafc; color: #0f172a; line-height: 1.65;
    }}

    /* ── Nav ── */
    .nav {{
      background: #fff; border-bottom: 1px solid #e2e8f0;
      padding: 0 1.5rem; display: flex; align-items: center;
      gap: 1rem; height: 56px; position: sticky; top: 0; z-index: 100;
    }}
    .nav-logo {{
      font-family: "Outfit", sans-serif; font-weight: 800;
      font-size: 1.2rem; color: #0f172a; text-decoration: none;
    }}
    .nav-logo span {{ color: #2563eb; }}
    .nav-back {{
      margin-left: auto; font-size: 0.82rem; color: #2563eb;
      text-decoration: none; font-weight: 600;
    }}
    .nav-back:hover {{ text-decoration: underline; }}

    /* ── Hero ── */
    .hero {{
      background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%);
      color: #fff; padding: 3.5rem 1.5rem 2.5rem;
    }}
    .hero-inner {{ max-width: 780px; margin: 0 auto; }}
    .hero-eyebrow {{
      font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em;
      text-transform: uppercase; color: #93c5fd; margin-bottom: 0.75rem;
    }}
    .hero-title {{
      font-family: "Outfit", sans-serif; font-size: clamp(1.6rem, 4vw, 2.4rem);
      font-weight: 800; line-height: 1.2; margin-bottom: 0.75rem;
    }}
    .hero-subtitle {{ color: #94a3b8; font-size: 0.95rem; margin-bottom: 1.5rem; }}
    .hero-stats {{
      display: flex; gap: 1.5rem; flex-wrap: wrap;
    }}
    .hero-stat {{
      background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12);
      border-radius: 10px; padding: 0.6rem 1.1rem;
    }}
    .hero-stat-num {{ font-size: 1.4rem; font-weight: 800; color: #60a5fa; }}
    .hero-stat-lbl {{ font-size: 0.72rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; }}

    /* ── Breadcrumb ── */
    .breadcrumb {{
      background: #fff; border-bottom: 1px solid #e2e8f0;
      padding: 0.6rem 1.5rem; font-size: 0.8rem; color: #64748b;
    }}
    .breadcrumb a {{ color: #2563eb; text-decoration: none; }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
    .breadcrumb span {{ margin: 0 0.35rem; }}

    /* ── Main layout ── */
    .main {{ max-width: 780px; margin: 2rem auto; padding: 0 1.5rem 4rem; }}

    /* ── Section header ── */
    .section-header {{
      display: flex; align-items: center; gap: 0.6rem;
      margin-bottom: 1.25rem; padding-bottom: 0.75rem;
      border-bottom: 2px solid #e2e8f0;
    }}
    .section-header h2 {{
      font-size: 1rem; font-weight: 700; color: #1e293b;
    }}
    .section-count {{
      background: #2563eb; color: #fff; border-radius: 20px;
      padding: 1px 9px; font-size: 0.72rem; font-weight: 700;
    }}

    /* ── Change cards ── */
    .change-card {{
      background: #fff; border: 1px solid #e2e8f0; border-radius: 14px;
      padding: 1.25rem 1.5rem; margin-bottom: 1rem;
      transition: box-shadow 0.15s ease, border-color 0.15s ease;
    }}
    .change-card:hover {{
      box-shadow: 0 4px 20px rgba(0,0,0,0.08); border-color: #cbd5e1;
    }}
    .card-top {{
      display: flex; justify-content: space-between; align-items: flex-start;
      gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.6rem;
    }}
    .card-meta {{ display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }}
    .card-confidence {{ font-size: 0.72rem; font-weight: 600; }}
    .card-location {{ font-size: 0.8rem; color: #64748b; font-weight: 600; }}
    .city-link {{ color: #2563eb; text-decoration: none; }}
    .city-link:hover {{ text-decoration: underline; }}
    .card-headline {{
      font-size: 1rem; font-weight: 700; color: #0f172a;
      margin-bottom: 0.5rem; line-height: 1.4;
    }}
    .card-headline a {{ color: inherit; text-decoration: none; }}
    .card-headline a:hover {{ color: #2563eb; }}
    .card-summary {{ font-size: 0.875rem; color: #475569; line-height: 1.6; margin-bottom: 0.75rem; }}
    .card-footer {{
      display: flex; gap: 1rem; align-items: center;
      flex-wrap: wrap; font-size: 0.78rem;
    }}
    .eff-date {{ color: #64748b; }}
    .src-link {{
      color: #2563eb; text-decoration: none; font-weight: 600;
      margin-left: auto;
    }}
    .src-link:hover {{ text-decoration: underline; }}

    /* ── Footer CTA ── */
    .cta-box {{
      background: linear-gradient(135deg, #1e3a5f, #0f172a);
      border-radius: 16px; padding: 2rem; text-align: center; margin-top: 2.5rem;
      color: #fff;
    }}
    .cta-box h3 {{ font-family: "Outfit", sans-serif; font-size: 1.3rem; margin-bottom: 0.5rem; }}
    .cta-box p {{ color: #94a3b8; font-size: 0.88rem; margin-bottom: 1.25rem; }}
    .cta-btn {{
      display: inline-block; background: #2563eb; color: #fff;
      padding: 0.65rem 1.5rem; border-radius: 8px; font-weight: 700;
      text-decoration: none; font-size: 0.9rem;
      transition: background 0.15s;
    }}
    .cta-btn:hover {{ background: #1d4ed8; }}
    .cta-btn-ghost {{
      display: inline-block; background: transparent; color: #93c5fd;
      padding: 0.65rem 1.25rem; border-radius: 8px; font-weight: 600;
      text-decoration: none; font-size: 0.88rem; margin-left: 0.5rem;
      border: 1px solid rgba(255,255,255,0.2);
    }}

    /* ── Footer ── */
    .footer {{
      text-align: center; padding: 2rem; font-size: 0.8rem; color: #94a3b8;
      border-top: 1px solid #e2e8f0; background: #fff;
    }}
    .footer a {{ color: #2563eb; text-decoration: none; }}

    @media (max-width: 600px) {{
      .hero {{ padding: 2rem 1rem 1.5rem; }}
      .main {{ padding: 0 1rem 3rem; }}
      .card-top {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>

  <nav class="nav">
    <a class="nav-logo" href="/">Lawful<span>Stay</span></a>
    <a class="nav-back" href="/regulatory-updates/">← All Updates</a>
  </nav>

  <header class="hero">
    <div class="hero-inner">
      <div class="hero-eyebrow">📋 STR Regulatory Updates</div>
      <h1 class="hero-title">{esc(title_str)}</h1>
      <p class="hero-subtitle">{esc(subtitle)}</p>
      <div class="hero-stats">
        <div class="hero-stat">
          <div class="hero-stat-num">{n}</div>
          <div class="hero-stat-lbl">Changes This Week</div>
        </div>
        <div class="hero-stat">
          <div class="hero-stat-num">{total_j}</div>
          <div class="hero-stat-lbl">Jurisdictions Tracked</div>
        </div>
        <div class="hero-stat">
          <div class="hero-stat-num">{formatted_date}</div>
          <div class="hero-stat-lbl">Published</div>
        </div>
      </div>
    </div>
  </header>

  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">LawfulStay</a>
    <span>›</span>
    <a href="/regulatory-updates/">Regulatory Updates</a>
    <span>›</span>
    {esc(formatted_date)}
  </nav>

  <main class="main">
    <div class="section-header">
      <h2>Regulatory Changes</h2>
      <span class="section-count">{n}</span>
    </div>

    {cards_html}

    <div class="cta-box">
      <h3>Stay ahead of every STR regulation change</h3>
      <p>LawfulStay tracks {total_j}+ jurisdictions across 6 continents —
         vacation rentals, holiday lets, Airbnb, VRBO, guest houses & cottage rentals.</p>
      <a class="cta-btn" href="/">Search the Database</a>
      <a class="cta-btn-ghost" href="/regulatory-updates/">View All Updates</a>
    </div>
  </main>

  <footer class="footer">
    <p>
      <a href="/">LawfulStay</a> · The global STR & vacation rental regulations database ·
      <a href="/regulatory-updates/">Regulatory Updates</a> ·
      Data last updated {esc(formatted_date)}
    </p>
  </footer>

</body>
</html>"""


def build_index_page(digests):
    """Build /regulatory-updates/index.html listing all digests."""
    url      = f"{SITE_URL}/regulatory-updates/"
    title    = f"Short-Term Rental Regulatory Updates {YEAR} | LawfulStay"
    desc     = ("Track every short-term rental, vacation rental, holiday let & Airbnb "
                "regulatory change worldwide. LawfulStay publishes weekly digests of "
                "STR law changes, new permits, moratoriums, and court rulings.")
    keywords = ("short-term rental regulatory updates, vacation rental law changes, "
                "Airbnb rule changes, holiday let regulations news, STR news, "
                "short-term rental ordinance tracker, vacation rental regulation tracker")

    graph = [
        {
            "@type": "WebPage",
            "@id": url,
            "url": url,
            "name": title,
            "description": esc_json(desc),
            "inLanguage": "en",
            "isPartOf": {"@id": f"{SITE_URL}/#website"},
            "about": {"@type": "Thing", "name": "Short-Term Rental Regulations"},
        },
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "LawfulStay", "item": f"{SITE_URL}/"},
                {"@type": "ListItem", "position": 2, "name": "Regulatory Updates", "item": url},
            ],
        },
    ]
    jsonld = json.dumps({"@context": "https://schema.org", "@graph": graph},
                        ensure_ascii=False, indent=2)

    # Build digest cards
    cards = ""
    for d in sorted(digests, key=lambda x: x["date"], reverse=True):
        slug   = d["date"]
        dt     = format_date(slug)
        n      = len(d.get("changes", []))
        ttl    = d.get("title", slug)
        sub    = d.get("subtitle", "")
        href   = f"/regulatory-updates/{slug}/"

        # Count by change type
        ctypes = {}
        for c in d.get("changes", []):
            ct = c.get("change_type", "Update")
            ctypes[ct] = ctypes.get(ct, 0) + 1
        type_pills = " ".join(
            f'<span style="font-size:0.7rem;background:#f1f5f9;color:#475569;'
            f'border-radius:20px;padding:2px 8px;border:1px solid #e2e8f0;">'
            f'{esc(k)} ({v})</span>'
            for k, v in sorted(ctypes.items(), key=lambda x: -x[1])
        )

        cards += f"""
    <a class="digest-card" href="{esc(href)}">
      <div class="dc-date">{esc(dt)}</div>
      <div class="dc-title">{esc(ttl)}</div>
      <div class="dc-subtitle">{esc(sub)}</div>
      <div class="dc-pills">{type_pills}</div>
      <div class="dc-footer">
        <span class="dc-count"><strong>{n}</strong> changes</span>
        <span class="dc-arrow">View digest →</span>
      </div>
    </a>"""

    total_changes = sum(len(d.get("changes", [])) for d in digests)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{esc(title)}</title>
  <link rel="canonical" href="{url}" />
  <meta name="description" content="{esc(desc)}" />
  <meta name="keywords" content="{esc(keywords)}" />
  <meta name="robots" content="index, follow" />

  <meta property="og:site_name" content="LawfulStay" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{esc(title)}" />
  <meta property="og:description" content="{esc(desc)}" />
  <meta property="og:url" content="{url}" />
  <meta property="og:image" content="{SITE_URL}/og_preview_card.jpg" />

  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{esc(title)}" />
  <meta name="twitter:description" content="{esc(desc)}" />

  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@700;800&display=swap" rel="stylesheet">

  <script type="application/ld+json">
  {jsonld}
  </script>

  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f8fafc; color: #0f172a; line-height: 1.65;
    }}
    .nav {{
      background: #fff; border-bottom: 1px solid #e2e8f0;
      padding: 0 1.5rem; display: flex; align-items: center;
      gap: 1rem; height: 56px; position: sticky; top: 0; z-index: 100;
    }}
    .nav-logo {{
      font-family: "Outfit", sans-serif; font-weight: 800;
      font-size: 1.2rem; color: #0f172a; text-decoration: none;
    }}
    .nav-logo span {{ color: #2563eb; }}
    .nav-home {{
      margin-left: auto; font-size: 0.82rem; color: #2563eb;
      text-decoration: none; font-weight: 600;
    }}
    .nav-home:hover {{ text-decoration: underline; }}

    .hero {{
      background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%);
      color: #fff; padding: 3.5rem 1.5rem 2.5rem;
    }}
    .hero-inner {{ max-width: 860px; margin: 0 auto; }}
    .hero-eyebrow {{
      font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em;
      text-transform: uppercase; color: #93c5fd; margin-bottom: 0.75rem;
    }}
    h1 {{
      font-family: "Outfit", sans-serif; font-size: clamp(1.7rem, 4vw, 2.6rem);
      font-weight: 800; line-height: 1.2; margin-bottom: 0.75rem;
    }}
    .hero-desc {{ color: #94a3b8; font-size: 0.95rem; max-width: 600px; margin-bottom: 1.5rem; }}
    .hero-stats {{ display: flex; gap: 1.5rem; flex-wrap: wrap; }}
    .hero-stat {{
      background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12);
      border-radius: 10px; padding: 0.6rem 1.1rem;
    }}
    .hero-stat-num {{ font-size: 1.4rem; font-weight: 800; color: #60a5fa; }}
    .hero-stat-lbl {{ font-size: 0.72rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; }}

    .breadcrumb {{
      background: #fff; border-bottom: 1px solid #e2e8f0;
      padding: 0.6rem 1.5rem; font-size: 0.8rem; color: #64748b;
    }}
    .breadcrumb a {{ color: #2563eb; text-decoration: none; }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
    .breadcrumb span {{ margin: 0 0.35rem; }}

    .main {{ max-width: 860px; margin: 2rem auto; padding: 0 1.5rem 4rem; }}

    .section-header {{
      display: flex; align-items: center; gap: 0.6rem;
      margin-bottom: 1.25rem; padding-bottom: 0.75rem;
      border-bottom: 2px solid #e2e8f0;
    }}
    .section-header h2 {{ font-size: 1rem; font-weight: 700; color: #1e293b; }}

    .digest-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 1rem;
    }}
    .digest-card {{
      background: #fff; border: 1px solid #e2e8f0; border-radius: 14px;
      padding: 1.25rem 1.5rem; text-decoration: none; color: inherit;
      display: flex; flex-direction: column; gap: 0.4rem;
      transition: box-shadow 0.15s, border-color 0.15s;
    }}
    .digest-card:hover {{
      box-shadow: 0 4px 20px rgba(0,0,0,0.08); border-color: #2563eb;
    }}
    .dc-date {{ font-size: 0.75rem; color: #2563eb; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }}
    .dc-title {{ font-size: 0.95rem; font-weight: 700; color: #0f172a; line-height: 1.35; }}
    .dc-subtitle {{ font-size: 0.8rem; color: #64748b; }}
    .dc-pills {{ display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.35rem; }}
    .dc-footer {{
      display: flex; justify-content: space-between; align-items: center;
      margin-top: 0.5rem; font-size: 0.8rem; color: #64748b;
    }}
    .dc-count {{ font-size: 0.82rem; }}
    .dc-arrow {{ color: #2563eb; font-weight: 600; font-size: 0.8rem; }}

    .empty {{
      text-align: center; padding: 3rem; color: #94a3b8; font-size: 0.9rem;
    }}

    .cta-box {{
      background: linear-gradient(135deg, #1e3a5f, #0f172a);
      border-radius: 16px; padding: 2rem; text-align: center; margin-top: 2.5rem;
      color: #fff;
    }}
    .cta-box h3 {{ font-family: "Outfit", sans-serif; font-size: 1.3rem; margin-bottom: 0.5rem; }}
    .cta-box p {{ color: #94a3b8; font-size: 0.88rem; margin-bottom: 1.25rem; }}
    .cta-btn {{
      display: inline-block; background: #2563eb; color: #fff;
      padding: 0.65rem 1.5rem; border-radius: 8px; font-weight: 700;
      text-decoration: none; font-size: 0.9rem; transition: background 0.15s;
    }}
    .cta-btn:hover {{ background: #1d4ed8; }}

    .footer {{
      text-align: center; padding: 2rem; font-size: 0.8rem; color: #94a3b8;
      border-top: 1px solid #e2e8f0; background: #fff;
    }}
    .footer a {{ color: #2563eb; text-decoration: none; }}

    @media (max-width: 600px) {{
      .hero {{ padding: 2rem 1rem 1.5rem; }}
      .main {{ padding: 0 1rem 3rem; }}
      .digest-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>

  <nav class="nav">
    <a class="nav-logo" href="/">Lawful<span>Stay</span></a>
    <a class="nav-home" href="/">← Back to Database</a>
  </nav>

  <header class="hero">
    <div class="hero-inner">
      <div class="hero-eyebrow">📋 Weekly Regulatory Digests</div>
      <h1>Short-Term Rental Regulatory Updates</h1>
      <p class="hero-desc">
        The authoritative tracker for vacation rental, holiday let, Airbnb & STR
        law changes worldwide — new ordinances, moratoriums, court rulings, and
        proposed regulations, published weekly.
      </p>
      <div class="hero-stats">
        <div class="hero-stat">
          <div class="hero-stat-num">{len(digests)}</div>
          <div class="hero-stat-lbl">Weekly Digests</div>
        </div>
        <div class="hero-stat">
          <div class="hero-stat-num">{total_changes}</div>
          <div class="hero-stat-lbl">Changes Tracked</div>
        </div>
      </div>
    </div>
  </header>

  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">LawfulStay</a>
    <span>›</span>
    Regulatory Updates
  </nav>

  <main class="main">
    <div class="section-header">
      <h2>All Regulatory Digests</h2>
    </div>

    {'<div class="digest-grid">' + cards + '</div>' if digests else '<div class="empty">No digests yet — check back soon.</div>'}

    <div class="cta-box">
      <h3>Track every STR regulation change</h3>
      <p>617+ jurisdictions across 6 continents — vacation rentals, holiday lets, Airbnb, VRBO & more.</p>
      <a class="cta-btn" href="/">Search the Database →</a>
    </div>
  </main>

  <footer class="footer">
    <p>
      <a href="/">LawfulStay</a> · The global STR & vacation rental regulations database ·
      <a href="/regulatory-updates/">Regulatory Updates</a>
    </p>
  </footer>

</body>
</html>"""


def ping_indexnow(urls):
    """Ping IndexNow (Bing + Yandex, Google picks it up) with new/updated URLs."""
    key = "lawfulstay-indexnow-key"  # Store in /opt/str-tracker/web/{key}.txt
    key_file = WEB / f"{key}.txt"
    if not key_file.exists():
        print(f"  IndexNow: key file not found at {key_file}, skipping ping")
        return

    payload = {
        "host": "lawfulstay.com",
        "key": key,
        "keyLocation": f"https://lawfulstay.com/{key}.txt",
        "urlList": urls,
    }
    try:
        r = requests.post(
            "https://api.indexnow.org/indexnow",
            json=payload, timeout=10,
            headers={"Content-Type": "application/json"}
        )
        print(f"  IndexNow ping: {r.status_code} — {len(urls)} URLs submitted")
    except Exception as e:
        print(f"  IndexNow ping failed: {e}")


def main():
    # Load all digest JSON files
    digests = []
    for f in sorted(DATA_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text())
            digests.append(d)
        except Exception as e:
            print(f"  Error reading {f}: {e}")

    print(f"Found {len(digests)} digest(s) to build")

    new_urls = []
    errors = 0

    for d in digests:
        slug = d.get("date", "")
        if not slug:
            continue
        out_dir = UPDATES_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "index.html"
        try:
            html = build_digest_page(d)
            out_file.write_text(html, encoding="utf-8")
            new_urls.append(f"{SITE_URL}/regulatory-updates/{slug}/")
        except Exception as e:
            print(f"  Error building {slug}: {e}")
            errors += 1

    # Build index page
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    idx_file = UPDATES_DIR / "index.html"
    try:
        html = build_index_page(digests)
        idx_file.write_text(html, encoding="utf-8")
        new_urls.append(f"{SITE_URL}/regulatory-updates/")
        print(f"Generated index page with {len(digests)} digest(s)")
    except Exception as e:
        print(f"  Error building index: {e}")
        errors += 1

    print(f"Generated {len(new_urls) - 1} digest pages + 1 index ({errors} errors)")

    # Ping IndexNow
    if new_urls:
        ping_indexnow(new_urls)

    return errors


if __name__ == "__main__":
    import sys
    sys.exit(main())
