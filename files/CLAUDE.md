# STR Regulation Tracker — Claude Code Instructions

## What This Project Is
A living database of short-term rental (STR) regulations across 240+ jurisdictions worldwide. Owned by Eric Mason, published via VRInsider and the LinkedIn Vacation Rental Professionals Group (21K members).

Full project history and data schema: see CONTEXT.md in this directory.

## Current Ask
Rebuild this tracker as a modern, maintainable system. Options to consider (discuss with Eric):

1. **Web App** — Searchable/filterable React or Next.js frontend backed by a database
2. **Data Layer** — JSON/SQLite data store with all 240+ jurisdictions, properly structured
3. **Auto-update pipeline** — Web scraping + AI summarization to keep data current
4. **Submission system** — Community contribution form → auto-ingestion
5. **API** — REST endpoint for VRInsider.com to query live

## Data Schema
21 fields per US jurisdiction. See CONTEXT.md for full field list and all existing data.

## Eric's Profile
- CEO-level interim executive, tech-forward, STR/hospitality industry expert
- Founder of VRInsider, moderator of VRP LinkedIn Group
- Needs solutions that are practical, deployable, and maintainable without a full engineering team

## Preferred Stack (if building)
- Python for data/backend
- React or vanilla JS for frontend
- Keep dependencies minimal
- Must be deployable on standard hosting (Vercel, Railway, etc.)
