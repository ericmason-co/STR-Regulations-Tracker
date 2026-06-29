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


def build_prompt(region: str, existing: list[dict]) -> str:
    labels = ", ".join(
        f"{j['city']} ({j.get('state') or j.get('country')})" for j in existing
    )
    field_list = ", ".join(FIELD_KEYS)
    return f"""You are the research engine for LawfulStay, a global short-term-rental (STR) \
regulation tracker. Today is {today()}.

Use web search to find NEW, PROPOSED, or MODIFIED short-term-rental / vacation-rental / \
holiday-let regulations and restrictions announced or updated in roughly the last 7 days, \
ANYWHERE in the world, at any level (country, state/province, county, region, city, town, \
or village).

Do TWO things:
1. A GLOBAL DISCOVERY SWEEP for anything new/proposed/modified worldwide in the last week.
2. A focused DEEP DIVE on this region today: {region}.

Favor authoritative sources (government ordinances, bills, official registries) and reputable \
industry trackers (Rent Responsibly, iGMS, Awning, AirDNA). Ignore marketing blogs and listings.

We already track these jurisdictions (avoid duplicating unless there is a genuine change): {labels}

Limit the "changes" array to a maximum of 5 of the most significant changes found. Keep all summaries and compliance notes under 2 sentences to prevent output token truncation.

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
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.load(resp)
    # Concatenate all text blocks from the final assistant message.
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    )


def extract_json(text: str) -> dict:
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
                if k in FIELD_KEYS and v:
                    existing[k] = v
            existing["status"] = normalize_status(existing.get("status", ""))
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

    data["meta"]["last_full_refresh"] = today()
    (ROOT / "data" / "jurisdictions.json").write_text(json.dumps(data, indent=2) + "\n")
    (ROOT / "data" / "policy_updates.json").write_text(json.dumps(changelog, indent=2) + "\n")
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
    raw = call_anthropic(build_prompt(region, existing), api_key)
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
    print(f"Applied: {updated} updated, {added} added.")

    problems = validate()
    if problems:
        print("VALIDATION ISSUES:")
        for p in problems:
            print("  -", p)

    # Rebuild outputs (reuse the existing scripts via import).
    import build_digest
    import export_xlsx

    export_xlsx.main(ROOT / "web" / "Global_STR_Regulations_Comprehensive_Database.xlsx")
    # Sync both data files into the web app so the table and the "latest changes"
    # panel stay current.
    for name in ("jurisdictions.json", "policy_updates.json"):
        (ROOT / "web" / name).write_text((ROOT / "data" / name).read_text())
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
