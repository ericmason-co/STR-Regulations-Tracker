#!/usr/bin/env python3
"""LawfulStay 'request a location' endpoint.

Tiny stdlib HTTP service (no dependencies). Listens on 127.0.0.1:8090; nginx
proxies /api/request-location to it. On a valid submission it appends to a JSONL
log and emails Eric (reusing the monitor's SMTP config in /etc/lawfulstay/monitor.env).

POST /api/request-location  (JSON)
  { "location": "City, State/Country" (required),
    "email": "optional@example.com",
    "notes": "optional free text",
    "website": ""   # honeypot — must be empty }
  -> 200 { "ok": true, "message": "..." }  |  4xx { "ok": false, "error": "..." }
"""
from __future__ import annotations

import json
import os
import re
import smtplib
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = Path("/opt/str-tracker/data/location_requests.jsonl")
ENV_FILE = "/etc/lawfulstay/monitor.env"
MAX_LOC = 200
_last_hit: dict[str, float] = {}


def load_env(path=ENV_FILE):
    env = {}
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    except FileNotFoundError:
        pass
    return env


ENV = load_env()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def send_email(loc, email, notes, ip, subscribe=False):
    host = ENV.get("SMTP_HOST")
    if not host:
        return
    msg = EmailMessage()
    msg["Subject"] = f"LawfulStay: location request — {loc[:80]}"
    msg["From"] = ENV.get("MAIL_FROM", ENV.get("SMTP_USER", ""))
    msg["To"] = ENV.get("MAIL_TO", "ericmason.co@gmail.com")
    msg.set_content(
        "New location request via lawfulstay.com:\n\n"
        f"Location: {loc}\n"
        f"Requester email: {email or '(none)'}\n"
        f"Notes: {notes or '(none)'}\n"
        f"Subscribe on Add: {'Yes' if subscribe else 'No'}\n"
        f"IP: {ip}\n"
        f"Time: {datetime.now(timezone.utc).isoformat()}\n"
    )
    with smtplib.SMTP(host, int(ENV.get("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        s.login(ENV["SMTP_USER"], ENV["SMTP_PASS"])
        s.send_message(msg)


def send_monitor_request_email(airbnb_id, vrbo_id, email, ip):
    host = ENV.get("SMTP_HOST")
    if not host:
        return
    msg = EmailMessage()
    msg["Subject"] = f"LawfulStay: listing monitor request — {email}"
    msg["From"] = ENV.get("MAIL_FROM", ENV.get("SMTP_USER", ""))
    msg["To"] = ENV.get("MAIL_TO", "ericmason.co@gmail.com")
    msg.set_content(
        "New listing monitor request via lawfulstay.com:\n\n"
        f"Email: {email}\n"
        f"Airbnb ID: {airbnb_id or '(none)'}\n"
        f"VRBO ID: {vrbo_id or '(none)'}\n"
        f"IP: {ip}\n"
        f"Time: {datetime.now(timezone.utc).isoformat()}\n"
    )
    with smtplib.SMTP(host, int(ENV.get("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        s.login(ENV["SMTP_USER"], ENV["SMTP_PASS"])
        s.send_message(msg)


def send_sub_email(j_label, email, ip):
    host = ENV.get("SMTP_HOST")
    if not host:
        return
    msg = EmailMessage()
    msg["Subject"] = f"LawfulStay: new alert subscription — {j_label[:80]}"
    msg["From"] = ENV.get("MAIL_FROM", ENV.get("SMTP_USER", ""))
    msg["To"] = ENV.get("MAIL_TO", "ericmason.co@gmail.com")
    msg.set_content(
        "New regulation change alert subscription via lawfulstay.com:\n\n"
        f"Jurisdiction: {j_label}\n"
        f"Subscriber email: {email}\n"
        f"IP: {ip}\n"
        f"Time: {datetime.now(timezone.utc).isoformat()}\n"
    )
    with smtplib.SMTP(host, int(ENV.get("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        s.login(ENV["SMTP_USER"], ENV["SMTP_PASS"])
        s.send_message(msg)


def send_feedback_email(j_label, email, notes, ip):
    host = ENV.get("SMTP_HOST")
    if not host:
        return
    msg = EmailMessage()
    msg["Subject"] = f"LawfulStay: correction/feedback — {j_label or 'Global'}"
    msg["From"] = ENV.get("MAIL_FROM", ENV.get("SMTP_USER", ""))
    msg["To"] = ENV.get("MAIL_TO", "ericmason.co@gmail.com")
    msg.set_content(
        "New regulation correction/feedback submitted via lawfulstay.com:\n\n"
        f"Jurisdiction: {j_label or 'General / Global Feedback'}\n"
        f"Submitter email: {email or '(none)'}\n"
        f"Correction details:\n{notes}\n\n"
        f"IP: {ip}\n"
        f"Time: {datetime.now(timezone.utc).isoformat()}\n"
    )
    with smtplib.SMTP(host, int(ENV.get("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        s.login(ENV["SMTP_USER"], ENV["SMTP_PASS"])
        s.send_message(msg)


def push_to_acumbamail(email: str, j_label: str) -> bool:
    token = ENV.get("ACUMBAMAIL_TOKEN")
    list_id = ENV.get("ACUMBAMAIL_LIST_ID")
    if not token or not list_id:
        return False
    url = "https://acumbamail.com/api/1/addSubscriber/"
    payload = {
        "auth_token": token,
        "response_type": "json",
        "list_id": int(list_id),
        "double_optin": 1,
        "welcome_email": 0,
        "merge_fields[email]": email,
        "merge_fields[JURISDICTION]": j_label
    }
    encoded_data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            print("Acumbamail push response:", res_json, flush=True)
            return True
    except Exception as e:
        print("Acumbamail push failed:", e, flush=True)
        return False


DB_PATH = Path("/opt/str-tracker/data/users.db")

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            ip TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS location_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            location TEXT NOT NULL,
            notes TEXT,
            subscribe_on_add INTEGER NOT NULL DEFAULT 0,
            contributor_opt_in INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    # Migration: add contributor_opt_in if it doesn't exist yet
    try:
        c.execute("ALTER TABLE location_requests ADD COLUMN contributor_opt_in INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS alert_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            jurisdiction_id TEXT NOT NULL,
            jurisdiction_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS monitored_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            airbnb_id TEXT,
            vrbo_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()
    
    try:
        migrate_existing_logs()
    except Exception as e:
        print("Log migration failed:", e, flush=True)

def get_or_create_user(conn, email, ip, ts_fallback=None):
    c = conn.cursor()
    now_str = ts_fallback or datetime.now(timezone.utc).isoformat()
    email_clean = email.strip().lower()
    
    c.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email_clean,))
    row = c.fetchone()
    if row:
        user_id = row[0]
        c.execute("UPDATE users SET last_seen = ?, ip = ? WHERE id = ?", (now_str, ip, user_id))
        return user_id
    else:
        c.execute("INSERT INTO users (email, created_at, last_seen, ip) VALUES (?, ?, ?, ?)",
                  (email.strip(), now_str, now_str, ip))
        return c.lastrowid

def migrate_existing_logs():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Migrate location requests
    loc_log = Path("/opt/str-tracker/data/location_requests.jsonl")
    if loc_log.exists():
        with loc_log.open("r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    ts = rec.get("ts", datetime.now(timezone.utc).isoformat())
                    email = rec.get("email", "")
                    loc = rec.get("location", "")
                    notes = rec.get("notes", "")
                    subscribe = bool(rec.get("subscribe", False))
                    ip = rec.get("ip", "")
                    
                    user_id = get_or_create_user(conn, email, ip, ts) if email else None
                    contributor_opt_in = bool(rec.get("contributor_opt_in", False))
                    
                    c.execute("""
                        SELECT id FROM location_requests 
                        WHERE (user_id = ? OR (user_id IS NULL AND ? IS NULL)) 
                          AND location = ? AND created_at = ?
                    """, (user_id, user_id, loc, ts))
                    if not c.fetchone():
                        c.execute("""
                            INSERT INTO location_requests (user_id, location, notes, subscribe_on_add, contributor_opt_in, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (user_id, loc, notes, 1 if subscribe else 0, 1 if contributor_opt_in else 0, ts))
                except Exception as e:
                    print("Error migrating location request line:", e, flush=True)
                    
    # 2. Migrate alert subscriptions
    sub_log = Path("/opt/str-tracker/data/regulation_subscriptions.jsonl")
    if sub_log.exists():
        with sub_log.open("r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    ts = rec.get("ts", datetime.now(timezone.utc).isoformat())
                    email = rec.get("email", "")
                    j_id = rec.get("jurisdiction_id", "")
                    j_label = rec.get("jurisdiction_label", "")
                    ip = rec.get("ip", "")
                    
                    if email:
                        user_id = get_or_create_user(conn, email, ip, ts)
                        c.execute("""
                            SELECT id FROM alert_subscriptions 
                            WHERE user_id = ? AND jurisdiction_id = ? AND created_at = ?
                        """, (user_id, j_id, ts))
                        if not c.fetchone():
                            c.execute("""
                                INSERT INTO alert_subscriptions (user_id, jurisdiction_id, jurisdiction_label, created_at)
                                VALUES (?, ?, ?, ?)
                            """, (user_id, j_id, j_label, ts))
                except Exception as e:
                    print("Error migrating subscription line:", e, flush=True)
                    
    # 3. Migrate listing monitor requests
    mon_log = Path("/opt/str-tracker/data/listing_monitoring_requests.jsonl")
    if mon_log.exists():
        with mon_log.open("r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    ts = rec.get("ts", datetime.now(timezone.utc).isoformat())
                    email = rec.get("email", "")
                    airbnb_id = rec.get("airbnb_id", "")
                    vrbo_id = rec.get("vrbo_id", "")
                    ip = rec.get("ip", "")
                    
                    if email:
                        user_id = get_or_create_user(conn, email, ip, ts)
                        c.execute("""
                            SELECT id FROM monitored_listings 
                            WHERE user_id = ? AND (airbnb_id = ? OR (airbnb_id IS NULL AND ? IS NULL)) AND created_at = ?
                        """, (user_id, airbnb_id, airbnb_id, ts))
                        if not c.fetchone():
                            c.execute("""
                                INSERT INTO monitored_listings (user_id, airbnb_id, vrbo_id, created_at)
                                VALUES (?, ?, ?, ?)
                            """, (user_id, airbnb_id, vrbo_id, ts))
                except Exception as e:
                    print("Error migrating listing monitor line:", e, flush=True)
                    
    conn.commit()
    conn.close()


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/api/contributors":
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                # Fetch all opted-in requests that have an associated user
                c.execute("""
                    SELECT u.email, lr.location, lr.created_at
                    FROM location_requests lr
                    JOIN users u ON u.id = lr.user_id
                    WHERE lr.contributor_opt_in = 1
                    ORDER BY lr.created_at ASC
                """)
                rows = c.fetchall()
                conn.close()

                # Group by email
                from collections import defaultdict
                grouped = defaultdict(list)
                earliest = {}
                for email, location, created_at in rows:
                    grouped[email].append(location)
                    if email not in earliest or created_at < earliest[email]:
                        earliest[email] = created_at

                contributors = []
                for email, locs in grouped.items():
                    prefix = email.split("@")[0]
                    # Capitalise and sanitise display name
                    display = prefix.replace(".", " ").replace("_", " ").replace("-", " ").title()
                    since_raw = earliest[email][:10]  # YYYY-MM-DD
                    # Format as "Month YYYY"
                    try:
                        from datetime import datetime as _dt
                        dt = _dt.strptime(since_raw, "%Y-%m-%d")
                        since = dt.strftime("%B %Y")
                    except Exception:
                        since = since_raw
                    contributors.append({
                        "display_name": display,
                        "locations": locs,
                        "since": since
                    })

                body = json.dumps({
                    "ok": True,
                    "contributors": contributors,
                    "total_locations": sum(len(c["locations"]) for c in contributors)
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                print("contributors endpoint error:", e, flush=True)
                self._json(500, {"ok": False, "error": "Server error."})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.rstrip("/")
        if path not in ("/api/request-location", "/api/subscribe-alerts", "/api/submit-feedback", "/api/monitor-listing"):
            return self._json(404, {"ok": False, "error": "not found"})

        ip = self.headers.get("X-Forwarded-For", "-").split(",")[0].strip()
        now = time.time()
        if now - _last_hit.get(ip, 0) < 10:  # one per 10s per IP
            return self._json(429, {"ok": False, "error": "Please wait a moment and try again."})

        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 4000:
                return self._json(413, {"ok": False, "error": "Too large."})
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json(400, {"ok": False, "error": "Invalid request."})

        if str(data.get("website", "")).strip():  # honeypot tripped
            return self._json(200, {"ok": True, "message": "Thanks!"})

        if path == "/api/request-location":
            loc = str(data.get("location", "")).strip()[:MAX_LOC]
            email = str(data.get("email", "")).strip()[:MAX_LOC]
            notes = str(data.get("notes", "")).strip()[:1000]
            subscribe = bool(data.get("subscribe", False))
            if len(loc) < 2:
                return self._json(400, {"ok": False, "error": "Please enter a location."})
            if email and not EMAIL_RE.match(email):
                return self._json(400, {"ok": False, "error": "Please enter a valid email."})

            rec = {"ts": datetime.now(timezone.utc).isoformat(), "location": loc,
                   "email": email, "notes": notes, "subscribe": subscribe, "ip": ip}
            LOG.parent.mkdir(parents=True, exist_ok=True)
            with LOG.open("a") as f:
                f.write(json.dumps(rec) + "\n")
                
            # SQLite insertion
            try:
                conn = sqlite3.connect(DB_PATH)
                user_id = get_or_create_user(conn, email, ip) if email else None
                c = conn.cursor()
                now_str = datetime.now(timezone.utc).isoformat()
                contributor_opt_in = bool(data.get("contributor_opt_in", False))
                c.execute("""
                    INSERT INTO location_requests (user_id, location, notes, subscribe_on_add, contributor_opt_in, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, loc, notes, 1 if subscribe else 0, 1 if contributor_opt_in else 0, now_str))
                conn.commit()
                conn.close()
            except Exception as e:
                print("SQLite location request insert failed:", e, flush=True)

            try:
                send_email(loc, email, notes, ip, subscribe)
            except Exception as e:  # don't fail the user if email hiccups
                print("email failed:", e, flush=True)

            if subscribe and email:
                try:
                    push_to_acumbamail(email, f"[Requested] {loc}")
                except Exception as e:
                    print("Acumbamail push failed in request handler:", e, flush=True)

            _last_hit[ip] = now
            return self._json(200, {"ok": True,
                                    "message": "Thanks — we'll research it and add it to the tracker."})

        elif path == "/api/monitor-listing":
            airbnb_id = str(data.get("airbnb_id", "")).strip()[:MAX_LOC]
            vrbo_id = str(data.get("vrbo_id", "")).strip()[:MAX_LOC]
            email = str(data.get("email", "")).strip()[:MAX_LOC]
            
            if not email or not EMAIL_RE.match(email):
                return self._json(400, {"ok": False, "error": "Please enter a valid email address."})
            if not airbnb_id and not vrbo_id:
                return self._json(400, {"ok": False, "error": "Please enter at least one Listing ID."})
                
            rec = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "airbnb_id": airbnb_id,
                "vrbo_id": vrbo_id,
                "email": email,
                "ip": ip
            }
            log_file = LOG.parent / "listing_monitoring_requests.jsonl"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a") as f:
                f.write(json.dumps(rec) + "\n")
                
            # SQLite insertion
            try:
                conn = sqlite3.connect(DB_PATH)
                user_id = get_or_create_user(conn, email, ip)
                c = conn.cursor()
                now_str = datetime.now(timezone.utc).isoformat()
                c.execute("""
                    INSERT INTO monitored_listings (user_id, airbnb_id, vrbo_id, created_at)
                    VALUES (?, ?, ?, ?)
                """, (user_id, airbnb_id, vrbo_id, now_str))
                conn.commit()
                conn.close()
            except Exception as e:
                print("SQLite monitored listing insert failed:", e, flush=True)
                
            try:
                send_monitor_request_email(airbnb_id, vrbo_id, email, ip)
            except Exception as e:
                print("monitor request email failed:", e, flush=True)
                
            try:
                push_to_acumbamail(email, "[Listing Monitor Request]")
            except Exception as e:
                print("Acumbamail push failed in monitor request handler:", e, flush=True)
                
            _last_hit[ip] = now
            return self._json(200, {"ok": True, "message": "Successfully registered! We will review your listing and enable alerts shortly."})

        elif path == "/api/subscribe-alerts":
            j_id = str(data.get("jurisdiction_id", "")).strip()[:MAX_LOC]
            j_label = str(data.get("jurisdiction_label", "")).strip()[:MAX_LOC]
            email = str(data.get("email", "")).strip()[:MAX_LOC]
            
            if not j_id or not j_label:
                return self._json(400, {"ok": False, "error": "Invalid jurisdiction."})
            if not email or not EMAIL_RE.match(email):
                return self._json(400, {"ok": False, "error": "Please enter a valid email address."})

            sub_log = Path("/opt/str-tracker/data/regulation_subscriptions.jsonl")
            rec = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "jurisdiction_id": j_id,
                "jurisdiction_label": j_label,
                "email": email,
                "ip": ip
            }
            sub_log.parent.mkdir(parents=True, exist_ok=True)
            with sub_log.open("a") as f:
                f.write(json.dumps(rec) + "\n")
                
            # SQLite insertion
            try:
                conn = sqlite3.connect(DB_PATH)
                user_id = get_or_create_user(conn, email, ip)
                c = conn.cursor()
                now_str = datetime.now(timezone.utc).isoformat()
                c.execute("""
                    INSERT INTO alert_subscriptions (user_id, jurisdiction_id, jurisdiction_label, created_at)
                    VALUES (?, ?, ?, ?)
                """, (user_id, j_id, j_label, now_str))
                conn.commit()
                conn.close()
            except Exception as e:
                print("SQLite alert subscription insert failed:", e, flush=True)

            try:
                send_sub_email(j_label, email, ip)
            except Exception as e:
                print("subscription email failed:", e, flush=True)
 
            try:
                push_to_acumbamail(email, j_label)
            except Exception as e:
                print("Acumbamail push failed in handler:", e, flush=True)

            _last_hit[ip] = now
            return self._json(200, {"ok": True, "message": f"You're in! Check your inbox to confirm — we're glad to have you as part of the LawfulStay community."})

        elif path == "/api/submit-feedback":
            j_id = str(data.get("jurisdiction_id", "")).strip()[:MAX_LOC]
            j_label = str(data.get("jurisdiction_label", "")).strip()[:MAX_LOC]
            email = str(data.get("email", "")).strip()[:MAX_LOC]
            notes = str(data.get("notes", "")).strip()[:1000]

            if not notes or len(notes) < 3:
                return self._json(400, {"ok": False, "error": "Please enter your feedback or correction details."})
            if email and not EMAIL_RE.match(email):
                return self._json(400, {"ok": False, "error": "Please enter a valid email address."})

            feedback_log = Path("/opt/str-tracker/data/regulation_feedback.jsonl")
            rec = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "jurisdiction_id": j_id,
                "jurisdiction_label": j_label,
                "email": email,
                "notes": notes,
                "ip": ip
            }
            feedback_log.parent.mkdir(parents=True, exist_ok=True)
            with feedback_log.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            try:
                send_feedback_email(j_label, email, notes, ip)
            except Exception as e:
                print("feedback email failed:", e, flush=True)

            _last_hit[ip] = now
            return self._json(200, {"ok": True, "message": "Thank you! Our research group will verify this correction."})

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8090"))
    print(f"request_server listening on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
