"""
Copperline — Lead Operations Dashboard
Run: python lead_engine/dashboard_server.py
Then open: http://localhost:5000
"""
from __future__ import annotations

import csv
import importlib.util
import json
import logging
import os
import re
import sys
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Timer

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

try:
    from flask import Flask, jsonify, request
except ImportError:
    print("\nFlask not installed. Installing now...\n")
    os.system(f"{sys.executable} -m pip install flask -q")
    from flask import Flask, jsonify, request

from run_lead_engine import run as run_pipeline, DEFAULT_PENDING_CSV, DEFAULT_PROSPECTS_CSV
from scoring.opportunity_scoring_agent import score_label as get_score_label, compute_numeric_score, score_priority_label
from send.email_sender_agent import process_pending_emails, is_real_send, send_next_due_email, CSV_WRITE_LOCK
from intelligence.email_extractor_agent import enrich_prospects_with_emails
from discovery.auto_prospect_agent import discover_prospects, INDUSTRY_QUERIES, discover_prospects_area
from outreach.followup_scheduler import run_followup_scheduler
from outreach.reply_checker import check_for_replies, reconcile_sent_mail
from outreach.email_draft_agent import DRAFT_VERSION as _CURRENT_DRAFT_VERSION
from city_planner import CityPlanner

# ---------------------------------------------------------------------------
# Load queue modules via direct file path — avoids collision with Python's
# built-in 'queue' stdlib module (package-style import would shadow it).
# ---------------------------------------------------------------------------
_qi_spec = importlib.util.spec_from_file_location(
    "queue_integrity",
    Path(__file__).resolve().parent / "queue" / "queue_integrity.py",
)
_qi_mod = importlib.util.module_from_spec(_qi_spec)
_qi_spec.loader.exec_module(_qi_mod)
scan_queue_integrity = _qi_mod.scan_queue_integrity

_er_spec = importlib.util.spec_from_file_location(
    "exception_router",
    Path(__file__).resolve().parent / "queue" / "exception_router.py",
)
_er_mod = importlib.util.module_from_spec(_er_spec)
_er_spec.loader.exec_module(_er_mod)
scan_exceptions = _er_mod.scan_exceptions

BASE_DIR      = Path(__file__).resolve().parent
PENDING_CSV   = DEFAULT_PENDING_CSV
PROSPECTS_CSV = DEFAULT_PROSPECTS_CSV
SEARCH_HISTORY_FILE = BASE_DIR / "data" / "search_history.json"
CITY_STORE_FILE     = BASE_DIR / "data" / "city_planner.json"
_city_planner = CityPlanner(CITY_STORE_FILE)


def _load_search_history() -> list:
    if not SEARCH_HISTORY_FILE.exists():
        return []
    try:
        with SEARCH_HISTORY_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _append_search_history(entry: dict) -> None:
    history = _load_search_history()
    history.insert(0, entry)
    history = history[:500]
    SEARCH_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SEARCH_HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
_handler = RotatingFileHandler(LOG_DIR / "copperline.log", maxBytes=2*1024*1024, backupCount=5, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler, logging.StreamHandler()])
log = logging.getLogger("copperline")

# Authoritative 41-column schema — matches run_lead_engine.PENDING_COLUMNS exactly.
# Column ORDER here determines what _write_pending() writes to the CSV header.
# All readers use DictReader (.get(col,"")) so are order-independent,
# but keeping one canonical ordering prevents future drift.
PENDING_COLUMNS = [
    "business_name", "city", "state", "website", "phone", "contact_method",
    "industry", "to_email", "subject", "body", "approved", "sent_at",
    "approval_reason",
    "scoring_reason", "final_priority_score", "automation_opportunity",
    "do_not_contact", "draft_version",
    "facebook_url", "instagram_url", "contact_form_url",
    "social_channels", "social_dm_text",
    "facebook_dm_draft", "instagram_dm_draft", "contact_form_message",
    "lead_insight_sentence", "lead_insight_signals",
    "opportunity_score",
    "last_contact_channel", "last_contacted_at", "contact_attempt_count",
    "contact_result", "next_followup_at", "campaign_key",
    "message_id", "replied", "replied_at", "reply_snippet",
    "conversation_notes", "conversation_next_step",
    "send_after",
]

_ACTIVE_RESULTS   = {"draft_ready", "sent", "submitted", "dm_sent", "no_reply"}
_TERMINAL_RESULTS = {"replied", "not_interested", "bad_lead", "no_contact_route", "closed"}

# ── Scheduling: industry send windows ────────────────────────────────────────
# Each entry is (start_hour, end_hour) in 24-hour local time.
# A random minute is chosen within the window when scheduling.
INDUSTRY_WINDOWS = {
    "hvac":        (7, 10),
    "plumbing":    (7, 10),
    "garage_door": (7, 10),
    "roofing":     (7, 10),
    "auto":        (8, 11),
    "locksmith":   (8, 11),
    "default":     (8, 10),
}


def _schedule_send_after(industry: str, days_ahead: int = 1) -> str:
    """
    Build a naive local ISO timestamp for scheduling.

    Picks a random minute within the industry send window on the target day.
    days_ahead=1 means tomorrow; higher values push further out.

    Returns a string like "2026-03-17T07:42:00".
    """
    from datetime import datetime as _dt, timedelta as _tdelta
    import random as _rand
    start_h, end_h = INDUSTRY_WINDOWS.get(industry, INDUSTRY_WINDOWS["default"])
    # Random hour and minute within window
    hour   = _rand.randint(start_h, end_h - 1)
    minute = _rand.randint(0, 59)
    target = _dt.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    target += _tdelta(days=days_ahead)
    return target.strftime("%Y-%m-%dT%H:%M:%S")
_DEFAULT_FOLLOWUP_DAYS = 7
CAMPAIGN_PRESETS_FILE  = BASE_DIR / "data" / "campaign_presets.json"

def _load_presets() -> list:
    if not CAMPAIGN_PRESETS_FILE.exists():
        return []
    try:
        return json.load(CAMPAIGN_PRESETS_FILE.open(encoding="utf-8"))
    except Exception:
        return []

def _preset_followup_days(campaign_key: str) -> int:
    for p in _load_presets():
        if p.get("key") == campaign_key:
            return int(p.get("followup_days", _DEFAULT_FOLLOWUP_DAYS))
    return _DEFAULT_FOLLOWUP_DAYS

app = Flask(__name__, static_folder=None)  # disable built-in /static/ route; custom route below serves dashboard_static/

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
    safe = [{col: row.get(col, "") for col in PENDING_COLUMNS} for row in rows]
    with CSV_WRITE_LOCK:
        with PENDING_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PENDING_COLUMNS)
            writer.writeheader()
            writer.writerows(safe)

def _prospects_count() -> int:
    if not PROSPECTS_CSV.exists():
        return 0
    with PROSPECTS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))

@app.route("/")
def index():
    return (BASE_DIR / "dashboard_static" / "index.html").read_text(encoding="utf-8")

@app.route("/static/<path:filename>")
def static_files(filename):
    from flask import send_from_directory
    return send_from_directory(BASE_DIR / "dashboard_static", filename)

@app.route("/api/status")
def api_status():
    rows  = _read_pending()
    stale = sum(1 for r in rows if not r.get("sent_at") and r.get("draft_version","") != _CURRENT_DRAFT_VERSION)
    sent_real   = sum(1 for r in rows if is_real_send(r))
    sent_logged = sum(1 for r in rows if (r.get("sent_at") or "").strip() and not (r.get("message_id") or "").strip())
    return jsonify({
        "prospects_loaded":      _prospects_count(),
        "total_drafted":         len(rows),
        "pending_approval":      sum(1 for r in rows if (r.get("approved") or "").lower() != "true" and not r.get("sent_at")),
        "approved_unsent":       sum(1 for r in rows if (r.get("approved") or "").lower() == "true" and not r.get("sent_at")),
        "sent":                  sent_real,
        "sent_logged_only":      sent_logged,
        "replied":               sum(1 for r in rows if (r.get("replied") or "").lower() == "true"),
        "stale_drafts":          stale,
        "current_draft_version": _CURRENT_DRAFT_VERSION,
    })

def _enrich_row(row: dict, index: int) -> dict:
    try:
        opp_score = int(row.get("opportunity_score") or 0)
    except (ValueError, TypeError):
        opp_score = 0
    if not opp_score:
        opp_score = compute_numeric_score(row)
        row["opportunity_score"] = str(opp_score)
    row["opp_score"]    = opp_score
    row["opp_priority"] = score_priority_label(opp_score)
    row["index"]        = index
    return row

@app.route("/api/queue")
def api_queue():
    rows = _read_pending()
    now_local = _datetime.now()
    for i, row in enumerate(rows):
        try: score = int(row.get("final_priority_score") or 0)
        except: score = 0
        row["score"] = score
        row["score_label"] = get_score_label(score) if score else ""
        _enrich_row(row, i)
        # Computed field: is_ready — true when send_after is set and its time has passed.
        # Used by frontend to promote past-due scheduled rows into the Actionable filter.
        send_after_raw = (row.get("send_after") or "").strip()
        if send_after_raw:
            try:
                row["is_ready"] = _datetime.fromisoformat(send_after_raw) <= now_local
            except ValueError:
                row["is_ready"] = False
        else:
            row["is_ready"] = False
    return jsonify(rows)

@app.route("/api/run_pipeline", methods=["POST"])
def api_run_pipeline():
    try:
        run_pipeline(input_csv=PROSPECTS_CSV, skip_scan=False)
        return jsonify({"ok": True, "total": len(_read_pending())})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.route("/api/update_row", methods=["POST"])
def api_update_row():
    data = request.json; idx = data.get("index"); updates = data.get("updates", {})
    rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    for key, val in updates.items():
        if key in PENDING_COLUMNS: rows[idx][key] = val
    _write_pending(rows)
    return jsonify({"ok": True})

@app.route("/api/approve_row", methods=["POST"])
def api_approve_row():
    idx = request.json.get("index"); rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    rows[idx]["approved"] = "true"
    _write_pending(rows); return jsonify({"ok": True})

@app.route("/api/unapprove_row", methods=["POST"])
def api_unapprove_row():
    idx = request.json.get("index"); rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    rows[idx]["approved"] = "false"
    _write_pending(rows); return jsonify({"ok": True})

@app.route("/api/approve_all", methods=["POST"])
def api_approve_all():
    rows = _read_pending(); count = 0
    for row in rows:
        if not row["sent_at"]: row["approved"] = "true"; count += 1
    _write_pending(rows); return jsonify({"ok": True, "approved": count})

@app.route("/api/send_approved", methods=["POST"])
def api_send_approved():
    send_live = request.json.get("send_live", False)
    try:
        stats = process_pending_emails(PENDING_CSV, dry_run=not send_live)
        if send_live:
            log.info("Send run: sent=%d failed=%d", stats.get("sent",0), stats.get("failed",0))
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        log.error("Send error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.route("/api/delete_row", methods=["POST"])
def api_delete_row():
    idx = request.json.get("index"); rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    rows.pop(idx); _write_pending(rows); return jsonify({"ok": True})

@app.route("/api/run_followups", methods=["POST"])
def api_run_followups():
    try:
        stats = run_followup_scheduler(dry_run=False)
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.route("/api/run_followups_dry_run", methods=["POST"])
def api_run_followups_dry_run():
    """
    Dry-run preview: returns the list of rows that WOULD get follow-up drafts
    without writing anything to the queue CSV.
    """
    try:
        from datetime import datetime as _dt, timezone as _tz
        import csv as _csv
        from send.email_sender_agent import is_real_send as _is_real_send
        from outreach.followup_scheduler import (
            followup_eligible, _followup_step, _read_pending, FOLLOWUP_DAYS_DEFAULT,
        )
        from discovery.prospect_discovery_agent import dedupe_key_for_prospect

        now  = _dt.now(_tz.utc)
        rows = _read_pending()

        unsent_keys = {
            dedupe_key_for_prospect(r)
            for r in rows
            if not (r.get("sent_at") or "").strip()
        }

        preview = []
        for row in rows:
            if not _is_real_send(row):
                continue
            eligible, _ = followup_eligible(row, now, unsent_keys)
            if eligible:
                step = _followup_step(row, now)
                preview.append({
                    "business_name": row.get("business_name", ""),
                    "to_email":      row.get("to_email", ""),
                    "sent_at":       row.get("sent_at", ""),
                    "followup_step": step,
                    "contact_attempt_count": row.get("contact_attempt_count", "0"),
                })

        return jsonify({"ok": True, "preview": preview, "count": len(preview)})
    except Exception as exc:
        log.error("followup dry_run error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.route("/api/replies")
def api_replies():
    rows = _read_pending()
    replied = sorted([r for r in rows if (r.get("replied") or "").lower() == "true"],
                     key=lambda r: r.get("replied_at",""), reverse=True)
    return jsonify(replied)

@app.route("/api/check_replies", methods=["POST"])
def api_check_replies():
    try:
        result = check_for_replies(max_messages=100)
        if result["new_replies"] > 0:
            log.info("Reply check: found=%d errors=%d", result["new_replies"], len(result["errors"]))
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        log.error("Reply check error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.route("/api/reconcile_sent", methods=["POST"])
def api_reconcile_sent():
    try:
        d = request.json or {}
        max_messages = int(d.get("max_messages", 150))
        lookback_hours = int(d.get("lookback_hours", 72))
        result = reconcile_sent_mail(max_messages=max_messages, lookback_hours=lookback_hours)
        if result.get("updated_rows", 0) > 0:
            log.info(
                "Sent reconciliation: updated=%d ambiguous=%d checked=%d",
                result.get("updated_rows", 0),
                result.get("skipped_ambiguous", 0),
                result.get("checked_sent_messages", 0),
            )
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        log.error("Sent reconciliation error: %s", exc, exc_info=True)
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
    from urllib.request import urlopen, Request as URLRequest
    import json as _json
    api_key = os.getenv("GOOGLE_PLACES_API_KEY","").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "GOOGLE_PLACES_API_KEY not set"})
    try:
        url = "https://places.googleapis.com/v1/places:searchText"
        payload = _json.dumps({"textQuery": "plumber Rockford IL", "maxResultCount": 1}).encode()
        req = URLRequest(url, data=payload,
                         headers={"Content-Type":"application/json","X-Goog-Api-Key":api_key,"X-Goog-FieldMask":"places.displayName"},
                         method="POST")
        with urlopen(req, timeout=8) as r:
            data = _json.loads(r.read().decode())
        return jsonify({"ok": True, "message": f"API key works. {len(data.get('places',[]))} result(s)."})
    except Exception as exc:
        try:
            msg = _json.loads(exc.read().decode()).get("error",{}).get("message",str(exc)) if hasattr(exc,"read") else str(exc)
        except: msg = str(exc)
        return jsonify({"ok": False, "error": msg})

@app.route("/api/search_history")
def api_search_history():
    return jsonify(_load_search_history())

# ── City planner ──────────────────────────────────────────────────────────────
@app.route("/api/cities")
def api_cities(): return jsonify(_city_planner.all_cities())

@app.route("/api/cities/add", methods=["POST"])
def api_cities_add():
    d = request.json or {}
    city = d.get("city","").strip(); state = d.get("state","").strip(); tier = d.get("tier")
    if not city or not state: return jsonify({"ok":False,"error":"city and state required"}),400
    return jsonify({"ok":True,"entry":_city_planner.ensure_city(city,state,tier)})

@app.route("/api/cities/skip", methods=["POST"])
def api_cities_skip():
    d = request.json or {}; city = d.get("city","").strip(); state = d.get("state","").strip()
    if not city or not state: return jsonify({"ok":False,"error":"city and state required"}),400
    _city_planner.skip_city(city,state); return jsonify({"ok":True})

@app.route("/api/cities/set_tier", methods=["POST"])
def api_cities_set_tier():
    d = request.json or {}; city = d.get("city","").strip(); state = d.get("state","").strip(); tier = d.get("tier","").strip()
    if not city or not state or not tier: return jsonify({"ok":False,"error":"city, state, and tier required"}),400
    _city_planner.set_tier(city,state,tier); return jsonify({"ok":True})

@app.route("/api/cities/tiers")
def api_cities_tiers(): return jsonify(_city_planner.tiers_info())

@app.route("/api/cities/suggest")
def api_cities_suggest():
    return jsonify(_city_planner.suggest(
        request.args.get("state","IL").strip().upper(),
        request.args.get("q","").strip(),
        int(request.args.get("limit",30))))

@app.route("/api/discover", methods=["POST"])
def api_discover():
    api_key = os.getenv("GOOGLE_PLACES_API_KEY","").strip()
    if not api_key: return jsonify({"ok":False,"error":"GOOGLE_PLACES_API_KEY not set."}),400
    data = request.json; industry = data.get("industry","plumbing")
    city = data.get("city","Rockford"); state = data.get("state","IL"); limit = int(data.get("limit",20))
    from datetime import datetime as _dt
    try:
        rows = discover_prospects(industry=industry,city=city,state=state,api_key=api_key,limit=limit,scrape_emails=True)
        ts = _dt.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        if len(rows) == 0:
            log.warning("Discover returned 0 rows: industry=%s city=%s state=%s",industry,city,state)
            _append_search_history({"ts":ts,"city":city,"state":state,"industry":industry,"limit":limit,"found":0,"status":"all_duplicates"})
            _city_planner.record_discovery(city,state,0,industry=industry)
            return jsonify({"ok":False,"all_duplicates":True,"error":"No new leads found — all results already in pipeline."}),200
        log.info("Discovered %d prospects: industry=%s city=%s state=%s",len(rows),industry,city,state)
        _append_search_history({"ts":ts,"city":city,"state":state,"industry":industry,"limit":limit,"found":len(rows),"status":"ok"})
        _city_planner.record_discovery(city,state,len(rows),industry=industry)
        run_pipeline(input_csv=PROSPECTS_CSV,skip_scan=True)
        return jsonify({"ok":True,"found":len(rows),"total_queue":len(_read_pending())})
    except Exception as exc:
        log.error("Discover error: %s",exc,exc_info=True)
        _append_search_history({"ts":_dt.utcnow().strftime("%Y-%m-%d %H:%M UTC"),"city":city,"state":state,"industry":industry,"limit":limit,"found":0,"status":"error","error":str(exc)[:120]})
        return jsonify({"ok":False,"error":str(exc)}),500

@app.route("/api/discover_area", methods=["POST"])
def api_discover_area():
    """
    Map-area discovery: find businesses within a lat/lng/radius circle.
    Body: { industry, lat, lng, radius_m, limit }
    Returns: { ok, places_found, prospects_added, prospects_skipped,
               drafts_created, queue_total, markers, error? }
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY","").strip()
    if not api_key:
        return jsonify({"ok":False,"error":"GOOGLE_PLACES_API_KEY not set."}), 400
    data = request.json or {}
    industry  = data.get("industry", "plumbing")
    limit     = int(data.get("limit", 20))
    try:
        lat      = float(data["lat"])
        lng      = float(data["lng"])
        radius_m = float(data.get("radius_m", 5000))
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"ok":False,"error":f"lat/lng required and must be numeric: {exc}"}), 400
    if not (1000 <= radius_m <= 50000):
        return jsonify({"ok":False,"error":"radius_m must be between 1000 and 50000"}), 400
    from datetime import datetime as _dt
    try:
        # Count queue before pipeline run so we can compute drafts_created
        queue_before = len(_read_pending())

        new_prospect_rows = discover_prospects_area(
            industry=industry, lat=lat, lng=lng,
            radius_m=radius_m, api_key=api_key,
            limit=limit, scrape_emails=True,
        )
        prospects_added   = len(new_prospect_rows)
        ts = _dt.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        _append_search_history({
            "ts": ts, "city": f"{lat:.4f},{lng:.4f}", "state": "area",
            "industry": industry, "limit": limit,
            "found": prospects_added,
            "status": "ok" if prospects_added else "all_duplicates",
        })

        if not prospects_added:
            log.warning("discover_area 0 new: industry=%s lat=%.4f lng=%.4f r=%.0f",
                        industry, lat, lng, radius_m)
            return jsonify({
                "ok": False,
                "all_duplicates": True,
                "places_found": 0, "prospects_added": 0, "prospects_skipped": limit,
                "drafts_created": 0, "queue_total": queue_before,
                "markers": [],
                "error": "No new leads found — all results already in pipeline.",
            }), 200

        log.info("discover_area: added=%d industry=%s lat=%.4f lng=%.4f r=%.0f",
                 prospects_added, industry, lat, lng, radius_m)

        run_pipeline(input_csv=PROSPECTS_CSV, skip_scan=True)

        queue_after    = len(_read_pending())
        drafts_created = max(0, queue_after - queue_before)

        # Build lightweight marker list for the map
        markers = [
            {
                "name":     r.get("business_name", ""),
                "city":     r.get("city", ""),
                "email":    r.get("to_email", ""),
                "channel":  r.get("contact_method", ""),
                "lat":      r.get("lat", ""),
                "lng":      r.get("lng", ""),
                "place_id": r.get("place_id", ""),  # Pass 24: stable ID for panel matching
            }
            for r in new_prospect_rows
        ]

        return jsonify({
            "ok":               True,
            "places_found":     prospects_added,  # Places returned & not duplicate
            "prospects_added":  prospects_added,
            "prospects_skipped": max(0, limit - prospects_added),
            "drafts_created":   drafts_created,
            "queue_total":      queue_after,
            "markers":          markers,
        })

    except Exception as exc:
        log.error("discover_area error: %s", exc, exc_info=True)
        return jsonify({"ok":False,"error":str(exc)}), 500

@app.route("/api/discover_area_batch", methods=["POST"])
def api_discover_area_batch():
    """
    Run discover_area in a loop until the area is exhausted.

    Same input as /api/discover_area: { industry, lat, lng, radius_m, limit }

    Stop conditions (first to trigger):
      - 0 new prospects found in an iteration
      - < 5 new prospects found in an iteration
      - 25 iterations reached

    Returns: { ok, total_new, iterations_run, stopped_reason, queue_total, markers }
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "GOOGLE_PLACES_API_KEY not set."}), 400

    data     = request.json or {}
    industry = data.get("industry", "plumbing")
    limit    = int(data.get("limit", 20))  # hard-capped to 20 per spec

    try:
        lat      = float(data["lat"])
        lng      = float(data["lng"])
        radius_m = float(data.get("radius_m", 5000))
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": f"lat/lng required and must be numeric: {exc}"}), 400

    if not (1000 <= radius_m <= 50000):
        return jsonify({"ok": False, "error": "radius_m must be between 1000 and 50000"}), 400

    import time as _t
    from datetime import datetime as _dt

    MAX_ITERATIONS   = 25
    STOP_THRESHOLD   = 5   # stop if found < this
    ITER_DELAY       = 1.5  # seconds between iterations

    total_new      = 0
    iterations_run = 0
    stopped_reason = "max_iterations"
    all_markers    = []
    queue_before   = len(_read_pending())

    for iteration in range(1, MAX_ITERATIONS + 1):
        iterations_run = iteration
        try:
            new_rows = discover_prospects_area(
                industry=industry, lat=lat, lng=lng,
                radius_m=radius_m, api_key=api_key,
                limit=limit, scrape_emails=True,
            )
        except Exception as exc:
            log.error("discover_area_batch error at iteration %d: %s", iteration, exc, exc_info=True)
            stopped_reason = "error"
            break

        found = len(new_rows)
        log.info("discover_area_batch iter=%d found=%d industry=%s lat=%.4f lng=%.4f",
                 iteration, found, industry, lat, lng)

        ts = _dt.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        _append_search_history({
            "ts": ts, "city": f"{lat:.4f},{lng:.4f}", "state": "area",
            "industry": industry, "limit": limit,
            "found": found,
            "status": "ok" if found else "all_duplicates",
            "batch_iteration": iteration,
        })

        if found > 0:
            total_new += found
            all_markers.extend([
                {
                    "name":     r.get("business_name", ""),
                    "city":     r.get("city", ""),
                    "email":    r.get("to_email", ""),
                    "channel":  r.get("contact_method", ""),
                    "lat":      r.get("lat", ""),
                    "lng":      r.get("lng", ""),
                    "place_id": r.get("place_id", ""),
                }
                for r in new_rows
            ])

        if found == 0:
            stopped_reason = "no_results"
            break

        if found < STOP_THRESHOLD:
            stopped_reason = "diminishing_returns"
            break

        if iteration < MAX_ITERATIONS:
            _t.sleep(ITER_DELAY)

    # Run pipeline once after all iterations complete
    if total_new > 0:
        try:
            run_pipeline(input_csv=PROSPECTS_CSV, skip_scan=True)
        except Exception as exc:
            log.error("discover_area_batch pipeline error: %s", exc, exc_info=True)

    queue_after    = len(_read_pending())
    drafts_created = max(0, queue_after - queue_before)

    _city_planner.record_discovery(
        f"{lat:.4f},{lng:.4f}", "area", total_new, industry=industry
    )

    log.info("discover_area_batch done: total_new=%d iterations=%d reason=%s",
             total_new, iterations_run, stopped_reason)

    return jsonify({
        "ok":            True,
        "total_new":     total_new,
        "iterations_run": iterations_run,
        "stopped_reason": stopped_reason,
        "drafts_created": drafts_created,
        "queue_total":   queue_after,
        "markers":       all_markers,
    })


@app.route("/api/presets")
def api_presets(): return jsonify(_load_presets())

from datetime import datetime as _datetime, timezone as _tz, timedelta as _td
def _now_utc_iso(): return _datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _followup_iso(days): return (_datetime.now(_tz.utc)+_td(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

@app.route("/api/log_contact", methods=["POST"])
def api_log_contact():
    d = request.json or {}; idx = d.get("index"); channel = d.get("channel","email")
    result = d.get("result","sent"); campaign_key = d.get("campaign_key","")
    rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)): return jsonify({"ok":False,"error":"Invalid index"}),400
    row = rows[idx]; now = _now_utc_iso()
    if result not in ("replied",):
        try: count = int(row.get("contact_attempt_count") or 0)+1
        except: count = 1
        row["contact_attempt_count"] = str(count)
    row["last_contact_channel"] = channel; row["last_contacted_at"] = now; row["contact_result"] = result
    if campaign_key: row["campaign_key"] = campaign_key
    if result not in _TERMINAL_RESULTS:
        row["next_followup_at"] = _followup_iso(_preset_followup_days(campaign_key or row.get("campaign_key","")))
    else:
        row["next_followup_at"] = ""
    if result == "sent" and not row.get("sent_at"): row["sent_at"] = now
    _write_pending(rows); log.info("contact_logged idx=%s channel=%s result=%s",idx,channel,result)
    return jsonify({"ok":True,"row":row})

@app.route("/api/snooze_row", methods=["POST"])
def api_snooze_row():
    d = request.json or {}; idx = d.get("index"); days = int(d.get("days",7))
    rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)): return jsonify({"ok":False,"error":"Invalid index"}),400
    rows[idx]["next_followup_at"] = _followup_iso(days)
    rows[idx]["contact_result"] = rows[idx].get("contact_result") or "no_reply"
    _write_pending(rows); return jsonify({"ok":True})

@app.route("/api/schedule_email", methods=["POST"])
def api_schedule_email():
    """
    Record send intent for a queue row by writing send_after.
    Does NOT trigger a send. Does NOT modify any other field.

    Accepts two scheduling modes:
      1. Explicit: send_after = "<ISO string>"  — stores exactly as provided
      2. Window:   days_ahead = <int>           — builds timestamp using industry window
         (send_after absent or empty triggers window mode when days_ahead provided)

    send_after = "" clears an existing schedule in both modes.
    """
    d             = request.json or {}
    idx           = d.get("index")
    business_name = (d.get("business_name") or "").strip()
    send_after_raw = d.get("send_after")
    days_ahead     = d.get("days_ahead")  # optional int — triggers industry window mode

    # Validate identity fields
    if idx is None or not isinstance(idx, int):
        return jsonify({"ok": False, "error": "index is required and must be an integer"}), 400
    if not business_name:
        return jsonify({"ok": False, "error": "business_name is required"}), 400

    rows = _read_pending()
    if not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400

    row_name = rows[idx].get("business_name", "").strip().lower()
    if row_name != business_name.lower():
        return jsonify({"ok": False, "error": "Row index/name mismatch — queue may have changed"}), 409

    # Determine the send_after value to store
    if send_after_raw is not None:
        # Explicit mode: use whatever was provided (including "" to clear)
        send_after = send_after_raw.strip()
    elif days_ahead is not None:
        # Window mode: compute industry-appropriate timestamp
        try:
            days_ahead_int = int(days_ahead)
            if days_ahead_int < 1:
                return jsonify({"ok": False, "error": "days_ahead must be >= 1"}), 400
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "days_ahead must be an integer"}), 400
        industry = (rows[idx].get("industry") or "default").strip().lower()
        send_after = _schedule_send_after(industry, days_ahead=days_ahead_int)
    else:
        return jsonify({"ok": False, "error": "send_after or days_ahead is required (use send_after=\"\" to clear)"}), 400

    # Write send_after only — no other fields touched
    rows[idx]["send_after"] = send_after
    _write_pending(rows)
    action = "cleared" if not send_after else "scheduled"
    log.info("schedule_email %s idx=%s business=%r send_after=%r", action, idx, business_name, send_after)
    return jsonify({"ok": True, "send_after": send_after})

@app.route("/api/social_queue")
def api_social_queue():
    rows = _read_pending(); result = []
    for i,r in enumerate(rows):
        if (r.get("contact_result") or "").strip() in _TERMINAL_RESULTS: continue
        if r.get("to_email","").strip(): continue
        has_fb = bool(r.get("facebook_url","").strip()); has_ig = bool(r.get("instagram_url","").strip()); has_form = bool(r.get("contact_form_url","").strip())
        if not (has_fb or has_ig or has_form): continue
        _enrich_row(r,i); result.append({**r,"best_channel":"facebook" if has_fb else ("instagram" if has_ig else "contact_form")})
    result.sort(key=lambda x:x["opp_score"],reverse=True); return jsonify(result)

@app.route("/api/queue_routed")
def api_queue_routed():
    rows = _read_pending(); eq=[]; fq=[]; sq=[]; nq=[]
    for i,r in enumerate(rows):
        if (r.get("contact_result") or "").strip() in _TERMINAL_RESULTS: continue
        _enrich_row(r,i)
        if r.get("to_email","").strip(): eq.append(r)
        elif r.get("contact_form_url","").strip(): fq.append(r)
        elif r.get("facebook_url","").strip() or r.get("instagram_url","").strip(): sq.append(r)
        else: nq.append(r)
    for b in (eq,fq,sq,nq): b.sort(key=lambda x:x["opp_score"],reverse=True)
    return jsonify({"email":eq,"contact_form":fq,"social":sq,"no_contact":nq,
                    "counts":{"email":len(eq),"contact_form":len(fq),"social":len(sq),"no_contact":len(nq),"total":len(eq)+len(fq)+len(sq)+len(nq)}})

@app.route("/api/sprint_next")
def api_sprint_next():
    cf = request.args.get("channel","any").strip().lower(); rows = _read_pending(); cands = []
    for i,r in enumerate(rows):
        if (r.get("contact_result") or "").strip() in _TERMINAL_RESULTS: continue
        if r.get("sent_at","").strip(): continue
        if cf=="email" and not r.get("to_email","").strip(): continue
        if cf=="social" and not (r.get("facebook_url","").strip() or r.get("instagram_url","").strip()): continue
        if cf=="form" and not r.get("contact_form_url","").strip(): continue
        try: score = int(r.get("opportunity_score") or 0)
        except: score = 0
        if not score: _enrich_row(r,i); score = r["opp_score"]
        else: r["opp_score"]=score; r["opp_priority"]=score_priority_label(score); r["index"]=i
        if r.get("to_email","").strip(): best,draft="email",r.get("body","")
        elif r.get("contact_form_url","").strip(): best,draft="contact_form",r.get("contact_form_message","") or r.get("body","")
        elif r.get("facebook_url","").strip(): best,draft="facebook",r.get("facebook_dm_draft","") or r.get("social_dm_text","")
        elif r.get("instagram_url","").strip(): best,draft="instagram",r.get("instagram_dm_draft","") or r.get("social_dm_text","")
        else: continue
        cands.append({**r,"best_channel":best,"sprint_draft":draft})
    if not cands: return jsonify({"ok":False,"lead":None,"message":"No more leads in sprint queue."})
    cands.sort(key=lambda x:x["opp_score"],reverse=True); lead=cands[0]
    lead["priority_label"]=lead.get("opp_priority",score_priority_label(lead.get("opp_score",0)))
    return jsonify({"ok":True,"lead":lead,"remaining":len(cands)-1})

@app.route("/api/conversation_queue")
def api_conversation_queue():
    rows = _read_pending(); convos = []
    for i,r in enumerate(rows):
        if (r.get("replied") or "").lower()=="true": _enrich_row(r,i); convos.append(r)
    convos.sort(key=lambda r:r.get("replied_at",""),reverse=True); return jsonify(convos)

@app.route("/api/update_conversation", methods=["POST"])
def api_update_conversation():
    d = request.json or {}; idx = d.get("index"); rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)): return jsonify({"ok":False,"error":"Invalid index"}),400
    rows[idx]["conversation_notes"] = d.get("notes",rows[idx].get("conversation_notes",""))
    rows[idx]["conversation_next_step"] = d.get("next_step",rows[idx].get("conversation_next_step",""))
    _write_pending(rows); return jsonify({"ok":True})

# ── Follow-up status helpers (Pass 22) ───────────────────────────────────────
# Schedule: touch1=sent_at, touch2=+2d, touch3=+5d, touch4=+10d
_FOLLOWUP_SCHEDULE = [2, 5, 10]  # days after sent_at for each follow-up touch

def compute_followup_status(row: dict) -> dict:
    """
    Compute follow-up status and next_due for a queue row.

    Returns dict with:
      status: "none" | "waiting" | "due" | "completed"
      next_due: ISO string or ""
      touch_num: int (which follow-up touch this would be, 1-3)

    Uses existing fields: sent_at, contact_attempt_count, replied.
    No new CSV columns required.
    """
    sent_raw = (row.get("sent_at") or "").strip()
    if not sent_raw:
        return {"status": "none", "next_due": "", "touch_num": 0}

    # Replied or terminal — completed
    if (row.get("replied") or "").lower() == "true":
        return {"status": "completed", "next_due": "", "touch_num": 0}
    if (row.get("contact_result") or "").strip() in _TERMINAL_RESULTS:
        return {"status": "completed", "next_due": "", "touch_num": 0}

    try:
        attempt_count = int(row.get("contact_attempt_count") or 0)
    except (ValueError, TypeError):
        attempt_count = 0

    # attempt_count = 0 means initial send only. Follow-up touches are 1, 2, 3.
    # After 3 follow-ups (attempt_count >= 3) → completed
    if attempt_count >= 3:
        return {"status": "completed", "next_due": "", "touch_num": 0}

    touch_num = attempt_count + 1  # next touch to send (1, 2, or 3)
    days_offset = _FOLLOWUP_SCHEDULE[attempt_count]  # index 0→2d, 1→5d, 2→10d

    try:
        sent_dt = _datetime.fromisoformat(sent_raw.replace("Z", "+00:00"))
        # Compare in UTC
        next_due_dt = sent_dt + _td(days=days_offset)
        now = _datetime.now(_tz.utc)
        if not next_due_dt.tzinfo:
            next_due_dt = next_due_dt.replace(tzinfo=_tz.utc)
        status = "due" if now >= next_due_dt else "waiting"
        return {"status": status, "next_due": next_due_dt.isoformat(), "touch_num": touch_num}
    except (ValueError, TypeError):
        return {"status": "none", "next_due": "", "touch_num": 0}


@app.route("/api/followups_due")
def api_followups_due():
    """
    Return rows where follow-up is currently due, sorted by next_due ascending.
    Excludes rows with no real send, already replied, or in terminal state.
    """
    rows = _read_pending()
    due = []
    for i, row in enumerate(rows):
        fs = compute_followup_status(row)
        if fs["status"] != "due":
            continue
        _enrich_row(row, i)
        row["followup_status"] = fs["status"]
        row["followup_next_due"] = fs["next_due"]
        row["followup_touch_num"] = fs["touch_num"]
        due.append(row)
    due.sort(key=lambda r: r.get("followup_next_due") or "")
    return jsonify(due)


@app.route("/api/send_followup", methods=["POST"])
def api_send_followup():
    """
    Generate and send a follow-up email for a specific queue row.

    Input: { index, business_name }

    Behavior:
    - Validates row identity (index + business_name match)
    - Confirms follow-up is actually due
    - Generates short follow-up message
    - Sends via Gmail SMTP
    - Increments contact_attempt_count
    - Updates last_contacted_at
    - Sets contact_result = "sent" if not already in terminal state
    - Does NOT touch sent_at (that field tracks the initial send only)
    """
    from send.email_sender_agent import _send_email_via_gmail, _append_signature
    d = request.json or {}
    idx           = d.get("index")
    business_name = (d.get("business_name") or "").strip()

    if idx is None or not isinstance(idx, int):
        return jsonify({"ok": False, "error": "index is required and must be an integer"}), 400
    if not business_name:
        return jsonify({"ok": False, "error": "business_name is required"}), 400

    rows = _read_pending()
    if not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400

    row = rows[idx]
    if row.get("business_name", "").strip().lower() != business_name.lower():
        return jsonify({"ok": False, "error": "Row index/name mismatch — queue may have changed"}), 409

    fs = compute_followup_status(row)
    if fs["status"] != "due":
        return jsonify({"ok": False, "error": f"Follow-up not due (status: {fs['status']})"}), 400

    to_email = (row.get("to_email") or "").strip()
    if not to_email or "@" not in to_email:
        return jsonify({"ok": False, "error": "No valid email address for this row"}), 400

    touch_num = fs["touch_num"]
    name      = row.get("business_name", "").strip()
    city      = row.get("city", "").strip()
    industry  = (row.get("industry") or "").replace("_", " ").strip()

    # Generate short follow-up copy — conversational, no pitch language
    if touch_num == 1:
        subject = "Re: quick question"
        body = (
            f"hey {name} — just following up on my note from last week.\n\n"
            f"i set up a simple missed-call text-back for a few {industry} businesses in {city} "
            f"and it's been catching a lot of after-hours calls they were losing. "
            f"happy to show you a quick example if you're curious.\n\n"
            "– Drew"
        )
    elif touch_num == 2:
        subject = "Re: quick question"
        body = (
            f"hey {name} — one more note before i move on.\n\n"
            f"if the timing's off or you've already got something in place, no worries at all. "
            f"just didn't want to disappear without checking.\n\n"
            "– Drew"
        )
    else:
        subject = "last note"
        body = (
            f"hey {name} — last one from me.\n\n"
            f"if things change and you want to talk about how to stop losing after-hours calls, "
            f"i'm easy to reach. good luck with the busy season.\n\n"
            "– Drew"
        )

    try:
        message_id = _send_email_via_gmail(to_email, subject, body)
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    except Exception as exc:
        log.error("send_followup SMTP error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": f"Send failed: {exc}"}), 500

    # Update row state — increment attempt count, log contact time
    now_str = _now_utc_iso()
    try:
        prev_count = int(row.get("contact_attempt_count") or 0)
    except (ValueError, TypeError):
        prev_count = 0
    row["contact_attempt_count"] = str(prev_count + 1)
    row["last_contacted_at"]     = now_str
    row["last_contact_channel"]  = "email"
    if (row.get("contact_result") or "").strip() not in _TERMINAL_RESULTS:
        row["contact_result"] = "sent"

    _write_pending(rows)
    log.info("send_followup ok: idx=%s name=%r touch=%d to=%s mid=%s",
             idx, name, touch_num, to_email, message_id)
    return jsonify({"ok": True, "touch_num": touch_num, "message_id": message_id})


@app.route("/api/followup_queue")
def api_followup_queue():
    rows = _read_pending(); now = _datetime.now(_tz.utc)
    today_end = now.replace(hour=23,minute=59,second=59); week_end = now+_td(days=7)
    overdue=[]; today=[]; this_week=[]; upcoming=[]
    for i,r in enumerate(rows):
        if (r.get("contact_result") or "").strip() in _TERMINAL_RESULTS: continue
        fs = (r.get("next_followup_at") or "").strip(); ss = (r.get("sent_at") or "").strip()
        if not fs and not ss: continue
        try:
            if not fs and ss: fdt = _datetime.fromisoformat(ss.replace("Z","+00:00"))+_td(days=_DEFAULT_FOLLOWUP_DAYS)
            else: fdt = _datetime.fromisoformat(fs.replace("Z","+00:00"))
        except: continue
        _enrich_row(r,i)
        fs_info = compute_followup_status(r)
        entry = {**r,"followup_dt":fdt.isoformat(),"followup_status":fs_info["status"],"followup_touch_num":fs_info["touch_num"],"followup_next_due":fs_info["next_due"]}
        if fdt < now: overdue.append(entry)
        elif fdt <= today_end: today.append(entry)
        elif fdt <= week_end: this_week.append(entry)
        else: upcoming.append(entry)
    for g in (overdue,today,this_week,upcoming): g.sort(key=lambda e:e["followup_dt"])
    return jsonify({"overdue":overdue,"today":today,"this_week":this_week,"upcoming":upcoming,
                    "counts":{"overdue":len(overdue),"today":len(today),"this_week":len(this_week),"upcoming":len(upcoming),"total":len(overdue)+len(today)+len(this_week)+len(upcoming)}})

TERRITORY_INDUSTRIES = ["plumbing","hvac","electrical","roofing","locksmith","garage_door","pest_control","cleaning","landscaping","towing"]

@app.route("/api/territory")
def api_territory(): return jsonify({"cities":_city_planner.get_industry_matrix(TERRITORY_INDUSTRIES),"industries":TERRITORY_INDUSTRIES})

@app.route("/api/territory/next_industry", methods=["POST"])
def api_territory_next_industry():
    d = request.json or {}; city = d.get("city","").strip(); state = d.get("state","").strip()
    if not city or not state: return jsonify({"ok":False,"error":"city and state required"}),400
    entry = _city_planner._find(city,state); ci = entry.get("industries",{}) if entry else {}
    for ind in TERRITORY_INDUSTRIES:
        rec = ci.get(ind)
        if not rec: return jsonify({"ok":True,"industry":ind,"reason":"never_run"})
        if rec.get("status")=="due": return jsonify({"ok":True,"industry":ind,"reason":"due"})
    oldest = min(TERRITORY_INDUSTRIES, key=lambda i: ci.get(i,{}).get("last_checked_at") or "0000")
    return jsonify({"ok":True,"industry":oldest,"reason":"all_covered_oldest"})

@app.route("/api/territory/skip_industry", methods=["POST"])
def api_territory_skip_industry():
    d = request.json or {}; city=d.get("city","").strip(); state=d.get("state","").strip(); industry=d.get("industry","").strip()
    if not city or not state or not industry: return jsonify({"ok":False,"error":"city, state, industry required"}),400
    _city_planner.ensure_city(city,state).setdefault("industries",{}).setdefault(industry,{"leads_found":0,"last_checked_at":None,"new_leads_last_run":0,"status":"never_checked"})["status"]="skipped"
    _city_planner._save(); return jsonify({"ok":True})

@app.route("/api/territory/mark_exhausted", methods=["POST"])
def api_territory_mark_exhausted():
    d = request.json or {}; city=d.get("city","").strip(); state=d.get("state","").strip(); industry=d.get("industry","").strip()
    if not city or not state or not industry: return jsonify({"ok":False,"error":"city, state, industry required"}),400
    _city_planner.ensure_city(city,state).setdefault("industries",{}).setdefault(industry,{"leads_found":0,"last_checked_at":None,"new_leads_last_run":0,"status":"never_checked"})["status"]="exhausted"
    _city_planner._save(); return jsonify({"ok":True})

@app.route("/api/city_leads")
def api_city_leads():
    city = request.args.get("city","").strip().lower(); state = request.args.get("state","").strip().lower()
    return jsonify([r for r in _read_pending() if r.get("city","").strip().lower()==city and (not state or r.get("state","").strip().lower()==state)])

@app.route("/api/opt_out_row", methods=["POST"])
def api_opt_out_row():
    idx = request.json.get("index"); rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)): return jsonify({"ok":False,"error":"Invalid index"}),400
    rows[idx]["do_not_contact"]="true"; rows[idx]["approved"]="false"; _write_pending(rows)
    name = rows[idx].get("business_name","").strip().lower()
    if name and PROSPECTS_CSV.exists():
        with PROSPECTS_CSV.open("r",newline="",encoding="utf-8-sig") as f:
            reader=csv.DictReader(f); fieldnames=list(reader.fieldnames or []); prows=list(reader)
        if "do_not_contact" not in fieldnames: fieldnames.append("do_not_contact")
        for pr in prows:
            if pr.get("business_name","").strip().lower()==name: pr["do_not_contact"]="true"
        with PROSPECTS_CSV.open("w",newline="",encoding="utf-8") as f:
            writer=csv.DictWriter(f,fieldnames=fieldnames); writer.writeheader(); writer.writerows(prows)
    log.info("opt_out name=%s",name); return jsonify({"ok":True})

@app.route("/api/reset_prospect_status", methods=["POST"])
def api_reset_prospect_status():
    bn = (request.json.get("business_name") or "").strip().lower()
    if not bn or not PROSPECTS_CSV.exists(): return jsonify({"ok":False,"error":"business_name required"}),400
    with PROSPECTS_CSV.open("r",newline="",encoding="utf-8-sig") as f:
        reader=csv.DictReader(f); fieldnames=list(reader.fieldnames or []); rows=list(reader)
    updated=0
    for row in rows:
        if row.get("business_name","").strip().lower()==bn: row["status"]="new"; updated+=1
    if updated:
        with PROSPECTS_CSV.open("w",newline="",encoding="utf-8") as f:
            writer=csv.DictWriter(f,fieldnames=fieldnames); writer.writeheader(); writer.writerows(rows)
    return jsonify({"ok":True,"updated":updated})

# ── Queue Health ──────────────────────────────────────────────────────────────
@app.route("/api/queue_health")
def api_queue_health():
    try: return jsonify({"ok":True,"health":scan_queue_integrity(PENDING_CSV)})
    except Exception as exc:
        log.error("queue_health error: %s",exc,exc_info=True)
        return jsonify({"ok":False,"error":str(exc)}),500

# ── Exception Queue (Phase B) ─────────────────────────────────────────────────
@app.route("/api/exceptions")
def api_exceptions():
    """
    Return all queue rows flagged with one or more exception conditions.

    Response:
      ok              bool
      total_rows      int   — total queue size
      exception_rows  int   — rows with at least one flag
      counts          dict  — {FLAG: count} for all 8 supported flags
      rows            list  — rows with exception_flags field appended
    """
    try:
        report = scan_exceptions(PENDING_CSV)
        return jsonify({"ok": True, **report})
    except Exception as exc:
        log.error("exceptions error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

# ── Missed Call Product ───────────────────────────────────────────────────────
def _mc_load_clients() -> list:
    actual = BASE_DIR.parent/"missed_call_product"/"clients.json"
    example = BASE_DIR.parent/"missed_call_product"/"clients.example.json"
    path = actual if actual.exists() else example
    if not path.exists(): return []
    try:
        with path.open(encoding="utf-8") as f: return json.load(f)
    except: return []

@app.route("/api/clients")
def api_clients(): return jsonify(_mc_load_clients())

@app.route("/api/clients/add", methods=["POST"])
def api_clients_add():
    d = request.json or {}; clients_path = BASE_DIR.parent/"missed_call_product"/"clients.json"
    clients = _mc_load_clients()
    nc = {"id":d.get("id",""),"business_name":d.get("business_name",""),"phone":d.get("phone",""),
          "sms_reply":d.get("sms_reply",""),"owner_email":d.get("owner_email",""),"active":d.get("active",True)}
    clients.append(nc); clients_path.parent.mkdir(parents=True,exist_ok=True)
    with clients_path.open("w",encoding="utf-8") as f: json.dump(clients,f,indent=2)
    log.info("client_added id=%s name=%s",nc["id"],nc["business_name"]); return jsonify({"ok":True,"client":nc})

@app.route("/api/demo_run", methods=["POST"])
def api_demo_run():
    d = request.json or {}; cid = d.get("client_id","demo"); bn = d.get("business_name","Demo Business"); cn = d.get("caller_number","+15555555555")
    steps = {"sms":{"ok":False,"detail":""},"sheet":{"ok":False,"detail":""},"notify":{"ok":False,"detail":""}}
    try:
        from missed_call_product.sms import send_sms; send_sms(cn,f"Hi! Thanks for calling {bn}. We'll follow up shortly."); steps["sms"]={"ok":True,"detail":f"SMS sent to {cn}"}
    except Exception as exc: steps["sms"]["detail"]=f"Failed: {exc}"; log.error("demo_run sms_failed | client=%s error=%s",cid,exc)
    try:
        from missed_call_product.sheets import log_missed_call; log_missed_call(cid,cn,bn); steps["sheet"]={"ok":True,"detail":"Logged to sheet"}
    except Exception as exc: steps["sheet"]["detail"]=f"Failed: {exc}"; log.error("demo_run sheet_failed | client=%s error=%s",cid,exc)
    try:
        from missed_call_product.notifier import notify_owner; notify_owner(cid,cn); steps["notify"]={"ok":True,"detail":"Owner notified"}
    except Exception as exc: steps["notify"]["detail"]=f"Failed: {exc}"; log.error("demo_run notify_failed | client=%s error=%s",cid,exc)
    log.info("demo_run complete | client=%s sms=%s sheet=%s notify=%s",cid,steps["sms"]["ok"],steps["sheet"]["ok"],steps["notify"]["ok"])
    return jsonify({"ok":any(s["ok"] for s in steps.values()),"client_id":cid,"business_name":bn,"steps":steps})

@app.route("/api/mc/health")
def mc_api_health():
    try:
        import urllib.request as _ur; mc_port = os.getenv("MISSED_CALL_PORT","8080")
        with _ur.urlopen(f"http://localhost:{mc_port}/health",timeout=3) as r: body=json.loads(r.read().decode())
        return jsonify({"ok":True,"service":{**body,"clients_loaded":body.get("clients_loaded",len(_mc_load_clients()))}})
    except Exception as exc: return jsonify({"ok":False,"error":str(exc)})

# ── Automated scheduler ───────────────────────────────────────────────────────
import threading as _threading_ds
import time as _time

_scheduler_started = False


def scheduler_loop() -> None:
    """
    Background thread: sends scheduled emails as their send_after time arrives.

    Loop behavior:
      - If an email was sent: sleep 5s (catch-up for multiple due emails)
      - If nothing was due: sleep 30s (idle poll)

    One email per iteration. No batching.
    Thread is daemon — exits automatically when the main process exits.
    """
    log.info("[scheduler] Auto-send runner started.")
    while True:
        try:
            sent = send_next_due_email(PENDING_CSV)
            if sent:
                _time.sleep(5)
            else:
                _time.sleep(30)
        except Exception as exc:
            log.error("[scheduler] Unexpected error: %s", exc, exc_info=True)
            _time.sleep(30)


def _start_scheduler_once() -> None:
    """Start the scheduler background thread exactly once."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    t = _threading_ds.Thread(target=scheduler_loop, daemon=True, name="copperline-scheduler")
    t.start()
    log.info("[scheduler] Thread started (daemon=True).")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8","utf_8"):
        try:
            import io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8",errors="replace")
        except: pass
    print(); print("  +------------------------------------------------+")
    print("  |  Copperline -- Lead Operations                 |")
    print("  |  Opening at  http://localhost:5000             |")
    print("  +------------------------------------------------+"); print()
    Timer(1.2,lambda: webbrowser.open("http://localhost:5000")).start()
    _start_scheduler_once()
    app.run(host="127.0.0.1",port=5000,debug=False)
