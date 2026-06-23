"""Build the email digest and LinkedIn post draft from recent changelog entries.

Reads changelog.json, selects entries newer than a cutoff (default: 7 days), and
writes two Markdown artifacts the monitor agent can hand off:
    out/digest_email.md      - plain digest for emailing Eric
    out/linkedin_post.md     - VRP-Group-ready post draft

Usage:
    python3 scripts/build_digest.py [--days N] [--since YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from schema import load_changelog, load_jurisdictions

OUT_DIR = Path(__file__).resolve().parent.parent / "out"

CHANGE_LABELS = {
    "new": "New regulation",
    "update": "Update",
    "status_change": "Status change",
    "repeal": "Repeal / rollback",
    "proposed": "Proposed",
}


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def select_recent(entries: list[dict], cutoff: date) -> list[dict]:
    picked = []
    for e in entries:
        if e.get("jurisdiction_id") == "seed":
            continue
        try:
            if _parse(e["date"]) >= cutoff:
                picked.append(e)
        except (KeyError, ValueError):
            continue
    return sorted(picked, key=lambda e: e["date"], reverse=True)


def build_email(entries: list[dict], cutoff: date, total: int) -> str:
    today = date.today().isoformat()
    lines = [
        "# STR Regulation Tracker - Weekly Digest",
        f"_Generated {today} | {len(entries)} change(s) since {cutoff.isoformat()} | "
        f"{total} jurisdictions tracked_",
        "",
    ]
    if not entries:
        lines += [
            "No new regulatory changes detected this cycle. The tracker re-verified "
            "all monitored jurisdictions and found no material updates.",
        ]
        return "\n".join(lines)

    for e in entries:
        label = CHANGE_LABELS.get(e.get("change_type", ""), e.get("change_type", ""))
        lines.append(f"## {e.get('jurisdiction_label', 'Unknown')} - {label}")
        lines.append(e.get("summary", ""))
        if e.get("old_value") or e.get("new_value"):
            lines.append(
                f"- **Changed:** {e.get('field','')}: "
                f"{e.get('old_value','-')} -> {e.get('new_value','-')}"
            )
        if e.get("effective_date"):
            lines.append(f"- **Effective:** {e['effective_date']}")
        if e.get("source_url"):
            lines.append(f"- **Source:** {e['source_url']}")
        lines.append(f"- **Confidence:** {e.get('confidence','-')}")
        lines.append("")
    return "\n".join(lines)


def build_linkedin(entries: list[dict]) -> str:
    if not entries:
        return (
            "No major STR regulatory changes this week across the markets we track. "
            "Quiet weeks matter too - stability is signal. #STRRegulations #VRP"
        )
    headline_count = len(entries)
    bullets = []
    for e in entries[:6]:
        loc = e.get("jurisdiction_label", "")
        summary = e.get("summary", "").rstrip(".")
        bullets.append(f"- {loc}: {summary}.")
    body = "\n".join(bullets)
    return (
        f"STR regulation moves fast. {headline_count} update(s) worth knowing this week:\n\n"
        f"{body}\n\n"
        "Full details and 240+ jurisdictions in the Global STR Regulation Tracker. "
        "What's changing in your market? Drop it below.\n\n"
        "#STRRegulations #ShortTermRentals #VacationRentals #VRP"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--since", type=str, default=None)
    args = ap.parse_args()

    cutoff = _parse(args.since) if args.since else date.today() - timedelta(days=args.days)

    changelog = load_changelog()
    total = len(load_jurisdictions()["jurisdictions"])
    recent = select_recent(changelog["entries"], cutoff)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "digest_email.md").write_text(build_email(recent, cutoff, total))
    (OUT_DIR / "linkedin_post.md").write_text(build_linkedin(recent))
    print(
        f"Wrote out/digest_email.md and out/linkedin_post.md "
        f"({len(recent)} recent change(s))."
    )


if __name__ == "__main__":
    main()
