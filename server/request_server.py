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


def send_email(loc, email, notes, ip):
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


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = self.path.rstrip("/")
        if path not in ("/api/request-location", "/api/subscribe-alerts"):
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
            if len(loc) < 2:
                return self._json(400, {"ok": False, "error": "Please enter a location."})
            if email and not EMAIL_RE.match(email):
                return self._json(400, {"ok": False, "error": "Please enter a valid email."})

            rec = {"ts": datetime.now(timezone.utc).isoformat(), "location": loc,
                   "email": email, "notes": notes, "ip": ip}
            LOG.parent.mkdir(parents=True, exist_ok=True)
            with LOG.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            try:
                send_email(loc, email, notes, ip)
            except Exception as e:  # don't fail the user if email hiccups
                print("email failed:", e, flush=True)

            _last_hit[ip] = now
            return self._json(200, {"ok": True,
                                    "message": "Thanks — we'll research it and add it to the tracker."})

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
            try:
                send_sub_email(j_label, email, ip)
            except Exception as e:
                print("subscription email failed:", e, flush=True)

            try:
                push_to_acumbamail(email, j_label)
            except Exception as e:
                print("Acumbamail push failed in handler:", e, flush=True)

            _last_hit[ip] = now
            return self._json(200, {"ok": True, "message": f"Successfully subscribed to alerts for {j_label}!"})

    def log_message(self, *a):  # quiet
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8090"))
    print(f"request_server listening on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
