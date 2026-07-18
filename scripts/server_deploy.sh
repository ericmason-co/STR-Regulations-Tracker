#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# LawfulStay — Server-side autonomous deploy script
# Pulls latest code from GitHub and rebuilds all generated assets.
# Runs on the server with NO dependency on the developer's laptop.
#
# Safe to run as a cron job. Never overwrites live data files.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP=/opt/str-tracker
LOG=/var/log/str-tracker/deploy.log
VENV="$APP/.venv/bin/python"

echo "=== Deploy started: $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"

cd "$APP"

# ── 1. Pull latest code from GitHub (code files only, not live data) ─────────
echo "[1/5] Fetching latest code from GitHub..." | tee -a "$LOG"
git fetch origin main 2>&1 | tee -a "$LOG"

# Checkout only tracked code files — explicitly exclude live data files
# that monitor.py manages on the server.
CODE_FILES=(
  web/index.html
  web/app.js
  web/styles.css
  web/database.js
  web/database.json
  web/favicon.svg
  web/robots.txt
  web/llms.txt
  web/.htaccess
  web/subscribed/index.html
)

SCRIPT_FILES=(
  scripts/monitor.py
  scripts/build_static_pages.py
  scripts/build_hub_pages.py
  scripts/generate_sitemap.py
  scripts/build_digest.py
  scripts/schema.py
  server/request_server.py
)

git checkout origin/main -- "${CODE_FILES[@]}" "${SCRIPT_FILES[@]}" 2>&1 | tee -a "$LOG" || true

# ── 2. Rebuild compressed CSS/JS ──────────────────────────────────────────────
echo "[2/5] Compressing CSS and JS..." | tee -a "$LOG"
if command -v gzip &>/dev/null; then
  gzip -9 -f -k web/styles.css  && mv web/styles.css.gz web/styles.min.css.gz  2>/dev/null || true
  gzip -9 -f -k web/app.js      && mv web/app.js.gz     web/app.min.js.gz       2>/dev/null || true
  gzip -9 -f -k web/jurisdictions.json 2>/dev/null || true
fi

# ── 3. Rebuild all 594 city pages ────────────────────────────────────────────
echo "[3/5] Rebuilding city pages..." | tee -a "$LOG"
"$VENV" scripts/build_static_pages.py 2>&1 | tee -a "$LOG"

# ── 4. Rebuild all 164 hub pages ─────────────────────────────────────────────
echo "[4/5] Rebuilding hub pages..." | tee -a "$LOG"
"$VENV" scripts/build_hub_pages.py 2>&1 | tee -a "$LOG"

# ── 5. Rebuild sitemap ───────────────────────────────────────────────────────
echo "[5/5] Rebuilding sitemap..." | tee -a "$LOG"
"$VENV" scripts/generate_sitemap.py 2>&1 | tee -a "$LOG"

echo "=== Deploy complete: $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
