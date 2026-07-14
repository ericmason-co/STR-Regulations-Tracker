"""Server-side daily monitor for the LawfulStay STR Regulation Tracker.

Ported from AGENT.md to run as a cron job on the droplet (no Claude app needed).
Each run:
  1. Picks the day's focus region (rotating) + always does a global discovery sweep.
  2. Calls the Anthropic API with the built-in web_search tool to find NEW, PROPOSED,
     or MODIFIED short-term-rental regulations worldwide in the last ~48h.
  3. Parses the model's strict-JSON output, applies changes to data/jurisdictions.json,
     and appends entries to data/changelog.json (de-duplicated).
  4. Validates, rebuilds the XLSX, syncs the web copy.
  5. Builds the email digest + LinkedIn draft and (if there were changes, or it's Monday)
     emails the digest via SMTP.

Config comes from /etc/lawfulstay/monitor.env (ANTHROPIC_API_KEY, SMTP_*, MAIL_*).
Run:  ./.venv/bin/python scripts/monitor.py [--dry-run] [--region NAME] [--days N]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import smtplib
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from schema import (  # noqa: E402
    FIELDS,
    VALID_STATUSES,
    continent_for,
    load_changelog,
    load_jurisdictions,
    validate,
)


def normalize_status(raw: str) -> str:
    """Coerce free-text status into one of the five allowed enum values.

    The model sometimes returns descriptive status text ("Approved June 9...");
    map it to the nearest valid bucket so the web app badges/filters stay clean.
    """
    if not raw:
        return "Pending"
    if raw in VALID_STATUSES:
        return raw
    s = raw.lower()
    if any(w in s for w in ("ban", "prohibit", "phase-out", "phase out", "eliminat")):
        return "Banned"
    if any(w in s for w in ("propos", "draft", "pending", "consult", "bill", "introduced",
                            "in principle", "under review", "comment")):
        return "Pending"
    if any(w in s for w in ("repeal", "rescind", "struck down", "overturn")):
        return "None"
    if any(w in s for w in ("restrict", "cap", "limit", "moratorium", "license required",
                            "permit required")):
        return "Restricted"
    if any(w in s for w in ("adopt", "approv", "enact", "effect", "active", "in force",
                            "legislat", "confirm", "registration", "passed")):
        return "Active"
    return "Pending"



# String fields that must never be boolean/int/None in the JSON output.
_STRING_FIELDS = [
    "city", "state", "country", "status", "license_required",
    "tax_registration_required", "fees", "primary_residence_required",
    "rental_day_cap", "occupancy_limit", "tax_rate", "zoning_restrictions",
    "min_stay", "density_rules", "insurance_required", "platform_obligations",
    "compliance_notes", "effective_date", "key_notes", "penalties",
    "additional_context", "source",
]

def coerce_strings(record: dict) -> dict:
    """Ensure every string-typed field is actually a str, not a bool/int/None.

    The Claude model occasionally emits JSON booleans (true/false) for fields
    like license_required or primary_residence_required.  A bare Python True
    has no .trim() method, which crashes the JS renderList() loop and silently
    hides every row after the first bad record.  Convert here so bad model
    output can never reach the browser.
    """
    for key in _STRING_FIELDS:
        val = record.get(key)
        if val is None or val == "":
            continue  # leave empties alone — UI treats them as Unknown
        if isinstance(val, bool):
            record[key] = "Yes" if val else "No"
        elif not isinstance(val, str):
            record[key] = str(val)
    return record

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("MONITOR_MODEL", "claude-sonnet-4-6")

# Rotating regional focus by weekday (Mon=0 .. Sun=6). Weekend = re-verify existing.
REGION_BY_WEEKDAY = {
    0: "United States & Canada (states, counties, cities, towns)",
    1: "Europe & the United Kingdom (national, regional, municipal)",
    2: "Asia-Pacific (Japan, Australia, New Zealand, Southeast Asia, etc.)",
    3: "Latin America & the Caribbean",
    4: "Africa & the Middle East",
    5: "Re-verify existing tracked jurisdictions with the oldest data",
    6: "Re-verify existing tracked jurisdictions with the oldest data",
}

FIELD_KEYS = [k for k, _ in FIELDS]


def today() -> str:
    return dt.date.today().isoformat()


def build_prompt(region: str, existing: list[dict], recent: list[dict] | None = None) -> str:
    # Only include a representative subset of jurisdictions to keep prompt size manageable.
    # Prioritise those relevant to the day's region focus, then sample others.
    region_lower = region.lower()
    def is_relevant(j):
        state = (j.get("state") or "").lower()
        country = (j.get("country") or "").lower()
        city = (j.get("city") or "").lower()
        return (region_lower in state or region_lower in country or
                region_lower in city or
                any(w in region_lower for w in [state, country]) and state)
    relevant = [j for j in existing if is_relevant(j)]
    # If we have fewer than 60 relevant, pad with a random sample of others
    import random
    others = [j for j in existing if not is_relevant(j)]
    random.shuffle(others)
    sample = relevant + others[:max(0, 80 - len(relevant))]
    labels = ", ".join(
        f"{j['city']} ({j.get('state') or j.get('country')})" for j in sample[:80]
    ) + (f" ... and {len(existing) - 80} more tracked globally" if len(existing) > 80 else "")
    field_list = ", ".join(FIELD_KEYS)
    recent = recent or []
    recent_block = "\n".join(
        f"- {r.get('jurisdiction_label', '')} | effective {r.get('effective_date', '?')} | "
        f"{(r.get('summary', '') or '')[:110]}"
        for r in recent[:25]
    ) or "(none yet)"
    return f"""You are the research engine for LawfulStay, a global short-term-rental (STR) \
regulation tracker. Today is {today()}.

Search the OPEN WEB BROADLY — news outlets, government gazettes, council/legislature pages, \
legal and industry coverage — for short-term-rental / vacation-rental / holiday-let regulation \
AND closely related topics: housing policy, tourism / occupancy / visitor / lodging taxes and \
levies, zoning, licensing and registration schemes, platform (Airbnb/Vrbo) regulation, night/day \
caps, primary-residence rules, bans, moratoria, and enforcement actions. Look ANYWHERE in the \
world, at any level (country, state/province, county, region, city, town, or village). Do NOT \
limit yourself to a fixed set of sites — cast a wide net to find the news, then cite the \
primary/official source for each item. Ignore marketing and listing-spam pages.

RECENCY WINDOW (mirror a Google-News "past 24 hours" search) — report an item ONLY if it meets at \
least one of these, relative to today ({today()}):
  (a) it was ANNOUNCED, REPORTED, or PUBLISHED in credible news within the PAST 24 HOURS — a new \
      regulatory announcement, vote, signing, adoption, proposal, ruling, enforcement action, or a \
      fresh news story/press release about a short-term / vacation-rental regulation; OR
  (b) the regulation/rule TAKES EFFECT within the NEXT 48 HOURS.
Capture recent announcements and new stories, exactly like a 24-hour news search. \
DATE DISCIPLINE IS CRITICAL: for each candidate, find and verify the date of the NEWEST source. \
If you cannot find coverage dated within the last 24 hours (and it is not effective within 48h), \
DROP the item — no matter how relevant. Do NOT include an item based on a months-old article. \
Put the verified publication/action date at the start of each "summary".

Also specifically scan today's focus region for qualifying items: {region}.

RUN A COMPREHENSIVE NEWS SWEEP — emulate a Google-News "past 24 hours" search for this topic. \
Run SEVERAL distinct web searches (aim for 8-12) with varied wording and languages so nothing is \
missed, for example:
  - short-term rental regulation / ban / ordinance / license / cap / moratorium
  - vacation rental law / rules / crackdown / ruling / fine
  - "holiday let" / "holiday rental" / "short-term let" regulation (UK, Ireland, Australia, NZ)
  - Airbnb regulation / ban / crackdown / delisting / court ruling
  - Vrbo / Booking.com short-term rental rules
  - tourist accommodation / tourist rental registration or licensing (Europe)
  - visitor levy / tourist tax / occupancy tax on short-term rentals
  - STR registration scheme / primary-residence rule / night cap / zoning change
  - local-language terms where relevant: "meuble de tourisme" (France), "minpaku" (Japan), \
    "vivienda de uso turistico" / "VUT" (Spain), "alojamento local" (Portugal), "affitti brevi" (Italy)
Prioritize NEWS results (press releases, council/legislature agendas, local newspapers, industry \
news wires) published in the last 24 hours, and pull EVERY qualifying item you find — not just the \
first few.

SOURCE AUTHORITY & NO DUPLICATES — the same regulatory action will often appear across several \
outlets. Report each distinct action exactly ONCE, and cite the SINGLE most authoritative source, \
in this priority:
  1. Official government / legislature / city-council / ordinance / registry / court page
  2. Government press release or official gazette
  3. Established news outlet or newswire (Reuters, AP, major local paper)
  4. Reputable industry tracker
  5. (never) blogs, listing pages, marketing/SEO content
Never emit two entries for the same action just because it appeared on different sites — \
consolidate into one entry with the best source_url. Treat two reports as the SAME action if they \
concern the same jurisdiction and the same effective date or the same vote/ordinance.

ALREADY REPORTED — these are already in the Market Updates feed. Do NOT report them again; only \
surface something genuinely NEW or a further development beyond what is listed here:
{recent_block}

We already track these jurisdictions (avoid duplicating unless there is a genuine change): {labels}

Report ALL qualifying changes you find (up to 12). Do not stop at a handful — if the news sweep \
surfaces 8-10 distinct qualifying items, include them all.

CRITICAL — for EVERY change you report, you MUST populate these fields in the "fields" object:
- "compliance_notes": 2-4 sentence plain-English summary of what the current rules require and what hosts must do to stay compliant. Rewrite this fully whenever any part of the regulation changes — do not leave it as the old text.
- "key_notes": The 2-4 most critical facts a host must know (permit requirements, night/day cap, primary-residence rule, tax rate, enforcement penalties). Use concise bullet-style prose.
- "source": The direct URL to the official government page, ordinance, or bill. Never leave blank.
- "penalties": Fines or enforcement consequences if known (e.g. "Up to ,000 per violation"). Use "Not specified" if genuinely not found.

Keep the top-level "summary" field under 2 sentences.

Return ONLY a single JSON object, no prose, no markdown fences, with this exact shape:
{{
  "changes": [
    {{
      "match": "<id or 'City, State/Country' of an existing tracked jurisdiction, or null if new>",
      "is_new": <true|false>,
      "change_type": "new|update|status_change|repeal|proposed",
      "jurisdiction_label": "City, State/Country",
      "region": "US|International",
      "country": "...",
      "state": "...",
      "city": "...",
      "summary": "1-2 sentence plain-English description of what changed",
      "field": "which of [{field_list}] changed, or 'multiple'",
      "old_value": "prior value if known, else ''",
      "new_value": "new value",
      "effective_date": "when it takes/took effect",
      "source_url": "primary source link",
      "confidence": "high|medium|low",
      "fields": {{ "any of the 21 schema fields you can source": "value" }}
    }}
  ]
}}

In the "fields" object, the "status" value MUST be exactly one of: Active, Restricted, Banned, \
Pending, None (use Pending for proposed/draft rules, Active for adopted/enacted ones). Put the \
descriptive wording in "summary" or "compliance_notes", never in "status".

If you find no credible changes, return {{"changes": []}}. Never invent regulations; if a source \
is ambiguous use confidence "low" and say so in the summary."""


def call_anthropic(prompt: str, api_key: str, max_searches: int = 8,
                   max_tokens: int = 8000) -> str:
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}
        ],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    # Retry up to 2 times on timeout; use a 480-second ceiling (8 min)
    last_exc = None
    for _attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=480) as resp:
                data = json.load(resp)
            last_exc = None
            break
        except TimeoutError as exc:
            last_exc = exc
            print(f"Anthropic API timeout (attempt {_attempt+1}/2), retrying...", flush=True)
        except Exception as exc:
            raise
    if last_exc is not None:
        raise last_exc
    # Concatenate all text blocks from the final assistant message.
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    )


def extract_json(text: str) -> dict:
    """Robustly pull the JSON object out of the model output, tolerating markdown
    fences or trailing prose after the closing brace (which broke a naive slice)."""
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text, i)          # parse first complete object
            if isinstance(obj, dict) and "changes" in obj:
                return obj
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)
    # Fallback to the old first-to-last slice if no clean object found.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model output:\n{text[:500]}")
    return json.loads(text[start : end + 1])


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def find_existing(data: dict, match: str | None, label: str):
    if not match:
        return None
    for j in data["jurisdictions"]:
        if j["id"] == match:
            return j
    target = (label or match or "").lower()
    for j in data["jurisdictions"]:
        jl = f"{j.get('city','')}, {j.get('state') or j.get('country','')}".lower()
        if jl == target:
            return j
    return None


def find_by_geo(data: dict, state: str, city: str, country: str):
    """Match an existing record by normalized geography, regardless of the model's
    is_new flag. Prevents duplicate records for places we already track."""
    tc, ts, tk = _norm(city), _norm(state), _norm(country)
    national = tc in ("", "national", "nationwide")
    for j in data["jurisdictions"]:
        jc, jk = _norm(j.get("city")), _norm(j.get("country"))
        if national:
            # National-level rule: match on country when neither has a real city.
            if jk == tk and jc in ("", "national", "nationwide"):
                return j
        elif jc == tc and (_norm(j.get("state")) == ts or jk == tk):
            return j
    return None


def make_id(region: str, state: str, city: str, country: str) -> str:
    import re

    def slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")

    prefix = "us" if region == "US" else "intl"
    geo = state if region == "US" else country
    return f"{prefix}-{slug(geo)}-{slug(city)}"


_EFF_FMTS = ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%m/%d/%Y", "%d %B %Y")


def _tl_label(s):
    # city + state/region (first two comma parts) so "Austin, Texas" == "Austin, Texas, USA"
    parts = [p.strip() for p in (s or "").split(",")]
    base = " ".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "")
    return " ".join(base.lower().split())


def _tl_eff(s):
    import datetime as _dt
    import re as _re
    s = (s or "").strip()
    if not s or s.lower() in ("unknown", "not specified", "n/a", "none", "current"):
        return ""
    for f in _EFF_FMTS:
        try:
            return _dt.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    m = _re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return m.group(0) if m else ""


def dedup_timeline(entries):
    """Keep the Market Updates feed clean. Two passes, each keeping the newest/fullest:
      1) one entry per jurisdiction per DAY (collapses same-day repeats even when the
         change_type or effective-date wording differs);
      2) merge same jurisdiction + same EFFECTIVE DATE across days (an upcoming rule
         re-caught each day by the 48h window)."""
    def score(e):
        return (len(e.get("summary", "") or ""), 1 if e.get("source_url") else 0)

    def collapse(items, keyfn):
        keep, order = {}, []
        for e in items:  # newest-first order preserved
            k = keyfn(e)
            if k not in keep:
                keep[k] = e
                order.append(k)
            elif score(e) > score(keep[k]):
                keep[k] = e
        return [keep[k] for k in order]

    # Pass 1: one per jurisdiction per day.
    out = collapse(entries, lambda e: (_tl_label(e.get("jurisdiction_label", "")), e.get("date", "")))

    # Pass 2: collapse the same rule re-reported on different days (by effective date).
    def eff_key(e):
        eff = _tl_eff(e.get("effective_date", ""))
        return ("eff", _tl_label(e.get("jurisdiction_label", "")), eff) if eff else ("uniq", id(e))

    return collapse(out, eff_key)


def apply_changes(changes: list[dict]) -> tuple[list[dict], int, int]:
    """Apply changes to jurisdictions.json + changelog.json. Returns (entries, updated, added)."""
    data = load_jurisdictions()
    changelog = load_changelog()
    new_entries: list[dict] = []
    updated = added = 0

    for ch in changes:
        label = ch.get("jurisdiction_label", "")
        fields = ch.get("fields", {}) or {}
        # Always try to match an existing record (by id/label, then by geography),
        # ignoring the model's is_new flag — it is only a hint and is often wrong.
        existing = find_existing(data, ch.get("match"), label)
        if existing is None:
            existing = find_by_geo(
                data,
                ch.get("state", ""),
                ch.get("city", "") or fields.get("city", ""),
                ch.get("country", ""),
            )

        if existing:
            for k, v in fields.items():
                # Update when model explicitly provides a value (even empty string = intentional clear).
                # Only skip when value is None, which means the model did not address that field.
                if k in FIELD_KEYS and v is not None:
                    existing[k] = v if v != "" else existing.get(k, "Unknown")
            existing["status"] = normalize_status(existing.get("status", ""))
            coerce_strings(existing)
            existing["last_changed"] = today()
            existing["last_checked"] = today()
            jid = existing["id"]
            updated += 1
        else:
            region = ch.get("region", "International")
            state = ch.get("state", "")
            country = ch.get("country", "Unknown")
            # City can be empty for national/state-level rules; fall back sensibly.
            city = ch.get("city", "") or fields.get("city", "") or state or "National"
            jid = make_id(region, state, city, country)
            if any(j["id"] == jid for j in data["jurisdictions"]):
                jid = f"{jid}-{today()}"
            record = {"id": jid, "region": region, "continent": continent_for(country, region),
                      "country": country, "last_checked": today(), "last_changed": today()}
            for k in FIELD_KEYS:
                record[k] = fields.get(k) or ch.get(k) or "Unknown"
            record["state"] = state or "National"
            record["city"] = city
            record["status"] = normalize_status(record.get("status", ""))
            # Seed an active_listings estimate so new locations always feed the
            # "Rentals Monitored" KPI (15k for state/national-level, 1.8k otherwise).
            _c = (record["city"] or "").lower()
            record["active_listings"] = (
                15000 if (_c in ("national", "nationwide", "state level", "state")
                          or record["city"] == record["state"]) else 1800
            )
            coerce_strings(record)
            data["jurisdictions"].append(record)
            added += 1

        entry = {
            "date": today(),
            "jurisdiction_id": jid,
            "jurisdiction_label": label,
            "change_type": ch.get("change_type", "update"),
            "field": ch.get("field", "multiple"),
            "summary": ch.get("summary", ""),
            "old_value": ch.get("old_value", ""),
            "new_value": ch.get("new_value", ""),
            "effective_date": ch.get("effective_date", ""),
            "source_url": ch.get("source_url", ""),
            "confidence": ch.get("confidence", "low"),
        }
        changelog["entries"].insert(0, entry)
        new_entries.append(entry)

    deduped = dedup_timeline(changelog.get("entries", []))
    changelog["entries"] = deduped
    data["meta"]["last_full_refresh"] = today()
    data["timeline"] = deduped
    (ROOT / "data" / "jurisdictions.json").write_text(json.dumps(data, indent=2) + "\n")
    (ROOT / "data" / "timeline.json").write_text(json.dumps(changelog, indent=2) + "\n")
    return new_entries, updated, added


def send_email(subject: str, body_md: str) -> str:
    host = os.environ.get("SMTP_HOST")
    if not host:
        return "SMTP not configured — skipped email (digest saved to out/digest_email.md)."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("MAIL_FROM", os.environ.get("SMTP_USER", ""))
    msg["To"] = os.environ.get("MAIL_TO", "ericmason.co@gmail.com")
    msg.set_content(body_md)
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    return f"Emailed digest to {msg['To']}."



def notify_subscribers(entries: list[dict]) -> None:
    """Send targeted alert emails to subscribers whose jurisdiction changed."""
    if not entries:
        return
    db = Path('/opt/str-tracker/data/users.db')
    if not db.exists():
        print('No users.db found — skipping subscriber notifications.')
        return
    host = os.environ.get('SMTP_HOST')
    if not host:
        print('SMTP not configured — skipping subscriber notifications.')
        return

    import sqlite3
    conn = sqlite3.connect(db)
    c = conn.cursor()
    notified = 0

    for entry in entries:
        jid = entry.get('jurisdiction_id', '')
        jlabel = entry.get('jurisdiction_label', '')
        summary = entry.get('summary', '')
        change_type = entry.get('change_type', 'update')
        source_url = entry.get('source_url', '')
        new_value = entry.get('new_value', '')

        # Find subscribers by jurisdiction_id or label match
        c.execute(
            "SELECT DISTINCT u.email FROM alert_subscriptions a "
            "JOIN users u ON u.id = a.user_id "
            "WHERE a.jurisdiction_id = ? OR LOWER(a.jurisdiction_label) = LOWER(?)",
            (jid, jlabel)
        )
        subscribers = [row[0] for row in c.fetchall()]
        if not subscribers:
            continue

        print(f'Notifying {len(subscribers)} subscriber(s) for {jlabel}...')
        for email in subscribers:
            try:
                msg = EmailMessage()
                msg['Subject'] = f'LawfulStay Alert: {jlabel} STR regulations changed'
                msg['From'] = os.environ.get('MAIL_FROM', os.environ.get('SMTP_USER', ''))
                msg['To'] = email
                body = (
                    'A regulation change has been detected for ' + jlabel + '.\n\n'
                    + 'Change type: ' + change_type + '\n'
                    + 'Summary: ' + summary + '\n'
                )
                if new_value:
                    body += 'New value: ' + new_value + '\n'
                if source_url:
                    body += 'Source: ' + source_url + '\n'
                body += (
                    'View the full details at: https://lawfulstay.com\n\n'
                    + 'You are receiving this because you subscribed to alerts for ' + jlabel + ' on LawfulStay.com.\n'
                    + 'To unsubscribe, reply to this email.'
                )
                msg.set_content(body)
                port = int(os.environ.get('SMTP_PORT', '587'))
                with smtplib.SMTP(host, port, timeout=30) as s:
                    s.starttls()
                    s.login(os.environ['SMTP_USER'], os.environ['SMTP_PASS'])
                    s.send_message(msg)
                notified += 1
            except Exception as e:
                print(f'Failed to notify {email}: {e}', flush=True)

    conn.close()
    print(f'Subscriber notifications sent: {notified}')

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="search + print, do not write data")
    ap.add_argument("--region", default=None)
    ap.add_argument("--days", type=int, default=2, help="digest look-back window")
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set (source /etc/lawfulstay/monitor.env).")

    region = args.region or REGION_BY_WEEKDAY[dt.date.today().weekday()]
    print(f"[{today()}] LawfulStay monitor — focus: {region}")

    existing = load_jurisdictions()["jurisdictions"]
    recent = load_changelog().get("entries", [])
    raw = call_anthropic(build_prompt(region, existing, recent), api_key,
                         max_searches=12, max_tokens=16000)
    try:
        result = extract_json(raw)
    except ValueError as e:
        sys.exit(f"Could not parse model output: {e}")
    changes = result.get("changes", [])
    print(f"Model reported {len(changes)} candidate change(s).")

    if args.dry_run:
        print(json.dumps(changes, indent=2))
        return

    entries, updated, added = apply_changes(changes)
    notify_subscribers(entries)
    print(f"Applied: {updated} updated, {added} added.")

    problems = validate()
    type_errors = [p for p in problems if "expected str" in p]
    warnings    = [p for p in problems if "expected str" not in p]
    if type_errors:
        print("BLOCKING TYPE ERRORS — auto-repairing before web sync:")
        for p in type_errors:
            print("  REPAIR:", p)
        import json as _json
        from schema import FIELDS as _FIELDS
        _data = _json.loads((ROOT / "data" / "jurisdictions.json").read_text())
        _repaired = 0
        for _rec in _data.get("jurisdictions", []):
            for _key, _ in _FIELDS:
                _val = _rec.get(_key)
                if _val is not None and not isinstance(_val, str):
                    _rec[_key] = "Yes" if (_val is True) else ("No" if (_val is False) else str(_val))
                    _repaired += 1
        (ROOT / "data" / "jurisdictions.json").write_text(_json.dumps(_data, indent=2) + "\n")
        print(f"  Auto-repaired {_repaired} type error(s) in data/jurisdictions.json.")
    if warnings:
        print("Validation warnings (non-blocking):")
        for p in warnings:
            print("  -", p)

    # Rebuild outputs (reuse the existing scripts via import).
    import build_digest
    import export_xlsx

    export_xlsx.main(ROOT / "web" / "Global_STR_Regulations_Comprehensive_Database.xlsx")
    # Sync both data files into the web app so the table and the "latest changes"
    # panel stay current.
    for name in ("jurisdictions.json", "timeline.json"):
        (ROOT / "web" / name).write_text((ROOT / "data" / name).read_text())
        if name == "jurisdictions.json":
            import gzip, shutil
            with open(ROOT / "web" / name, "rb") as f_in, gzip.open(str(ROOT / "web" / (name + ".gz")), "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
            print("Re-compressed jurisdictions.json.gz", flush=True)
    # Re-minify JS and CSS so minified files stay current
    try:
        import jsmin, rcssmin
        js = (ROOT / "web" / "app.js").read_text()
        (ROOT / "web" / "app.min.js").write_text(jsmin.jsmin(js))
        import subprocess
        subprocess.run(["gzip", "-kf", str(ROOT / "web" / "app.min.js")])
        css = (ROOT / "web" / "styles.css").read_text()
        (ROOT / "web" / "styles.min.css").write_text(rcssmin.cssmin(css))
        subprocess.run(["gzip", "-kf", str(ROOT / "web" / "styles.min.css")])
        print("Re-minified and compressed JS/CSS", flush=True)
    except Exception as e:
        print("JS/CSS minification failed:", e, flush=True)
    # Regenerate static HTML pages for all jurisdictions
    try:
        import subprocess
        result = subprocess.run(["python3", "/opt/str-tracker/scripts/build_static_pages.py"], capture_output=True, text=True)
        print(result.stdout.strip(), flush=True)
        if result.returncode != 0 and result.stderr:
            print("build_static_pages stderr:", result.stderr[:400], flush=True)
    except Exception as e:
        print("Static page generation failed:", e, flush=True)
    # Regenerate state/country hub pages (must run after static pages)
    try:
        result = subprocess.run(["python3", "/opt/str-tracker/scripts/build_hub_pages.py"], capture_output=True, text=True)
        print(result.stdout.strip(), flush=True)
        if result.returncode != 0 and result.stderr:
            print("build_hub_pages stderr:", result.stderr[:400], flush=True)
    except Exception as e:
        print("Hub page generation failed:", e, flush=True)
    # Regenerate sitemap (includes city pages + hub pages)
    try:
        result = subprocess.run(["python3", "/opt/str-tracker/scripts/generate_sitemap.py"], capture_output=True, text=True)
        print(result.stdout.strip(), flush=True)
    except Exception as e:
        print("Sitemap generation failed:", e, flush=True)
    # Ping search engines via IndexNow
    try:
        import urllib.request, json as _json
        _key = "83ca2ff4eaa346079f116276df3d47ad"
        _data = _json.load(open(ROOT / "data" / "jurisdictions.json"))
        # City pages + hub pages from sitemap
        _city_urls = ["https://lawfulstay.com/regulations/" + j["id"] + "/" for j in _data["jurisdictions"] if j.get("id")]
        _hub_meta_path = ROOT / "data" / "hub_pages.json"
        _hub_urls = []
        if _hub_meta_path.exists():
            import json as _jj
            _hmeta = _jj.load(open(_hub_meta_path))
            _hub_urls = (
                ["https://lawfulstay.com/regulations/state/" + s + "/" for s, _ in _hmeta.get("state_pages", [])] +
                ["https://lawfulstay.com/regulations/country/" + c + "/" for c, _ in _hmeta.get("country_pages", [])]
            )
        _urls = ["https://lawfulstay.com/"] + _city_urls + _hub_urls
        _payload = _json.dumps({"host": "lawfulstay.com", "key": _key, "keyLocation": "https://lawfulstay.com/" + _key + ".txt", "urlList": _urls}).encode()
        _req = urllib.request.Request("https://api.indexnow.org/indexnow", data=_payload, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        with urllib.request.urlopen(_req, timeout=30) as _r:
            print(f"IndexNow: {_r.status} — {len(_urls)} URLs submitted", flush=True)
    except Exception as e:
        print("IndexNow ping failed:", e, flush=True)
    sys.argv = ["build_digest.py", "--days", str(args.days)]
    build_digest.main()

    is_monday = dt.date.today().weekday() == 0
    if entries or is_monday:
        subject = f"LawfulStay — Daily Digest {today()}"
        body = (ROOT / "out" / "digest_email.md").read_text()
        print(send_email(subject, body))
    else:
        print("No changes and not Monday — skipping email.")
    print("LinkedIn draft: out/linkedin_post.md")
    print("Done.")


if __name__ == "__main__":
    main()
