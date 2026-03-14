"""
Copperline — Lead Operations Dashboard
Run: python lead_engine/dashboard_server.py
Then open: http://localhost:5000
"""
from __future__ import annotations

import csv
import json
import os
import sys
import webbrowser
from pathlib import Path
from threading import Timer

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from flask import Flask, jsonify, request
except ImportError:
    print("\nFlask not installed. Installing now...\n")
    os.system(f"{sys.executable} -m pip install flask -q")
    from flask import Flask, jsonify, request

from run_lead_engine import run as run_pipeline, DEFAULT_PENDING_CSV, DEFAULT_PROSPECTS_CSV
from scoring.opportunity_scoring_agent import score_label as get_score_label
from send.email_sender_agent import process_pending_emails
from intelligence.email_extractor_agent import enrich_prospects_with_emails
from discovery.auto_prospect_agent import discover_prospects, INDUSTRY_QUERIES
from outreach.followup_scheduler import run_followup_scheduler

BASE_DIR = Path(__file__).resolve().parent
PENDING_CSV = DEFAULT_PENDING_CSV
PROSPECTS_CSV = DEFAULT_PROSPECTS_CSV

PENDING_COLUMNS = [
    "business_name", "city", "state", "website", "phone", "contact_method",
    "industry", "to_email", "subject", "body", "approved", "sent_at",
    "scoring_reason", "final_priority_score", "automation_opportunity",
]

app = Flask(__name__)


# ── Data helpers ──────────────────────────────────────────────────────────────

def _read_pending() -> list:
    if not PENDING_CSV.exists():
        return []
    with PENDING_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        return [{col: row.get(col, "") for col in PENDING_COLUMNS} for row in reader]


def _write_pending(rows: list) -> None:
    PENDING_CSV.parent.mkdir(parents=True, exist_ok=True)
    with PENDING_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PENDING_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _prospects_count() -> int:
    if not PROSPECTS_CSV.exists():
        return 0
    with PROSPECTS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    html_path = BASE_DIR / "dashboard_static" / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.route("/api/status")
def api_status():
    rows = _read_pending()
    return jsonify({
        "prospects_loaded": _prospects_count(),
        "total_drafted": len(rows),
        "pending_approval": sum(1 for r in rows
                                if r["approved"].lower() != "true" and not r["sent_at"]),
        "approved_unsent": sum(1 for r in rows
                               if r["approved"].lower() == "true" and not r["sent_at"]),
        "sent": sum(1 for r in rows if r["sent_at"]),
    })


@app.route("/api/queue")
def api_queue():
    rows = _read_pending()
    for row in rows:
        try:
            score = int(row.get("final_priority_score") or 0)
        except (ValueError, TypeError):
            score = 0
        row["score"] = score
        row["score_label"] = get_score_label(score) if score else ""
    return jsonify(rows)


@app.route("/api/run_pipeline", methods=["POST"])
def api_run_pipeline():
    try:
        run_pipeline(input_csv=PROSPECTS_CSV, skip_scan=False)
        rows = _read_pending()
        return jsonify({"ok": True, "total": len(rows)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/update_row", methods=["POST"])
def api_update_row():
    data = request.json
    idx = data.get("index")
    updates = data.get("updates", {})
    rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    for key, val in updates.items():
        if key in PENDING_COLUMNS:
            rows[idx][key] = val
    _write_pending(rows)
    return jsonify({"ok": True})


@app.route("/api/approve_row", methods=["POST"])
def api_approve_row():
    idx = request.json.get("index")
    rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    rows[idx]["approved"] = "true"
    _write_pending(rows)
    return jsonify({"ok": True})


@app.route("/api/unapprove_row", methods=["POST"])
def api_unapprove_row():
    idx = request.json.get("index")
    rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    rows[idx]["approved"] = "false"
    _write_pending(rows)
    return jsonify({"ok": True})


@app.route("/api/approve_all", methods=["POST"])
def api_approve_all():
    rows = _read_pending()
    count = 0
    for row in rows:
        if not row["sent_at"]:
            row["approved"] = "true"
            count += 1
    _write_pending(rows)
    return jsonify({"ok": True, "approved": count})


@app.route("/api/send_approved", methods=["POST"])
def api_send_approved():
    send_live = request.json.get("send_live", False)
    try:
        stats = process_pending_emails(PENDING_CSV, dry_run=not send_live)
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/delete_row", methods=["POST"])
def api_delete_row():
    idx = request.json.get("index")
    rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    rows.pop(idx)
    _write_pending(rows)
    return jsonify({"ok": True})


@app.route("/api/run_followups", methods=["POST"])
def api_run_followups():
    try:
        stats = run_followup_scheduler(dry_run=False)
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/extract_emails", methods=["POST"])
def api_extract_emails():
    try:
        stats = enrich_prospects_with_emails(PROSPECTS_CSV, limit=0, overwrite=False)
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/industries")
def api_industries():
    return jsonify(sorted(INDUSTRY_QUERIES.keys()))


@app.route("/api/check_api_key")
def api_check_api_key():
    """Verify API key against Places API (New) endpoint."""
    from urllib.request import urlopen, Request as URLRequest
    import json as _json
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "GOOGLE_PLACES_API_KEY not set in Launch Dashboard.bat"})
    try:
        url = "https://places.googleapis.com/v1/places:searchText"
        payload = _json.dumps({"textQuery": "plumber Rockford IL", "maxResultCount": 1}).encode()
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName",
        }
        req = URLRequest(url, data=payload, headers=headers, method="POST")
        with urlopen(req, timeout=8) as r:
            data = _json.loads(r.read().decode())
        count = len(data.get("places", []))
        return jsonify({"ok": True, "message": f"API key works. Test query returned {count} result(s)."})
    except Exception as exc:
        # urllib raises HTTPError for 4xx — extract body for Google's error message
        try:
            body = _json.loads(exc.read().decode()) if hasattr(exc, 'read') else {}
            msg = body.get("error", {}).get("message", str(exc))
        except Exception:
            msg = str(exc)
        return jsonify({"ok": False, "error": msg})


@app.route("/api/discover", methods=["POST"])
def api_discover():
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "GOOGLE_PLACES_API_KEY not set. See setup instructions."}), 400
    data = request.json
    industry = data.get("industry", "plumbing")
    city     = data.get("city", "Rockford")
    state    = data.get("state", "IL")
    limit    = int(data.get("limit", 20))
    try:
        rows = discover_prospects(industry=industry, city=city, state=state,
                                  api_key=api_key, limit=limit, scrape_emails=True)
        if len(rows) == 0:
            return jsonify({
                "ok": False,
                "error": "Google Places returned 0 results. Check your API key is valid and Places API (New) is enabled in Google Cloud Console."
            }), 400
        # Draft emails only for the newly discovered rows
        run_pipeline(input_csv=PROSPECTS_CSV, skip_scan=True)
        pending = _read_pending()
        return jsonify({"ok": True, "found": len(rows), "total_queue": len(pending)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    print()
    print("  ┌──────────────────────────────────────────────┐")
    print("  │     Copperline — Lead Operations             │")
    print("  │     Opening at  http://localhost:5000        │")
    print("  └──────────────────────────────────────────────┘")
    print()
    Timer(1.2, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
