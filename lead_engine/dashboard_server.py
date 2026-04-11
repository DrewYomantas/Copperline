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
import math
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
from send.email_sender_agent import (
    process_pending_emails,
    is_real_send,
    send_next_due_email,
    CSV_WRITE_LOCK,
    _is_send_eligible,
    get_send_readiness,
    _parse_send_after_local,
)
from send.mail_config import mail_status_payload
from intelligence.email_extractor_agent import enrich_prospects_with_emails
from intelligence.observation_evidence_agent import refresh_observation_evidence
from discovery.auto_prospect_agent import (
    discover_prospects,
    INDUSTRY_QUERIES,
    PROSPECTS_COLUMNS,
    discover_prospects_area,
)
from outreach.followup_scheduler import run_followup_scheduler
from outreach.followup_draft_agent import build_followup_plan, FollowupBlockedError
from outreach.observation_candidate_agent import (
    build_observation_candidate,
    ObservationCandidateBlockedError,
    ObservationValidationError,
    validate_observation_text,
)
from outreach.reply_checker import check_for_replies, reconcile_sent_mail
from outreach.email_draft_agent import DRAFT_VERSION as _CURRENT_DRAFT_VERSION
from city_planner import CityPlanner
import lead_memory as _lm  # Pass 44: durable lead memory + suppression registry
from stranded_drafted import scan_stranded_drafted
from delivery_kits import get_catalog_payload, compute_stack_truth, DELIVERY_CATALOG, PRELAUNCH_MODE

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
GMAIL_SENT_CSV      = BASE_DIR / "scripts" / "gmail_sent_preserve_set_for_reset.csv"
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
    "business_specific_observation",
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
TERRITORY_CELL_DEGREES = 0.02

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


def _read_prospects() -> list:
    if not PROSPECTS_CSV.exists():
        return []
    with PROSPECTS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _read_prospects_with_fieldnames() -> tuple[list, list[str]]:
    if not PROSPECTS_CSV.exists():
        return [], list(PROSPECTS_COLUMNS)
    with PROSPECTS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or PROSPECTS_COLUMNS)
        rows = [dict(row) for row in reader]
    return rows, fieldnames


def _write_prospects(rows: list, fieldnames: list[str]) -> None:
    safe_fieldnames = fieldnames or list(PROSPECTS_COLUMNS)
    safe_rows = [{col: row.get(col, "") for col in safe_fieldnames} for row in rows]
    with CSV_WRITE_LOCK:
        with PROSPECTS_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=safe_fieldnames)
            writer.writeheader()
            writer.writerows(safe_rows)


def _find_matching_prospect(row: dict, prospects: list) -> dict | None:
    if not row or not prospects:
        return None
    queue_key = _lm.lead_key(row)
    for prospect in prospects:
        if _lm.lead_key(prospect) == queue_key:
            return prospect
    return None


def _find_matching_prospect_index(row: dict, prospects: list) -> int | None:
    if not row or not prospects:
        return None
    queue_key = _lm.lead_key(row)
    for idx, prospect in enumerate(prospects):
        if _lm.lead_key(prospect) == queue_key:
            return idx
    return None


def _float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_area_coords(city_value: str, state_value: str) -> tuple[float | None, float | None]:
    if (state_value or "").strip().lower() != "area":
        return None, None
    raw = (city_value or "").strip()
    if "," not in raw:
        return None, None
    lat_str, lng_str = raw.split(",", 1)
    lat = _float_or_none(lat_str.strip())
    lng = _float_or_none(lng_str.strip())
    if lat is None or lng is None:
        return None, None
    return lat, lng


def _territory_bucket(lat: float, lng: float, *, cell_degrees: float = TERRITORY_CELL_DEGREES) -> dict:
    lat_idx = math.floor(lat / cell_degrees)
    lng_idx = math.floor(lng / cell_degrees)
    min_lat = lat_idx * cell_degrees
    min_lng = lng_idx * cell_degrees
    max_lat = min_lat + cell_degrees
    max_lng = min_lng + cell_degrees
    return {
        "key": f"{lat_idx}:{lng_idx}",
        "min_lat": round(min_lat, 6),
        "min_lng": round(min_lng, 6),
        "max_lat": round(max_lat, 6),
        "max_lng": round(max_lng, 6),
        "center_lat": round(min_lat + (cell_degrees / 2), 6),
        "center_lng": round(min_lng + (cell_degrees / 2), 6),
    }


def _territory_cell(cells: dict, lat: float, lng: float) -> dict:
    bucket = _territory_bucket(lat, lng)
    key = bucket["key"]
    if key not in cells:
        cells[key] = {
            **bucket,
            "lead_count": 0,
            "lead_status_counts": {},
            "lead_industries": {},
            "lead_email_count": 0,
            "search_count": 0,
            "search_ok_count": 0,
            "search_duplicate_count": 0,
            "search_error_count": 0,
            "search_found_total": 0,
            "search_industries": {},
            "search_ok_by_industry": {},
            "search_duplicate_by_industry": {},
            "search_found_by_industry": {},
            "last_search_at": "",
            "planner_area_records": 0,
            "planner_checked_count": 0,
            "planner_leads_total": 0,
            "planner_checked_by_industry": {},
            "planner_leads_by_industry": {},
            "planner_last_checked_at": "",
            "recommended_radius_m": 1600,
        }
    return cells[key]


def _bump(counter: dict, key: str, amount: int = 1) -> None:
    if not key:
        return
    counter[key] = int(counter.get(key, 0) or 0) + int(amount or 0)

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
    stranded = scan_stranded_drafted(PROSPECTS_CSV, PENDING_CSV, GMAIL_SENT_CSV if GMAIL_SENT_CSV.exists() else None, sample_limit=5)
    readiness = [get_send_readiness(r) for r in rows]
    return jsonify({
        "prospects_loaded":      _prospects_count(),
        "total_drafted":         len(rows),
        "pending_approval":      sum(1 for r, truth in zip(rows, readiness) if not r.get("sent_at") and truth.get("draft_valid") and not truth.get("is_send_ready")),
        "approved_unsent":       sum(1 for r, truth in zip(rows, readiness) if not r.get("sent_at") and truth.get("is_send_ready")),
        "sent":                  sent_real,
        "sent_logged_only":      sent_logged,
        "replied":               sum(1 for r in rows if (r.get("replied") or "").lower() == "true"),
        "stale_drafts":          stale,
        "stranded_drafted_missing_queue": stranded["recoverable_count"],
        "current_draft_version": _CURRENT_DRAFT_VERSION,
        "mail":                  mail_status_payload(),
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
        send_after_dt = _parse_send_after_local(send_after_raw)
        row["is_ready"] = bool(send_after_dt and send_after_dt <= now_local)
        readiness = get_send_readiness(row)
        row["send_ready"] = readiness["is_send_ready"]
        row["send_ready_blocked_reason"] = readiness["blocked_reason"]
        row["send_ready_blocked_message"] = readiness["blocked_message"]
        row["draft_valid"] = readiness["draft_valid"]
        row["draft_blocked_reason"] = readiness["draft_blocked_reason"]
        row["draft_blocked_message"] = readiness["draft_blocked_message"]
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
    readiness = get_send_readiness({**rows[idx], "approved": "true"})
    if not readiness["draft_valid"]:
        return jsonify({
            "ok": False,
            "blocked": True,
            "blocked_reason": readiness["draft_blocked_reason"],
            "error": readiness["draft_blocked_message"] or "Draft is not valid for approval.",
        }), 422
    if not (rows[idx].get("to_email") or "").strip():
        return jsonify({
            "ok": False,
            "blocked": True,
            "blocked_reason": "no_email",
            "error": "Add a To Email before approval.",
        }), 422
    rows[idx]["approved"] = "true"
    _write_pending(rows)
    try: _lm.record_event(rows[idx], _lm.EVT_APPROVED)
    except Exception as _e: log.warning("lead_memory event failed (approved): %s", _e)
    return jsonify({"ok": True})

@app.route("/api/unapprove_row", methods=["POST"])
def api_unapprove_row():
    idx = request.json.get("index"); rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    rows[idx]["approved"] = "false"
    _write_pending(rows)
    try: _lm.record_event(rows[idx], _lm.EVT_UNAPPROVED)
    except Exception as _e: log.warning("lead_memory event failed (unapproved): %s", _e)
    return jsonify({"ok": True})

@app.route("/api/approve_all", methods=["POST"])
def api_approve_all():
    rows = _read_pending(); count = 0
    for row in rows:
        if row["sent_at"]:
            continue
        readiness = get_send_readiness({**row, "approved": "true"})
        if readiness["draft_valid"] and (row.get("to_email") or "").strip():
            row["approved"] = "true"
            count += 1
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
    # Pass 44: record durable memory BEFORE removing from queue
    try:
        _lm.record_suppression(rows[idx], "deleted_intentionally",
                               note="deleted from queue by operator")
    except Exception as _lm_exc:
        log.warning("lead_memory record failed on delete: %s", _lm_exc)
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
            followup_eligible, _followup_step, _read_pending,
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
        blocked_preview = []
        for row in rows:
            if not _is_real_send(row):
                continue
            eligible, _ = followup_eligible(row, now, unsent_keys)
            if eligible:
                step = _followup_step(row, now)
                try:
                    plan = build_followup_plan(row, step)
                except FollowupBlockedError as exc:
                    blocked_preview.append({
                        "business_name": row.get("business_name", ""),
                        "to_email": row.get("to_email", ""),
                        "sent_at": row.get("sent_at", ""),
                        "followup_step": step,
                        "blocked_reason": exc.reason,
                        "error": str(exc),
                    })
                    continue

                preview.append({
                    "business_name": row.get("business_name", ""),
                    "to_email": row.get("to_email", ""),
                    "sent_at": row.get("sent_at", ""),
                    "followup_step": step,
                    "contact_attempt_count": row.get("contact_attempt_count", "0"),
                    "angle_family": plan["angle_family"],
                    "angle_label": plan["angle_label"],
                    "context_source": plan["context"].get("anchor_source", ""),
                })

        return jsonify({
            "ok": True,
            "preview": preview,
            "blocked_preview": blocked_preview,
            "count": len(preview),
            "blocked_count": len(blocked_preview),
        })
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


@app.route("/api/map_territory_overlay")
def api_map_territory_overlay():
    """
    Build a coarse territory overlay from persisted discovery/search evidence.

    Data sources:
      - prospects.csv lat/lng rows
      - search_history.json area searches
      - city_planner.json AREA entries

    Returns coarse territory cells only. This is neighborhood guidance, not an
    exact boundary system.
    """
    cells: dict[str, dict] = {}
    prospects = _read_prospects()
    search_history = _load_search_history()
    planner_rows = _city_planner.all_cities()

    for row in prospects:
        lat = _float_or_none(row.get("lat"))
        lng = _float_or_none(row.get("lng"))
        if lat is None or lng is None:
            continue
        cell = _territory_cell(cells, lat, lng)
        cell["lead_count"] += 1
        status = (row.get("status") or "").strip().lower() or "unknown"
        _bump(cell["lead_status_counts"], status)
        industry = (row.get("industry") or "").strip().lower()
        _bump(cell["lead_industries"], industry)
        if (row.get("to_email") or "").strip():
            cell["lead_email_count"] += 1

    for entry in search_history:
        lat, lng = _parse_area_coords(entry.get("city", ""), entry.get("state", ""))
        if lat is None or lng is None:
            continue
        cell = _territory_cell(cells, lat, lng)
        status = (entry.get("status") or "").strip().lower() or "unknown"
        industry = (entry.get("industry") or "").strip().lower()
        found = _int_or_zero(entry.get("found"))
        cell["search_count"] += 1
        cell["search_found_total"] += found
        _bump(cell["search_industries"], industry)
        _bump(cell["search_found_by_industry"], industry, found)
        if status == "ok":
            cell["search_ok_count"] += 1
            _bump(cell["search_ok_by_industry"], industry)
        elif status == "all_duplicates":
            cell["search_duplicate_count"] += 1
            _bump(cell["search_duplicate_by_industry"], industry)
        elif status == "error":
            cell["search_error_count"] += 1
        ts = (entry.get("ts") or "").strip()
        if ts and ts > cell["last_search_at"]:
            cell["last_search_at"] = ts

    for entry in planner_rows:
        lat, lng = _parse_area_coords(entry.get("city", ""), entry.get("state", ""))
        if lat is None or lng is None:
            continue
        cell = _territory_cell(cells, lat, lng)
        cell["planner_area_records"] += 1
        cell["planner_leads_total"] += _int_or_zero(entry.get("leads_found"))
        industries = entry.get("industries") or {}
        for industry, meta in industries.items():
            status = (meta.get("status") or "").strip().lower()
            if status in {"checked", "skipped", "exhausted", "due"}:
                cell["planner_checked_count"] += 1
                _bump(cell["planner_checked_by_industry"], industry.strip().lower())
            leads_found = _int_or_zero(meta.get("leads_found"))
            _bump(cell["planner_leads_by_industry"], industry.strip().lower(), leads_found)
            checked_at = (meta.get("last_checked_at") or "").strip()
            if checked_at and checked_at > cell["planner_last_checked_at"]:
                cell["planner_last_checked_at"] = checked_at

    cell_rows = sorted(
        cells.values(),
        key=lambda cell: (
            -int(cell.get("search_count", 0) or 0),
            -int(cell.get("lead_count", 0) or 0),
            cell.get("key", ""),
        ),
    )

    summary = {
        "cell_degrees": TERRITORY_CELL_DEGREES,
        "notes": "Coarse territory cells built from stored area-search centers and stored lead coordinates. Use them as neighborhood guidance, not exact boundaries.",
        "area_search_rows": sum(1 for e in search_history if str(e.get("state", "")).strip().lower() == "area"),
        "planner_area_rows": sum(1 for e in planner_rows if str(e.get("state", "")).strip().lower() == "area"),
        "prospects_with_coords": sum(1 for row in prospects if _float_or_none(row.get("lat")) is not None and _float_or_none(row.get("lng")) is not None),
        "cells_total": len(cell_rows),
        "cells_with_searches": sum(1 for cell in cell_rows if int(cell.get("search_count", 0) or 0) > 0),
        "cells_with_leads": sum(1 for cell in cell_rows if int(cell.get("lead_count", 0) or 0) > 0),
        "industries": sorted({
            industry
            for cell in cell_rows
            for industry in (
                list((cell.get("lead_industries") or {}).keys()) +
                list((cell.get("search_industries") or {}).keys()) +
                list((cell.get("planner_checked_by_industry") or {}).keys())
            )
            if industry
        }),
    }
    return jsonify({"cells": cell_rows, "summary": summary})

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
    # Pass 45: honour include_suppressed flag — default False
    include_suppressed = str(data.get("include_suppressed","")).strip().lower() in ("1","true")
    from datetime import datetime as _dt
    try:
        rows = discover_prospects(industry=industry,city=city,state=state,api_key=api_key,limit=limit,scrape_emails=True)
        ts = _dt.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        if len(rows) == 0:
            log.warning("Discover returned 0 rows: industry=%s city=%s state=%s",industry,city,state)
            _append_search_history({"ts":ts,"city":city,"state":state,"industry":industry,"limit":limit,"found":0,"status":"all_duplicates"})
            _city_planner.record_discovery(city,state,0,industry=industry)
            return jsonify({"ok":False,"all_duplicates":True,"error":"No new leads found — all results already in pipeline."}),200
        # Pass 45: filter suppressed rows before running the pipeline so they
        # are not re-drafted.  Rows whose identities are not yet in memory
        # (no suppression record) are allowed through unconditionally.
        if not include_suppressed:
            unsuppressed = [r for r in rows if not _lm.is_suppressed(r)]
            suppressed_skipped = len(rows) - len(unsuppressed)
            if suppressed_skipped:
                log.info("discover: skipped %d suppressed rows (industry=%s city=%s)",
                         suppressed_skipped, industry, city)
        else:
            unsuppressed = rows
            suppressed_skipped = 0
        if not unsuppressed:
            log.info("Discover: all %d rows suppressed, nothing to pipeline", len(rows))
            _append_search_history({"ts":ts,"city":city,"state":state,"industry":industry,"limit":limit,"found":0,"status":"all_suppressed"})
            _city_planner.record_discovery(city,state,0,industry=industry)
            return jsonify({"ok":False,"all_suppressed":True,"suppressed_skipped":suppressed_skipped,
                            "error":"All discovered leads are currently suppressed."}),200
        log.info("Discovered %d prospects (suppressed_skipped=%d): industry=%s city=%s state=%s",
                 len(unsuppressed),suppressed_skipped,industry,city,state)
        _append_search_history({"ts":ts,"city":city,"state":state,"industry":industry,"limit":limit,
                                 "found":len(unsuppressed),"suppressed_skipped":suppressed_skipped,"status":"ok"})
        _city_planner.record_discovery(city,state,len(unsuppressed),industry=industry)
        run_pipeline(input_csv=PROSPECTS_CSV,skip_scan=True)
        return jsonify({"ok":True,"found":len(unsuppressed),"suppressed_skipped":suppressed_skipped,
                        "total_queue":len(_read_pending())})
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
        # Pass 44: tag suppressed leads so the frontend can filter/dim them
        _include_supp = request.args.get("include_suppressed","").strip() in ("1","true")
        markers = []
        for r in new_prospect_rows:
            _supp = _lm.is_suppressed(r)
            if _supp and not _include_supp:
                continue   # suppress from default discovery results
            markers.append({
                "name":       r.get("business_name", ""),
                "city":       r.get("city", ""),
                "email":      r.get("to_email", ""),
                "channel":    r.get("contact_method", ""),
                "lat":        r.get("lat", ""),
                "lng":        r.get("lng", ""),
                "place_id":   r.get("place_id", ""),
                "suppressed": _supp,
            })

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

    # Pass 45: honour include_suppressed flag — default False (mirrors api_discover_area)
    include_suppressed = str(data.get("include_suppressed","")).strip().lower() in ("1","true")

    total_new      = 0
    iterations_run = 0
    stopped_reason = "max_iterations"
    all_markers    = []
    total_suppressed_skipped = 0
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
            # Pass 45: filter suppressed rows before accumulating markers
            for r in new_rows:
                _supp = _lm.is_suppressed(r)
                if _supp and not include_suppressed:
                    total_suppressed_skipped += 1
                    continue
                all_markers.append({
                    "name":       r.get("business_name", ""),
                    "city":       r.get("city", ""),
                    "email":      r.get("to_email", ""),
                    "channel":    r.get("contact_method", ""),
                    "lat":        r.get("lat", ""),
                    "lng":        r.get("lng", ""),
                    "place_id":   r.get("place_id", ""),
                    "suppressed": _supp,
                })

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

    log.info("discover_area_batch done: total_new=%d suppressed_skipped=%d iterations=%d reason=%s",
             total_new, total_suppressed_skipped, iterations_run, stopped_reason)

    return jsonify({
        "ok":                True,
        "total_new":         total_new,
        "suppressed_skipped": total_suppressed_skipped,
        "iterations_run":    iterations_run,
        "stopped_reason":    stopped_reason,
        "drafts_created":    drafts_created,
        "queue_total":       queue_after,
        "markers":           all_markers,
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
    # Pass 46: record contacted state in durable memory when result is "sent"
    if result == "sent":
        try:
            _lm.record_suppression(row, "contacted",
                                   note=f"contact logged via panel: channel={channel}")
        except Exception as _lm_exc:
            log.warning("lead_memory record failed on log_contact: %s", _lm_exc)
    # Pass 47: record replied event (non-state, narrative only)
    if result == "replied":
        try:
            _lm.record_event(row, _lm.EVT_REPLIED,
                             detail=f"channel={channel}")
        except Exception as _lm_exc:
            log.warning("lead_memory event failed (replied): %s", _lm_exc)
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
        return jsonify({"ok": False, "error": "Invalid index", "blocked_reason": "invalid_request"}), 400

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
    # Pass 48: record scheduled/unscheduled lifecycle event
    try:
        _evt = _lm.EVT_UNSCHEDULED if not send_after else _lm.EVT_SCHEDULED
        _det = send_after if send_after else ""
        _lm.record_event(rows[idx], _evt, detail=_det)
    except Exception as _e:
        log.warning("lead_memory event failed (%s): %s", action, _e)
    return jsonify({"ok": True, "send_after": send_after})

@app.route("/api/debug/scheduled_send_probe", methods=["POST"])
def api_debug_scheduled_send_probe():
    """
    Read-only helper for controlled scheduled-send verification.
    Returns scheduler-relevant state for one queue row without mutating data.
    """
    if os.getenv("COPPERLINE_ENABLE_DEBUG_ROUTES", "").strip().lower() not in {"1", "true", "yes"}:
        return jsonify({"ok": False, "error": "Not found"}), 404

    d = request.json or {}
    idx = d.get("index")
    business_name = (d.get("business_name") or "").strip()

    if idx is None or not isinstance(idx, int):
        return jsonify({"ok": False, "error": "index is required and must be an integer"}), 400
    if not business_name:
        return jsonify({"ok": False, "error": "business_name is required"}), 400

    rows = _read_pending()
    if not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400

    row = rows[idx]
    row_name = row.get("business_name", "").strip().lower()
    if row_name != business_name.lower():
        return jsonify({"ok": False, "error": "Row index/name mismatch — queue may have changed"}), 409

    send_after_raw = (row.get("send_after") or "").strip()
    now_local = _datetime.now()
    send_after_due = False
    send_after_parse_error = False
    send_after_dt = _parse_send_after_local(send_after_raw)
    if send_after_raw and send_after_dt is None:
        send_after_parse_error = True
    elif send_after_dt is not None:
        send_after_due = now_local >= send_after_dt

    payload = {
        "ok": True,
        "index": idx,
        "business_name": row.get("business_name", ""),
        "to_email": row.get("to_email", ""),
        "approved": (row.get("approved") or "").strip().lower() == "true",
        "sent_at": (row.get("sent_at") or "").strip(),
        "message_id": (row.get("message_id") or "").strip(),
        "send_after": send_after_raw,
        "send_after_due": send_after_due,
        "send_after_parse_error": send_after_parse_error,
        "is_send_eligible": _is_send_eligible(row),
        **get_send_readiness(row),
    }
    return jsonify(payload)


@app.route("/api/queue_row_truth", methods=["POST"])
def api_queue_row_truth():
    d = request.json or {}
    idx = d.get("index")
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
        return jsonify({"ok": False, "error": "Row index/name mismatch"}), 409

    readiness = get_send_readiness(row)
    return jsonify({
        "ok": True,
        "index": idx,
        "business_name": row.get("business_name", ""),
        "approved": (row.get("approved") or "").strip().lower() == "true",
        "to_email": row.get("to_email", ""),
        "send_after": row.get("send_after", ""),
        **readiness,
    })

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

_DELIVERY_CORE_OFFERS = {
    "presence_refresh": "Presence Refresh",
    "starter_website": "Starter Website",
    "lead_contact_setup": "Lead & Contact Setup",
}
_DELIVERY_BUNDLES = {
    "basic_cleanup": {"label": "Basic Cleanup", "core_offer": "presence_refresh"},
    "presence_website": {"label": "Presence + Website", "core_offer": "starter_website"},
    "full_starter_package": {"label": "Full Starter Package", "core_offer": "lead_contact_setup"},
}
_DELIVERY_SPECIALTY_MODULES = {
    "missed_call_recovery": "Missed Call Recovery",
    "follow_up_reminder_setup": "Follow-Up & Reminder Setup",
    "review_request_system": "Review Request System",
    "estimate_job_status_communication": "Estimate & Job Status Communication",
    "client_approval_estimate_portal": "Client Approval / Estimate Portal",
    "mobile_admin_workflow_helper": "Mobile Admin / owner workflow helper",
}
_DELIVERY_CORE_KEYS = set(_DELIVERY_CORE_OFFERS)
_DELIVERY_BUNDLE_KEYS = set(_DELIVERY_BUNDLES)
_DELIVERY_SPECIALTY_KEYS = set(_DELIVERY_SPECIALTY_MODULES)
_DELIVERY_BUNDLE_BY_CORE = {bundle["core_offer"]: key for key, bundle in _DELIVERY_BUNDLES.items()}
_LEGACY_PACKAGE_STACKS = {
    "missed_call_recovery": {
        "core_offer": "",
        "bundle_key": "",
        "selected_modules": ["missed_call_recovery"],
    },
    "lead_intake_routing": {
        "core_offer": "lead_contact_setup",
        "bundle_key": "",
        "selected_modules": [],
    },
    "followup_reactivation": {
        "core_offer": "",
        "bundle_key": "",
        "selected_modules": ["follow_up_reminder_setup"],
    },
    "review_request_system": {
        "core_offer": "",
        "bundle_key": "",
        "selected_modules": ["review_request_system"],
    },
    "estimate_job_status_communication": {
        "core_offer": "",
        "bundle_key": "",
        "selected_modules": ["estimate_job_status_communication"],
    },
}
_DELIVERY_STAGES = {
    "discovered",
    "drafted",
    "contacted",
    "replied",
    "call_booked",
    "proposal_ready",
    "won",
    "deployment_pending",
    "live",
}
_DELIVERY_READINESS_KEYS = (
    "activation_packet_ready",
    "assets_ready",
    "vendor_access_collected",
    "copy_approved",
    "routing_logic_defined",
    "qa_ready",
    "rollback_ready",
    "handoff_ready",
    "live",
)
_DELIVERY_VISIBILITY_KEYS = {"hidden", "internal", "ready"}
_DELIVERY_BUILD_STATUS_KEYS = {"planned", "hardening", "verification", "ready"}
_DELIVERY_OFFER_TYPE_KEYS = {"public", "internal"}
_DELIVERY_SUPPORT_POLICY_KEYS = {"", "optional_support", "managed_automation", "internal_only"}
_DELIVERY_OWNERSHIP_KEYS = {"", "client_owned", "drew_managed", "hybrid"}
_DELIVERY_KIT_STATUS_KEYS = {"", "hidden", "internal", "limited", "ready"}
_DEPLOY_SNAPSHOT_KEYS = (
    "business_name",
    "contact_name",
    "phone",
    "email",
    "category",
    "website",
    "google_presence",
    "facebook_presence",
    "notes",
)
_DEPLOY_DISCOVERY_KEYS = (
    "poor_or_missing_website",
    "weak_google_facebook_presence",
    "no_clear_contact_flow",
    "missed_calls",
    "weak_follow_up",
    "wants_more_reviews",
    "estimate_or_job_status_problem",
    "wants_ongoing_support",
)
_DEPLOY_QUOTE_MODES = {"live_quote", "formal_estimate"}
_DEPLOY_MONTHLY_SUPPORT_STATES = {True, False}
_DEPLOY_DEFAULT_NOTES = ""
_CONSULT_BUILDER_KEYS = (
    "freeform_notes",
    "business_type",
    "current_tools_accounts",
    "owner_preferences",
    "urgency",
    "transcript_summary",
    "do_not_recommend_notes",
)
_PROPOSAL_OPTION_OFFER_KEYS = _DELIVERY_CORE_KEYS | _DELIVERY_BUNDLE_KEYS | (_DELIVERY_SPECIALTY_KEYS - {"mobile_admin_workflow_helper"})
_ACCEPTED_OPTION_STATUSES = {"draft_only", "client_leaning", "client_accepted"}


def _coerce_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "__yes__"}


def _normalize_snapshot(value: dict | None) -> dict:
    base = {k: "" for k in _DEPLOY_SNAPSHOT_KEYS}
    base["google_presence"] = False
    base["facebook_presence"] = False
    if not isinstance(value, dict):
        return base
    for key in _DEPLOY_SNAPSHOT_KEYS:
        if key in {"google_presence", "facebook_presence"}:
            base[key] = _coerce_bool(value.get(key))
        elif isinstance(value.get(key), str):
            base[key] = value.get(key, "").strip()
    return base


def _normalize_discovery(value: dict | None) -> dict:
    base = {k: False for k in _DEPLOY_DISCOVERY_KEYS}
    if not isinstance(value, dict):
        return base
    for key in _DEPLOY_DISCOVERY_KEYS:
        if key in value:
            base[key] = _coerce_bool(value.get(key))
    return base


def _normalize_consult_builder(value: dict | None) -> dict:
    base = {k: "" for k in _CONSULT_BUILDER_KEYS}
    base["quick_wins"] = []
    if not isinstance(value, dict):
        return base
    for key in _CONSULT_BUILDER_KEYS:
        if isinstance(value.get(key), str):
            base[key] = value.get(key, "").strip()[:2000]
    quick_wins = value.get("quick_wins")
    if isinstance(quick_wins, list):
        clean_wins = []
        for item in quick_wins[:12]:
            if not isinstance(item, dict):
                continue
            offer_key = str(item.get("offer_key") or "").strip().lower()
            clean_wins.append({
                "id": str(item.get("id") or "")[:80],
                "category": str(item.get("category") or "other").strip()[:40],
                "what_noticed": str(item.get("what_noticed") or "").strip()[:1000],
                "why_matters": str(item.get("why_matters") or "").strip()[:1000],
                "quick_win": str(item.get("quick_win") or "").strip()[:1000],
                "priority": str(item.get("priority") or "soon").strip()[:20],
                "offer_key": offer_key if offer_key in (_DELIVERY_CORE_KEYS | _DELIVERY_SPECIALTY_KEYS) else "",
                "is_easy_fix": _coerce_bool(item.get("is_easy_fix")),
            })
        base["quick_wins"] = clean_wins
    return base


def _clean_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    seen = set()
    out = []
    for item in value:
        if not isinstance(item, str):
            continue
        clean = item.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean[:200])
    return out


def _clean_link_list(value) -> list[str]:
    return _clean_string_list(value)


def _normalize_proposal_options(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    clean_options = []
    for item in value[:6]:
        if not isinstance(item, dict):
            continue
        offers = []
        raw_offers = item.get("offer_keys")
        if raw_offers is None:
            raw_offers = item.get("included_offers")
        for offer_key in raw_offers or []:
            if not isinstance(offer_key, str):
                continue
            key = offer_key.strip().lower()
            if key in _PROPOSAL_OPTION_OFFER_KEYS and key not in offers:
                offers.append(key)
        clean_options.append({
            "id": str(item.get("id") or "")[:80],
            "label": str(item.get("label") or "")[:120],
            "offer_keys": offers[:8],
            "price_note": str(item.get("price_note") or "")[:120],
            "scope_note": str(item.get("scope_note") or "")[:1000],
            "recommended": _coerce_bool(item.get("recommended", item.get("is_recommended"))),
            "assumptions": str(item.get("assumptions", item.get("notes") or "") or "")[:1000],
        })
    return clean_options


def _deploy_task_templates(profile: dict | None) -> list[str]:
    profile = profile if isinstance(profile, dict) else {}
    tasks: list[str] = []
    core_offer = (profile.get("core_offer") or "").strip().lower()
    bundle_key = (profile.get("bundle_key") or "").strip().lower()
    modules = _normalize_selected_modules(profile.get("selected_modules"))
    truth = compute_stack_truth(core_offer, bundle_key, modules)
    if core_offer == "presence_refresh":
        tasks += [
            "Refresh Google Business Profile",
            "Refresh Facebook / local presence",
            "Tighten photos, hours, and about copy",
        ]
    elif core_offer == "starter_website":
        tasks += [
            "Draft the one-page site",
            "Collect photos and service list",
            "Connect the contact flow",
        ]
    elif core_offer == "lead_contact_setup":
        tasks += [
            "Map the intake flow",
            "Set follow-up reminders",
            "Route new leads to the owner",
        ]

    if bundle_key == "basic_cleanup":
        tasks.append("Trim the presence cleanup to the fast wins")
    elif bundle_key == "presence_website":
        tasks += ["Tie the site back to the business profiles"]
    elif bundle_key == "full_starter_package":
        tasks += ["Confirm the full starter stack is ready for handoff"]

    module_tasks = {
        "missed_call_recovery": "Set missed-call response and text-back",
        "follow_up_reminder_setup": "Set follow-up timing and reminders",
        "review_request_system": "Set review request trigger and copy",
        "estimate_job_status_communication": "Set estimate / job status updates",
        "client_approval_estimate_portal": "Set the approval path and portal",
        "mobile_admin_workflow_helper": "Confirm the mobile admin workflow",
    }
    for module in modules:
        task = module_tasks.get(module)
        if task:
            tasks.append(task)
    for item in truth.get("required_artifacts", []):
        tasks.append(f"Collect: {item}")
    for item in truth.get("access_requirements", []):
        tasks.append(f"Confirm access: {item}")
    if _coerce_bool(profile.get("monthly_support")):
        tasks.append("Confirm monthly support scope")
    return list(dict.fromkeys(tasks))


def _apply_stack_truth_defaults(merged: dict) -> dict:
    truth = compute_stack_truth(
        (merged.get("core_offer") or "").strip().lower(),
        (merged.get("bundle_key") or "").strip().lower(),
        _normalize_selected_modules(merged.get("selected_modules")),
    )
    if not truth.get("kit_key"):
        return {}
    return {
        "prelaunch_mode": PRELAUNCH_MODE,
        "offer_type": truth.get("offer_type", "public"),
        "build_status": truth.get("build_status", "planned"),
        "launch_eligible": bool(truth.get("launch_eligible")),
        "visibility_state": truth.get("visibility_state", "hidden"),
        "target_visibility_state": truth.get("target_visibility_state", "hidden"),
        "kit_key": truth.get("kit_key", ""),
        "kit_version": truth.get("kit_version", ""),
        "kit_status": truth.get("kit_status", ""),
        "current_truth_notes": truth.get("current_truth_notes", []),
        "target_truth_notes": truth.get("target_truth_notes", []),
        "required_artifacts": truth.get("required_artifacts", []),
        "access_requirements": truth.get("access_requirements", []),
        "qa_checks": truth.get("qa_checks", []),
        "rollback_plan": truth.get("rollback_plan", []),
        "definition_of_done": truth.get("definition_of_done", []),
        "missing_artifacts": truth.get("missing_artifacts", []),
        "missing_qa": truth.get("missing_qa", []),
        "missing_closeout": truth.get("missing_closeout", []),
        "missing_rollback": truth.get("missing_rollback", []),
        "next_hardening_steps": truth.get("next_hardening_steps", []),
        "activation_packet_sections": truth.get("activation_packet_sections", []),
        "ownership_mode": truth.get("ownership_mode", ""),
        "support_policy_key": truth.get("support_policy_key", ""),
        "support_summary": truth.get("support_summary", ""),
    }


def _delivery_profile_default(row: dict | None = None) -> dict:
    is_replied = ((row or {}).get("replied") or "").strip().lower() == "true"
    return {
        "snapshot": {k: (False if k in {"google_presence", "facebook_presence"} else "") for k in _DEPLOY_SNAPSHOT_KEYS},
        "discovery": {k: False for k in _DEPLOY_DISCOVERY_KEYS},
        "consult_builder": {**{k: "" for k in _CONSULT_BUILDER_KEYS}, "quick_wins": []},
        "draft_recommendation": {},
        "proposal_options": [],
        "accepted_option_id": "",
        "accepted_option_status": "draft_only",
        "accepted_option_date": "",
        "accepted_option_label": "",
        "accepted_option_note": "",
        "accepted_scope_note": "",
        "accepted_assumptions": "",
        "core_offer": "",
        "bundle_key": "",
        "selected_modules": [],
        "price": "",
        "pricing_mode": "live_quote",
        "monthly_support": False,
        "monthly_fee": "",
        "agreement_status": "",
        "invoice_status": "",
        "deposit_status": "",
        "offer_notes": "",
        "activation_tasks": [],
        "prelaunch_mode": PRELAUNCH_MODE,
        "offer_type": "public",
        "build_status": "planned",
        "launch_eligible": False,
        "visibility_state": "hidden",
        "target_visibility_state": "hidden",
        "kit_key": "",
        "kit_version": "",
        "kit_status": "",
        "current_truth_notes": [],
        "target_truth_notes": [],
        "required_artifacts": [],
        "artifact_links": [],
        "access_requirements": [],
        "credential_status": "",
        "qa_checks": [],
        "rollback_plan": [],
        "definition_of_done": [],
        "missing_artifacts": [],
        "missing_qa": [],
        "missing_closeout": [],
        "missing_rollback": [],
        "next_hardening_steps": [],
        "activation_packet_sections": [],
        "handoff_status": "",
        "closeout_status": "",
        "ownership_mode": "",
        "support_policy_key": "",
        "support_summary": "",
        "change_order_status": "in_scope",
        "revision_round": 0,
        "revision_status": "",
        "change_order_needed": False,
        "change_order_notes": "",
        "blockers": [],
        "next_step": "",
        "activation_packet_status": "draft",
        "stage": "replied" if is_replied else "discovered",
        "readiness": {k: False for k in _DELIVERY_READINESS_KEYS},
        "updated_at": "",
    }


def _legacy_stack_for_package(package_key: str) -> dict:
    return dict(_LEGACY_PACKAGE_STACKS.get(package_key or "", {}))


def _normalize_selected_modules(value) -> list[str]:
    if not isinstance(value, list):
        return []
    seen = set()
    modules = []
    for item in value:
        if not isinstance(item, str):
            continue
        key = item.strip().lower()
        if key in _DELIVERY_SPECIALTY_KEYS and key not in seen:
            seen.add(key)
            modules.append(key)
    return modules


def _finalize_delivery_stack_patch(clean_patch: dict, current_profile: dict) -> tuple[dict, str | None]:
    merged = dict(current_profile or {})
    merged.update(clean_patch)
    bundle_key = (merged.get("bundle_key") or "").strip().lower()
    core_offer = (merged.get("core_offer") or "").strip().lower()
    if bundle_key:
        bundle_core = _DELIVERY_BUNDLES[bundle_key]["core_offer"]
        if core_offer and core_offer != bundle_core:
            return clean_patch, "bundle_key does not match core_offer"
        clean_patch["core_offer"] = core_offer or bundle_core
    return clean_patch, None


def _finalize_activation_patch(clean_patch: dict, current_profile: dict) -> dict:
    merged = dict(current_profile or {})
    merged.update(clean_patch)
    if "snapshot" in merged and isinstance(merged["snapshot"], dict):
        clean_patch["snapshot"] = _normalize_snapshot(merged["snapshot"])
    if "discovery" in merged and isinstance(merged["discovery"], dict):
        clean_patch["discovery"] = _normalize_discovery(merged["discovery"])
    if "consult_builder" in merged and isinstance(merged["consult_builder"], dict):
        clean_patch["consult_builder"] = _normalize_consult_builder(merged["consult_builder"])
    if "draft_recommendation" in merged and isinstance(merged["draft_recommendation"], dict):
        clean_patch["draft_recommendation"] = dict(merged["draft_recommendation"])
    if "proposal_options" in merged:
        clean_patch["proposal_options"] = _normalize_proposal_options(merged.get("proposal_options"))
    if "accepted_option_id" in merged:
        clean_patch["accepted_option_id"] = str(merged.get("accepted_option_id") or "").strip()[:80]
    if "accepted_option_status" in merged:
        status = str(merged.get("accepted_option_status") or "").strip().lower()
        clean_patch["accepted_option_status"] = status if status in _ACCEPTED_OPTION_STATUSES else "draft_only"
    if "accepted_option_date" in merged:
        clean_patch["accepted_option_date"] = str(merged.get("accepted_option_date") or "").strip()[:40]
    if "accepted_option_label" in merged:
        clean_patch["accepted_option_label"] = str(merged.get("accepted_option_label") or "").strip()[:120]
    if "accepted_option_note" in merged:
        clean_patch["accepted_option_note"] = str(merged.get("accepted_option_note") or "").strip()[:1000]
    if "accepted_scope_note" in merged:
        clean_patch["accepted_scope_note"] = str(merged.get("accepted_scope_note") or "").strip()[:1000]
    if "accepted_assumptions" in merged:
        clean_patch["accepted_assumptions"] = str(merged.get("accepted_assumptions") or "").strip()[:1000]

    pricing_mode = (merged.get("pricing_mode") or "").strip().lower()
    if pricing_mode in _DEPLOY_QUOTE_MODES:
        clean_patch["pricing_mode"] = pricing_mode
    elif "pricing_mode" in clean_patch:
        clean_patch["pricing_mode"] = "live_quote"

    if "monthly_support" in merged:
        clean_patch["monthly_support"] = _coerce_bool(merged.get("monthly_support"))
    if "monthly_fee" in merged:
        monthly_fee = merged.get("monthly_fee")
        clean_patch["monthly_fee"] = str(monthly_fee).strip() if monthly_fee is not None else ""
    if "deposit_status" in merged:
        clean_patch["deposit_status"] = (merged.get("deposit_status") or "").strip()
    if "artifact_links" in merged:
        clean_patch["artifact_links"] = _clean_link_list(merged.get("artifact_links"))
    if "blockers" in merged:
        clean_patch["blockers"] = _clean_string_list(merged.get("blockers"))
    if "next_step" in merged:
        clean_patch["next_step"] = (merged.get("next_step") or "").strip()[:200]
    if "credential_status" in merged:
        clean_patch["credential_status"] = (merged.get("credential_status") or "").strip()[:80]
    if "handoff_status" in merged:
        clean_patch["handoff_status"] = (merged.get("handoff_status") or "").strip()[:80]
    if "closeout_status" in merged:
        clean_patch["closeout_status"] = (merged.get("closeout_status") or "").strip()[:80]
    if "activation_packet_status" in merged:
        clean_patch["activation_packet_status"] = (merged.get("activation_packet_status") or "").strip()[:80]
    if "revision_status" in merged:
        clean_patch["revision_status"] = (merged.get("revision_status") or "").strip()[:80]
    if "change_order_status" in merged:
        clean_patch["change_order_status"] = (merged.get("change_order_status") or "").strip()[:80]
    if "change_order_notes" in merged:
        clean_patch["change_order_notes"] = (merged.get("change_order_notes") or "")[:1000]
    if "change_order_needed" in merged:
        clean_patch["change_order_needed"] = _coerce_bool(merged.get("change_order_needed"))
    if "revision_round" in merged:
        try:
            clean_patch["revision_round"] = max(0, int(merged.get("revision_round") or 0))
        except (TypeError, ValueError):
            clean_patch["revision_round"] = 0
    if "visibility_state" in merged:
        visibility_state = (merged.get("visibility_state") or "").strip().lower()
        clean_patch["visibility_state"] = visibility_state if visibility_state in _DELIVERY_VISIBILITY_KEYS else "hidden"
    if "offer_type" in merged:
        offer_type = (merged.get("offer_type") or "").strip().lower()
        clean_patch["offer_type"] = offer_type if offer_type in _DELIVERY_OFFER_TYPE_KEYS else "public"
    if "build_status" in merged:
        build_status = (merged.get("build_status") or "").strip().lower()
        clean_patch["build_status"] = build_status if build_status in _DELIVERY_BUILD_STATUS_KEYS else "planned"
    if "launch_eligible" in merged:
        clean_patch["launch_eligible"] = _coerce_bool(merged.get("launch_eligible"))
    if "ownership_mode" in merged:
        ownership_mode = (merged.get("ownership_mode") or "").strip().lower()
        clean_patch["ownership_mode"] = ownership_mode if ownership_mode in _DELIVERY_OWNERSHIP_KEYS else ""
    if "support_policy_key" in merged:
        support_policy_key = (merged.get("support_policy_key") or "").strip().lower()
        clean_patch["support_policy_key"] = support_policy_key if support_policy_key in _DELIVERY_SUPPORT_POLICY_KEYS else ""
    if "kit_status" in merged:
        kit_status = (merged.get("kit_status") or "").strip().lower()
        clean_patch["kit_status"] = kit_status if kit_status in _DELIVERY_KIT_STATUS_KEYS else ""

    clean_patch.update(_apply_stack_truth_defaults(merged))

    clean_patch["activation_tasks"] = _deploy_task_templates(merged)
    return clean_patch


def _normalize_delivery_profile(raw_profile: dict | None, row: dict | None = None) -> dict:
    base = _delivery_profile_default(row)
    if not isinstance(raw_profile, dict):
        return base

    package_key = (raw_profile.get("package_key") or "").strip().lower()
    legacy_stack = _legacy_stack_for_package(package_key)

    core_offer = (raw_profile.get("core_offer") or "").strip().lower()
    if core_offer in _DELIVERY_CORE_KEYS:
        base["core_offer"] = core_offer

    bundle_key = (raw_profile.get("bundle_key") or "").strip().lower()
    if bundle_key in _DELIVERY_BUNDLE_KEYS:
        base["bundle_key"] = bundle_key

    if not base["core_offer"] and base["bundle_key"]:
        base["core_offer"] = _DELIVERY_BUNDLES[base["bundle_key"]]["core_offer"]

    if not base["core_offer"] and legacy_stack.get("core_offer"):
        base["core_offer"] = legacy_stack["core_offer"]
    if not base["bundle_key"] and legacy_stack.get("bundle_key"):
        base["bundle_key"] = legacy_stack["bundle_key"]

    selected_modules = _normalize_selected_modules(raw_profile.get("selected_modules"))
    if not selected_modules and legacy_stack.get("selected_modules"):
        selected_modules = _normalize_selected_modules(legacy_stack["selected_modules"])
    base["selected_modules"] = selected_modules

    snapshot = raw_profile.get("snapshot")
    if isinstance(snapshot, dict):
        base["snapshot"] = _normalize_snapshot(snapshot)

    discovery = raw_profile.get("discovery")
    if isinstance(discovery, dict):
        base["discovery"] = _normalize_discovery(discovery)
    consult_builder = raw_profile.get("consult_builder")
    if isinstance(consult_builder, dict):
        base["consult_builder"] = _normalize_consult_builder(consult_builder)
    draft_recommendation = raw_profile.get("draft_recommendation")
    if isinstance(draft_recommendation, dict):
        base["draft_recommendation"] = dict(draft_recommendation)
    base["proposal_options"] = _normalize_proposal_options(raw_profile.get("proposal_options"))
    accepted_option_id = raw_profile.get("accepted_option_id")
    if isinstance(accepted_option_id, str):
        base["accepted_option_id"] = accepted_option_id.strip()
    accepted_option_status = (raw_profile.get("accepted_option_status") or "").strip().lower()
    if accepted_option_status in _ACCEPTED_OPTION_STATUSES:
        base["accepted_option_status"] = accepted_option_status
    accepted_option_date = raw_profile.get("accepted_option_date")
    if isinstance(accepted_option_date, str):
        base["accepted_option_date"] = accepted_option_date.strip()
    accepted_option_label = raw_profile.get("accepted_option_label")
    if isinstance(accepted_option_label, str):
        base["accepted_option_label"] = accepted_option_label.strip()
    accepted_option_note = raw_profile.get("accepted_option_note")
    if isinstance(accepted_option_note, str):
        base["accepted_option_note"] = accepted_option_note.strip()
    accepted_scope_note = raw_profile.get("accepted_scope_note")
    if isinstance(accepted_scope_note, str):
        base["accepted_scope_note"] = accepted_scope_note.strip()
    accepted_assumptions = raw_profile.get("accepted_assumptions")
    if isinstance(accepted_assumptions, str):
        base["accepted_assumptions"] = accepted_assumptions.strip()

    price = raw_profile.get("price")
    if isinstance(price, (int, float)):
        base["price"] = str(price)
    elif isinstance(price, str):
        base["price"] = price.strip()

    pricing_mode = (raw_profile.get("pricing_mode") or "").strip().lower()
    if pricing_mode in _DEPLOY_QUOTE_MODES:
        base["pricing_mode"] = pricing_mode

    monthly_support = raw_profile.get("monthly_support")
    if isinstance(monthly_support, bool):
        base["monthly_support"] = monthly_support
    elif monthly_support is not None:
        base["monthly_support"] = _coerce_bool(monthly_support)

    monthly_fee = raw_profile.get("monthly_fee")
    if isinstance(monthly_fee, (int, float)):
        base["monthly_fee"] = str(monthly_fee)
    elif isinstance(monthly_fee, str):
        base["monthly_fee"] = monthly_fee.strip()

    agreement_status = raw_profile.get("agreement_status")
    if isinstance(agreement_status, str):
        base["agreement_status"] = agreement_status.strip()

    invoice_status = raw_profile.get("invoice_status")
    if isinstance(invoice_status, str):
        base["invoice_status"] = invoice_status.strip()

    deposit_status = raw_profile.get("deposit_status")
    if isinstance(deposit_status, str):
        base["deposit_status"] = deposit_status.strip()

    offer_notes = raw_profile.get("offer_notes")
    if isinstance(offer_notes, str):
        base["offer_notes"] = offer_notes

    activation_tasks = raw_profile.get("activation_tasks")
    if isinstance(activation_tasks, list):
        base["activation_tasks"] = [task for task in activation_tasks if isinstance(task, str) and task.strip()]

    visibility_state = (raw_profile.get("visibility_state") or "").strip().lower()
    if visibility_state in _DELIVERY_VISIBILITY_KEYS:
        base["visibility_state"] = visibility_state
    offer_type = (raw_profile.get("offer_type") or "").strip().lower()
    if offer_type in _DELIVERY_OFFER_TYPE_KEYS:
        base["offer_type"] = offer_type
    build_status = (raw_profile.get("build_status") or "").strip().lower()
    if build_status in _DELIVERY_BUILD_STATUS_KEYS:
        base["build_status"] = build_status
    if "launch_eligible" in raw_profile:
        base["launch_eligible"] = _coerce_bool(raw_profile.get("launch_eligible"))
    target_visibility_state = (raw_profile.get("target_visibility_state") or "").strip().lower()
    if target_visibility_state in _DELIVERY_VISIBILITY_KEYS:
        base["target_visibility_state"] = target_visibility_state
    kit_key = raw_profile.get("kit_key")
    if isinstance(kit_key, str):
        base["kit_key"] = kit_key.strip()
    kit_version = raw_profile.get("kit_version")
    if isinstance(kit_version, str):
        base["kit_version"] = kit_version.strip()
    kit_status = (raw_profile.get("kit_status") or "").strip().lower()
    if kit_status in _DELIVERY_KIT_STATUS_KEYS:
        base["kit_status"] = kit_status
    artifact_links = raw_profile.get("artifact_links")
    if isinstance(artifact_links, list):
        base["artifact_links"] = _clean_link_list(artifact_links)
    required_artifacts = raw_profile.get("required_artifacts")
    if isinstance(required_artifacts, list):
        base["required_artifacts"] = _clean_string_list(required_artifacts)
    access_requirements = raw_profile.get("access_requirements")
    if isinstance(access_requirements, list):
        base["access_requirements"] = _clean_string_list(access_requirements)
    credential_status = raw_profile.get("credential_status")
    if isinstance(credential_status, str):
        base["credential_status"] = credential_status.strip()
    qa_checks = raw_profile.get("qa_checks")
    if isinstance(qa_checks, list):
        base["qa_checks"] = _clean_string_list(qa_checks)
    rollback_plan = raw_profile.get("rollback_plan")
    if isinstance(rollback_plan, list):
        base["rollback_plan"] = _clean_string_list(rollback_plan)
    definition_of_done = raw_profile.get("definition_of_done")
    if isinstance(definition_of_done, list):
        base["definition_of_done"] = _clean_string_list(definition_of_done)
    activation_packet_sections = raw_profile.get("activation_packet_sections")
    if isinstance(activation_packet_sections, list):
        base["activation_packet_sections"] = _clean_string_list(activation_packet_sections)
    handoff_status = raw_profile.get("handoff_status")
    if isinstance(handoff_status, str):
        base["handoff_status"] = handoff_status.strip()
    closeout_status = raw_profile.get("closeout_status")
    if isinstance(closeout_status, str):
        base["closeout_status"] = closeout_status.strip()
    ownership_mode = (raw_profile.get("ownership_mode") or "").strip().lower()
    if ownership_mode in _DELIVERY_OWNERSHIP_KEYS:
        base["ownership_mode"] = ownership_mode
    support_policy_key = (raw_profile.get("support_policy_key") or "").strip().lower()
    if support_policy_key in _DELIVERY_SUPPORT_POLICY_KEYS:
        base["support_policy_key"] = support_policy_key
    support_summary = raw_profile.get("support_summary")
    if isinstance(support_summary, str):
        base["support_summary"] = support_summary
    current_truth_notes = raw_profile.get("current_truth_notes")
    if isinstance(current_truth_notes, list):
        base["current_truth_notes"] = _clean_string_list(current_truth_notes)
    target_truth_notes = raw_profile.get("target_truth_notes")
    if isinstance(target_truth_notes, list):
        base["target_truth_notes"] = _clean_string_list(target_truth_notes)
    missing_artifacts = raw_profile.get("missing_artifacts")
    if isinstance(missing_artifacts, list):
        base["missing_artifacts"] = _clean_string_list(missing_artifacts)
    missing_qa = raw_profile.get("missing_qa")
    if isinstance(missing_qa, list):
        base["missing_qa"] = _clean_string_list(missing_qa)
    missing_closeout = raw_profile.get("missing_closeout")
    if isinstance(missing_closeout, list):
        base["missing_closeout"] = _clean_string_list(missing_closeout)
    missing_rollback = raw_profile.get("missing_rollback")
    if isinstance(missing_rollback, list):
        base["missing_rollback"] = _clean_string_list(missing_rollback)
    next_hardening_steps = raw_profile.get("next_hardening_steps")
    if isinstance(next_hardening_steps, list):
        base["next_hardening_steps"] = _clean_string_list(next_hardening_steps)
    change_order_status = raw_profile.get("change_order_status")
    if isinstance(change_order_status, str):
        base["change_order_status"] = change_order_status.strip()
    revision_status = raw_profile.get("revision_status")
    if isinstance(revision_status, str):
        base["revision_status"] = revision_status.strip()
    try:
        base["revision_round"] = max(0, int(raw_profile.get("revision_round") or 0))
    except (TypeError, ValueError):
        pass
    base["change_order_needed"] = _coerce_bool(raw_profile.get("change_order_needed"))
    change_order_notes = raw_profile.get("change_order_notes")
    if isinstance(change_order_notes, str):
        base["change_order_notes"] = change_order_notes
    blockers = raw_profile.get("blockers")
    if isinstance(blockers, list):
        base["blockers"] = _clean_string_list(blockers)
    next_step = raw_profile.get("next_step")
    if isinstance(next_step, str):
        base["next_step"] = next_step.strip()
    activation_packet_status = raw_profile.get("activation_packet_status")
    if isinstance(activation_packet_status, str):
        base["activation_packet_status"] = activation_packet_status.strip()

    stage = (raw_profile.get("stage") or "").strip().lower()
    if stage in _DELIVERY_STAGES:
        base["stage"] = stage

    readiness = raw_profile.get("readiness")
    if isinstance(readiness, dict):
        for key in _DELIVERY_READINESS_KEYS:
            if key in readiness:
                base["readiness"][key] = bool(readiness.get(key))

    updated_at = raw_profile.get("updated_at")
    if isinstance(updated_at, str):
        base["updated_at"] = updated_at

    base.update(_apply_stack_truth_defaults(base))

    return base


@app.route("/api/delivery_catalog")
def api_delivery_catalog():
    catalog = get_catalog_payload()
    offer_evidence = _build_offer_evidence_summary()
    catalog["offer_evidence_summary"] = offer_evidence["offers_by_key"]
    catalog["offer_evidence_overview"] = offer_evidence["overview"]
    for item in catalog.get("hardening_items", []):
        item["evidence_summary"] = offer_evidence["offers_by_key"].get(item.get("key"), {})
    return jsonify({"ok": True, "catalog": catalog})


DELIVERY_EXEC_LOG = BASE_DIR / "data" / "delivery_execution_log.json"

def _load_exec_log():
    if DELIVERY_EXEC_LOG.exists():
        try:
            return json.loads(DELIVERY_EXEC_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_exec_log(data):
    DELIVERY_EXEC_LOG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


_DELIVERY_REVIEW_STATUSES = {"not_ready", "ready_for_manual_review", "reviewed_insufficient", "reviewed_complete"}


def _delivery_review_label(status: str) -> str:
    return {
        "ready_for_manual_review": "Ready for manual review",
        "reviewed_insufficient": "Reviewed, evidence insufficient",
        "reviewed_complete": "Reviewed, evidence complete",
    }.get(status, "Not ready for review")


def _delivery_run_sort_stamp(state: dict) -> str:
    if not isinstance(state, dict):
        return ""
    for key in ("updated_at", "closeout_date", "delivery_date", "started_at"):
        value = str(state.get(key) or "").strip()
        if value:
            return value
    return ""


def _empty_offer_evidence_summary(offer_key: str, offer: dict | None = None) -> dict:
    offer = offer or {}
    return {
        "offer_key": offer_key,
        "offer_label": offer.get("label") or offer_key,
        "offer_type": offer.get("offer_type") or "",
        "build_status": offer.get("build_status") or "",
        "launch_eligible": bool(offer.get("launch_eligible")),
        "total_runs": 0,
        "closeout_captured_count": 0,
        "ready_for_manual_review_count": 0,
        "reviewed_complete_count": 0,
        "reviewed_insufficient_count": 0,
        "candidate_for_review_count": 0,
        "proof_present_count": 0,
        "proof_missing_count": 0,
        "artifact_refs_count": 0,
        "owner_acknowledged_count": 0,
        "open_blocker_count": 0,
        "open_blocker_present": False,
        "last_run_key": "",
        "last_run_date": "",
        "last_client_business_name": "",
        "last_reviewed_run_key": "",
        "last_reviewed_run_date": "",
        "last_reviewed_status": "",
        "last_reviewed_business_name": "",
        "last_evidence_run_key": "",
        "last_evidence_run_date": "",
        "last_evidence_business_name": "",
        "proof_coverage_summary": "No delivery runs yet",
        "evidence_presence": "No run evidence yet",
        "promotion_readiness": {
            "status": "no_reviewed_runs",
            "label": "No reviewed runs yet",
            "note": "No reviewed delivery evidence exists for this offer yet.",
        },
        "recent_runs": [],
    }


def _build_delivery_review_row(run_key: str, state: dict, records: dict) -> dict | None:
    if not isinstance(state, dict):
        return None
    lead_key = str(state.get("lead_key") or "").strip()
    offer_key = str(state.get("offer_key") or "").strip()
    if not offer_key and "|" in run_key:
        parts = run_key.split("|", 1)
        lead_key = lead_key or ("" if parts[0] == "practice" else parts[0])
        offer_key = parts[1]
    if lead_key == "practice":
        lead_key = ""
    offer = DELIVERY_CATALOG.get(offer_key, {})
    record = records.get(lead_key, {}) if lead_key else {}
    checks = state.get("checks") if isinstance(state.get("checks"), dict) else {}
    blockers = (state.get("blockers") or "").strip()
    before_proof = (state.get("before_proof_link") or state.get("proof_links") or "").strip()
    after_proof = (state.get("after_proof_link") or "").strip()
    artifact_refs = (state.get("artifact_refs") or "").strip()
    proof_present = bool(before_proof and after_proof)
    review_status = (state.get("verification_review_status") or "not_ready").strip()
    if review_status not in _DELIVERY_REVIEW_STATUSES:
        review_status = "not_ready"
    closeout_status = state.get("closeout_status") or "open"
    candidate = closeout_status == "captured" and proof_present and not blockers
    return {
        "run_key": run_key,
        "lead_key": lead_key,
        "offer_key": offer_key,
        "business_name": state.get("business_name") or record.get("business_name", "") or "Practice run",
        "offer_label": offer.get("label") or offer_key,
        "closeout_status": closeout_status,
        "owner_ack_status": state.get("owner_ack_status") or "pending",
        "verification_review_status": review_status,
        "verification_review_label": _delivery_review_label(review_status),
        "proof_present": proof_present,
        "before_proof_present": bool(before_proof),
        "after_proof_present": bool(after_proof),
        "artifact_refs_present": bool(artifact_refs),
        "blockers_present": bool(blockers),
        "blockers": blockers,
        "candidate_for_review": candidate,
        "checks_done": sum(1 for v in checks.values() if v is True),
        "checks_tracked": len(checks),
        "updated_at": state.get("updated_at", ""),
        "closeout_date": state.get("closeout_date", ""),
        "delivery_date": state.get("delivery_date", ""),
        "sort_stamp": _delivery_run_sort_stamp(state),
        "verification_review_notes": (state.get("verification_review_notes") or "").strip(),
    }


def _offer_promotion_readiness(summary: dict) -> dict:
    reviewed_complete = int(summary.get("reviewed_complete_count") or 0)
    reviewed_insufficient = int(summary.get("reviewed_insufficient_count") or 0)
    ready_for_review = int(summary.get("ready_for_manual_review_count") or 0)
    proof_present = int(summary.get("proof_present_count") or 0)
    closeout_captured = int(summary.get("closeout_captured_count") or 0)
    blocker_count = int(summary.get("open_blocker_count") or 0)
    last_reviewed_status = summary.get("last_reviewed_status") or ""

    if reviewed_complete > 0 and proof_present > 0 and closeout_captured > 0 and blocker_count == 0:
        return {
            "status": "ready_for_human_verification",
            "label": "Ready for human verification decision",
            "note": "A reviewed-complete run exists with proof, closeout, and no open blockers. Promotion still requires an operator decision.",
        }
    if reviewed_complete > 0 or reviewed_insufficient > 0:
        if last_reviewed_status == "reviewed_insufficient" or proof_present == 0 or closeout_captured == 0:
            return {
                "status": "reviewed_proof_incomplete",
                "label": "Reviewed evidence exists, but proof incomplete",
                "note": "At least one run was reviewed, but the available evidence still shows proof, closeout, or blocker gaps.",
            }
        return {
            "status": "criteria_partially_supported",
            "label": "Reviewed evidence exists, criteria partially supported",
            "note": "Reviewed evidence exists, but the catalog promotion criteria still need human verification against the actual run proof.",
        }
    if ready_for_review > 0:
        return {
            "status": "awaiting_manual_review",
            "label": "Evidence captured, waiting for manual review",
            "note": "Run evidence has been marked ready for manual review, but no reviewed decision exists yet.",
        }
    return {
        "status": "no_reviewed_runs",
        "label": "No reviewed runs yet",
        "note": "No reviewed delivery evidence exists for this offer yet.",
    }


def _build_offer_evidence_summary(log: dict | None = None, records: dict | None = None) -> dict:
    log = log if isinstance(log, dict) else _load_exec_log()
    records = records if isinstance(records, dict) else _lm.get_all_records()
    offers_by_key = {
        key: _empty_offer_evidence_summary(key, offer)
        for key, offer in DELIVERY_CATALOG.items()
    }
    for run_key, state in log.items():
        row = _build_delivery_review_row(run_key, state, records)
        if not row:
            continue
        offer_key = row.get("offer_key") or ""
        if offer_key not in offers_by_key:
            offers_by_key[offer_key] = _empty_offer_evidence_summary(offer_key, DELIVERY_CATALOG.get(offer_key))
        summary = offers_by_key[offer_key]
        summary["total_runs"] += 1
        if row["closeout_status"] == "captured":
            summary["closeout_captured_count"] += 1
        if row["verification_review_status"] == "ready_for_manual_review":
            summary["ready_for_manual_review_count"] += 1
        if row["verification_review_status"] == "reviewed_complete":
            summary["reviewed_complete_count"] += 1
        if row["verification_review_status"] == "reviewed_insufficient":
            summary["reviewed_insufficient_count"] += 1
        if row["candidate_for_review"]:
            summary["candidate_for_review_count"] += 1
        if row["proof_present"]:
            summary["proof_present_count"] += 1
        if row["artifact_refs_present"]:
            summary["artifact_refs_count"] += 1
        if row["owner_ack_status"] == "acknowledged":
            summary["owner_acknowledged_count"] += 1
        if row["blockers_present"]:
            summary["open_blocker_count"] += 1
            summary["open_blocker_present"] = True

        light_run = {
            "run_key": row["run_key"],
            "lead_key": row["lead_key"],
            "offer_key": row["offer_key"],
            "business_name": row["business_name"],
            "verification_review_status": row["verification_review_status"],
            "verification_review_label": row["verification_review_label"],
            "closeout_status": row["closeout_status"],
            "proof_present": row["proof_present"],
            "artifact_refs_present": row["artifact_refs_present"],
            "blockers_present": row["blockers_present"],
            "updated_at": row["updated_at"],
            "closeout_date": row["closeout_date"],
            "delivery_date": row["delivery_date"],
            "sort_stamp": row["sort_stamp"],
        }
        summary["recent_runs"].append(light_run)

        if row["sort_stamp"] >= (summary["last_run_date"] or ""):
            summary["last_run_key"] = row["run_key"]
            summary["last_run_date"] = row["sort_stamp"]
            summary["last_client_business_name"] = row["business_name"]

        if row["proof_present"] or row["artifact_refs_present"] or row["closeout_status"] == "captured":
            if row["sort_stamp"] >= (summary["last_evidence_run_date"] or ""):
                summary["last_evidence_run_key"] = row["run_key"]
                summary["last_evidence_run_date"] = row["sort_stamp"]
                summary["last_evidence_business_name"] = row["business_name"]

        if row["verification_review_status"] in {"reviewed_complete", "reviewed_insufficient"}:
            if row["sort_stamp"] >= (summary["last_reviewed_run_date"] or ""):
                summary["last_reviewed_run_key"] = row["run_key"]
                summary["last_reviewed_run_date"] = row["sort_stamp"]
                summary["last_reviewed_status"] = row["verification_review_status"]
                summary["last_reviewed_business_name"] = row["business_name"]

    overview = {
        "offers_with_runs": 0,
        "offers_with_review_ready_runs": 0,
        "offers_with_reviewed_complete_runs": 0,
        "offers_ready_for_human_verification": 0,
    }
    for summary in offers_by_key.values():
        summary["proof_missing_count"] = max(0, summary["total_runs"] - summary["proof_present_count"])
        if summary["total_runs"]:
            summary["proof_coverage_summary"] = f"{summary['proof_present_count']} / {summary['total_runs']} runs with before/after proof"
            if summary["proof_present_count"] > 0:
                summary["evidence_presence"] = "Evidence present"
            elif summary["artifact_refs_count"] > 0 or summary["closeout_captured_count"] > 0:
                summary["evidence_presence"] = "Partial evidence present"
            else:
                summary["evidence_presence"] = "Runs exist, but proof is still missing"
        summary["recent_runs"].sort(key=lambda item: item.get("sort_stamp", ""), reverse=True)
        summary["recent_runs"] = summary["recent_runs"][:5]
        summary["promotion_readiness"] = _offer_promotion_readiness(summary)
        if summary["total_runs"] > 0:
            overview["offers_with_runs"] += 1
        if summary["ready_for_manual_review_count"] > 0:
            overview["offers_with_review_ready_runs"] += 1
        if summary["reviewed_complete_count"] > 0:
            overview["offers_with_reviewed_complete_runs"] += 1
        if summary["promotion_readiness"]["status"] == "ready_for_human_verification":
            overview["offers_ready_for_human_verification"] += 1
    offers = sorted(offers_by_key.values(), key=lambda item: (item.get("offer_type") != "public", item.get("offer_label", "")))
    return {"offers": offers, "offers_by_key": offers_by_key, "overview": overview}


@app.route("/api/delivery_run_clients")
def api_delivery_run_clients():
    all_records = _lm.get_all_records()
    clients = []
    for key, record in all_records.items():
        raw_profile = record.get("delivery_profile")
        if not isinstance(raw_profile, dict):
            continue
        stage = (raw_profile.get("stage") or "").strip().lower()
        if not stage:
            continue
        clients.append({
            "key":              key,
            "business_name":    record.get("business_name", ""),
            "city":             record.get("city", ""),
            "stage":            stage,
            "core_offer":       raw_profile.get("core_offer", ""),
            "bundle_key":       raw_profile.get("bundle_key", ""),
            "selected_modules": raw_profile.get("selected_modules", []),
        })
    stage_order = {"won": 0, "deployment_pending": 1, "live": 2, "call_booked": 3}
    clients.sort(key=lambda c: stage_order.get(c.get("stage", ""), 9))
    return jsonify({"ok": True, "clients": clients})


@app.route("/api/delivery_run", methods=["GET"])
def api_delivery_run_get():
    run_key   = (request.args.get("run_key")   or "").strip()
    offer_key = (request.args.get("offer_key") or "").strip()  # backward compat
    if not run_key and offer_key:
        run_key = offer_key
    log = _load_exec_log()
    if run_key:
        state = log.get(run_key) or log.get("practice|" + run_key) or {}
        return jsonify({"ok": True, "run_key": run_key, "state": state})
    return jsonify({"ok": True, "all": log})


@app.route("/api/delivery_run", methods=["POST"])
def api_delivery_run_save():
    import datetime
    body = request.json or {}
    run_key       = (body.get("run_key")       or "").strip()
    offer_key     = (body.get("offer_key")     or "").strip()
    lead_key      = (body.get("lead_key")      or "practice").strip()
    business_name = (body.get("business_name") or "").strip()[:200]

    if not run_key:
        if offer_key:
            run_key = offer_key  # backward compat
        else:
            return jsonify({"ok": False, "error": "run_key or offer_key required"}), 400

    if not offer_key and "|" in run_key:
        offer_key = run_key.split("|", 1)[1]

    if offer_key and offer_key not in DELIVERY_CATALOG:
        return jsonify({"ok": False, "error": "unknown offer_key"}), 400

    log = _load_exec_log()
    merged = dict(log.get(run_key, {}))

    if lead_key and lead_key != "practice":
        merged["lead_key"] = lead_key
    if offer_key:
        merged["offer_key"] = offer_key
    if business_name:
        merged["business_name"] = business_name

    patch = body.get("state", {})

    if "checks" in patch and isinstance(patch["checks"], dict):
        existing_checks = merged.get("checks", {})
        for k, v in patch["checks"].items():
            if isinstance(k, str) and isinstance(v, bool):
                existing_checks[k] = v
        merged["checks"] = existing_checks

    text_fields = ("work_notes", "before_proof_link", "after_proof_link",
                   "artifact_refs", "blockers", "closeout_notes", "post_closeout_notes",
                   "proof_links", "delivery_date", "closeout_date", "remaining_recommendations",
                   "verification_review_notes")  # proof_links kept for backward compat
    for field in text_fields:
        if field in patch and isinstance(patch[field], str):
            merged[field] = patch[field].strip()[:2000]

    if "closeout_status" in patch and patch["closeout_status"] in ("open", "in_progress", "captured"):
        merged["closeout_status"] = patch["closeout_status"]

    if "owner_ack_status" in patch and patch["owner_ack_status"] in ("pending", "acknowledged"):
        merged["owner_ack_status"] = patch["owner_ack_status"]

    if "verification_review_status" in patch and patch["verification_review_status"] in _DELIVERY_REVIEW_STATUSES:
        merged["verification_review_status"] = patch["verification_review_status"]

    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    if "started_at" not in merged:
        merged["started_at"] = now
    merged["updated_at"] = now

    log[run_key] = merged
    _save_exec_log(log)
    return jsonify({"ok": True, "run_key": run_key, "state": merged})


@app.route("/api/delivery_review_queue")
def api_delivery_review_queue():
    records = _lm.get_all_records()
    log = _load_exec_log()
    rows = []
    for run_key, state in log.items():
        row = _build_delivery_review_row(run_key, state, records)
        if row:
            rows.append(row)
    status_order = {"ready_for_manual_review": 0, "not_ready": 1, "reviewed_insufficient": 2, "reviewed_complete": 3}
    rows.sort(key=lambda row: (status_order.get(row["verification_review_status"], 9), not row["candidate_for_review"], row.get("updated_at", "")), reverse=False)
    return jsonify({"ok": True, "rows": rows})


@app.route("/api/delivery_offer_evidence")
def api_delivery_offer_evidence():
    payload = _build_offer_evidence_summary()
    return jsonify({"ok": True, **payload})


@app.route("/api/conversation_queue")
def api_conversation_queue():
    rows = _read_pending(); convos = []
    for i,r in enumerate(rows):
        if (r.get("replied") or "").lower()=="true":
            _enrich_row(r,i)
            mem = _lm.get_delivery_profile(r)
            r["delivery_profile"] = _normalize_delivery_profile(mem, r)
            convos.append(r)
    convos.sort(key=lambda r:r.get("replied_at",""),reverse=True); return jsonify(convos)

@app.route("/api/update_conversation", methods=["POST"])
def api_update_conversation():
    d = request.json or {}; idx = d.get("index"); rows = _read_pending()
    if idx is None or not (0 <= idx < len(rows)): return jsonify({"ok":False,"error":"Invalid index"}),400
    rows[idx]["conversation_notes"] = d.get("notes",rows[idx].get("conversation_notes",""))
    rows[idx]["conversation_next_step"] = d.get("next_step",rows[idx].get("conversation_next_step",""))
    _write_pending(rows)
    # Pass 47: record lifecycle event when a note is saved
    _notes = (d.get("notes") or "").strip()
    if _notes:
        try:
            _lm.record_event(rows[idx], _lm.EVT_NOTE_ADDED,
                             detail=_notes[:120])
        except Exception as _e:
            log.warning("lead_memory event failed (note_added): %s", _e)
    return jsonify({"ok":True})


@app.route("/api/update_delivery_profile", methods=["POST"])
def api_update_delivery_profile():
    d = request.json or {}
    idx = d.get("index")
    patch = d.get("profile")
    rows = _read_pending()

    if idx is None or not isinstance(idx, int) or not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400
    if not isinstance(patch, dict):
        return jsonify({"ok": False, "error": "profile must be an object"}), 400

    clean_patch: dict = {}
    current_profile = _normalize_delivery_profile(_lm.get_delivery_profile(rows[idx]), rows[idx])

    if "package_key" in patch:
        package_key = (patch.get("package_key") or "").strip().lower()
        if package_key:
            legacy_stack = _legacy_stack_for_package(package_key)
            if not legacy_stack:
                return jsonify({"ok": False, "error": "Invalid package_key"}), 400
            clean_patch.update(legacy_stack)

    if "core_offer" in patch:
        core_offer = (patch.get("core_offer") or "").strip().lower()
        if core_offer and core_offer not in _DELIVERY_CORE_KEYS:
            return jsonify({"ok": False, "error": "Invalid core_offer"}), 400
        clean_patch["core_offer"] = core_offer

    if "bundle_key" in patch:
        bundle_key = (patch.get("bundle_key") or "").strip().lower()
        if bundle_key and bundle_key not in _DELIVERY_BUNDLE_KEYS:
            return jsonify({"ok": False, "error": "Invalid bundle_key"}), 400
        clean_patch["bundle_key"] = bundle_key

    if "selected_modules" in patch:
        selected_modules = patch.get("selected_modules")
        if not isinstance(selected_modules, list):
            return jsonify({"ok": False, "error": "selected_modules must be an array"}), 400
        for item in selected_modules:
            if not isinstance(item, str) or item.strip().lower() not in _DELIVERY_SPECIALTY_KEYS:
                return jsonify({"ok": False, "error": "selected_modules contains invalid values"}), 400
        clean_modules = _normalize_selected_modules(selected_modules)
        clean_patch["selected_modules"] = clean_modules

    if "price" in patch:
        price = patch.get("price")
        if isinstance(price, (int, float)):
            clean_patch["price"] = str(price)
        elif isinstance(price, str):
            clean_patch["price"] = price.strip()[:80]
        elif price in (None, ""):
            clean_patch["price"] = ""
        else:
            return jsonify({"ok": False, "error": "price must be a string or number"}), 400

    if "agreement_status" in patch:
        agreement_status = patch.get("agreement_status")
        if not isinstance(agreement_status, str):
            return jsonify({"ok": False, "error": "agreement_status must be a string"}), 400
        clean_patch["agreement_status"] = agreement_status.strip()[:40]

    if "invoice_status" in patch:
        invoice_status = patch.get("invoice_status")
        if not isinstance(invoice_status, str):
            return jsonify({"ok": False, "error": "invoice_status must be a string"}), 400
        clean_patch["invoice_status"] = invoice_status.strip()[:40]

    if "offer_notes" in patch:
        offer_notes = patch.get("offer_notes")
        if not isinstance(offer_notes, str):
            return jsonify({"ok": False, "error": "offer_notes must be a string"}), 400
        clean_patch["offer_notes"] = offer_notes[:2000]
    if "artifact_links" in patch:
        clean_patch["artifact_links"] = _clean_link_list(patch.get("artifact_links"))
    if "credential_status" in patch:
        credential_status = patch.get("credential_status")
        if not isinstance(credential_status, str):
            return jsonify({"ok": False, "error": "credential_status must be a string"}), 400
        clean_patch["credential_status"] = credential_status.strip()[:80]
    if "handoff_status" in patch:
        handoff_status = patch.get("handoff_status")
        if not isinstance(handoff_status, str):
            return jsonify({"ok": False, "error": "handoff_status must be a string"}), 400
        clean_patch["handoff_status"] = handoff_status.strip()[:80]
    if "closeout_status" in patch:
        closeout_status = patch.get("closeout_status")
        if not isinstance(closeout_status, str):
            return jsonify({"ok": False, "error": "closeout_status must be a string"}), 400
        clean_patch["closeout_status"] = closeout_status.strip()[:80]
    if "revision_status" in patch:
        revision_status = patch.get("revision_status")
        if not isinstance(revision_status, str):
            return jsonify({"ok": False, "error": "revision_status must be a string"}), 400
        clean_patch["revision_status"] = revision_status.strip()[:80]
    if "revision_round" in patch:
        try:
            clean_patch["revision_round"] = max(0, int(patch.get("revision_round") or 0))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "revision_round must be a number"}), 400
    if "change_order_status" in patch:
        change_order_status = patch.get("change_order_status")
        if not isinstance(change_order_status, str):
            return jsonify({"ok": False, "error": "change_order_status must be a string"}), 400
        clean_patch["change_order_status"] = change_order_status.strip()[:80]
    if "change_order_needed" in patch:
        clean_patch["change_order_needed"] = _coerce_bool(patch.get("change_order_needed"))
    if "change_order_notes" in patch:
        change_order_notes = patch.get("change_order_notes")
        if not isinstance(change_order_notes, str):
            return jsonify({"ok": False, "error": "change_order_notes must be a string"}), 400
        clean_patch["change_order_notes"] = change_order_notes[:1000]
    if "blockers" in patch:
        clean_patch["blockers"] = _clean_string_list(patch.get("blockers"))
    if "next_step" in patch:
        next_step = patch.get("next_step")
        if not isinstance(next_step, str):
            return jsonify({"ok": False, "error": "next_step must be a string"}), 400
        clean_patch["next_step"] = next_step.strip()[:200]
    if "activation_packet_status" in patch:
        activation_packet_status = patch.get("activation_packet_status")
        if not isinstance(activation_packet_status, str):
            return jsonify({"ok": False, "error": "activation_packet_status must be a string"}), 400
        clean_patch["activation_packet_status"] = activation_packet_status.strip()[:80]

    if "stage" in patch:
        stage = (patch.get("stage") or "").strip().lower()
        if stage and stage not in _DELIVERY_STAGES:
            return jsonify({"ok": False, "error": "Invalid stage"}), 400
        clean_patch["stage"] = stage

    if "readiness" in patch:
        readiness = patch.get("readiness")
        if not isinstance(readiness, dict):
            return jsonify({"ok": False, "error": "readiness must be an object"}), 400
        clean_readiness = {}
        for key, value in readiness.items():
            if key not in _DELIVERY_READINESS_KEYS:
                continue
            clean_readiness[key] = bool(value)
        clean_patch["readiness"] = clean_readiness

    clean_patch, error = _finalize_delivery_stack_patch(clean_patch, current_profile)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    clean_patch = _finalize_activation_patch(clean_patch, current_profile)

    if not clean_patch:
        return jsonify({"ok": True, "delivery_profile": current_profile})

    record = _lm.update_delivery_profile(rows[idx], clean_patch)
    if not record:
        return jsonify({"ok": False, "error": "Failed to update delivery profile"}), 500

    profile = _normalize_delivery_profile(record.get("delivery_profile"), rows[idx])
    return jsonify({"ok": True, "delivery_profile": profile})

# ── Pass 86: Delivery Board endpoints ────────────────────────────────────────

_BOARD_STAGES = {"won", "deployment_pending", "live"}


@app.route("/api/delivery_board")
def api_delivery_board():
    """
    Return board-ready rows for the delivery board (stages: won, deployment_pending, live).
    Also returns compact top stats.
    """
    all_records = _lm.get_all_records()
    rows = []
    for key, record in all_records.items():
        raw_profile = record.get("delivery_profile")
        if not isinstance(raw_profile, dict):
            continue
        stage = (raw_profile.get("stage") or "").strip().lower()
        if stage not in _BOARD_STAGES:
            continue
        profile = _normalize_delivery_profile(raw_profile)
        readiness = profile.get("readiness", {})
        readiness_keys = list(_DELIVERY_READINESS_KEYS)
        completed = sum(1 for k in readiness_keys if readiness.get(k))
        total_keys = len(readiness_keys)
        rows.append({
            "key":           key,
            "business_name": record.get("business_name", ""),
            "city":          record.get("city", ""),
            "website":       record.get("website", ""),
            "phone":         record.get("phone", ""),
            "stage":         stage,
            "core_offer":    profile.get("core_offer", ""),
            "bundle_key":    profile.get("bundle_key", ""),
            "selected_modules": profile.get("selected_modules", []),
            "price":         profile.get("price", ""),
            "monthly_support": profile.get("monthly_support", False),
            "monthly_fee":   profile.get("monthly_fee", ""),
            "agreement_status": profile.get("agreement_status", ""),
            "invoice_status": profile.get("invoice_status", ""),
            "deposit_status": profile.get("deposit_status", ""),
            "offer_notes":   profile.get("offer_notes", ""),
            "accepted_option_status": profile.get("accepted_option_status", "draft_only"),
            "accepted_option_label": profile.get("accepted_option_label", ""),
            "accepted_scope_note": profile.get("accepted_scope_note", ""),
            "prelaunch_mode": profile.get("prelaunch_mode", PRELAUNCH_MODE),
            "offer_type":    profile.get("offer_type", "public"),
            "build_status":  profile.get("build_status", "planned"),
            "launch_eligible": profile.get("launch_eligible", False),
            "visibility_state": profile.get("visibility_state", "hidden"),
            "target_visibility_state": profile.get("target_visibility_state", "hidden"),
            "kit_key":       profile.get("kit_key", ""),
            "kit_status":    profile.get("kit_status", ""),
            "current_truth_notes": profile.get("current_truth_notes", []),
            "target_truth_notes": profile.get("target_truth_notes", []),
            "required_artifacts": profile.get("required_artifacts", []),
            "access_requirements": profile.get("access_requirements", []),
            "missing_artifacts": profile.get("missing_artifacts", []),
            "missing_qa": profile.get("missing_qa", []),
            "missing_closeout": profile.get("missing_closeout", []),
            "missing_rollback": profile.get("missing_rollback", []),
            "next_hardening_steps": profile.get("next_hardening_steps", []),
            "rollback_plan": profile.get("rollback_plan", []),
            "ownership_mode": profile.get("ownership_mode", ""),
            "support_policy_key": profile.get("support_policy_key", ""),
            "support_summary": profile.get("support_summary", ""),
            "handoff_status": profile.get("handoff_status", ""),
            "closeout_status": profile.get("closeout_status", ""),
            "activation_packet_status": profile.get("activation_packet_status", ""),
            "blockers":      profile.get("blockers", []),
            "next_step":     profile.get("next_step", ""),
            "readiness":     readiness,
            "readiness_pct": round(completed / total_keys * 100) if total_keys else 0,
            "readiness_done": completed,
            "readiness_total": total_keys,
            "updated_at":    profile.get("updated_at", ""),
            "last_updated":  record.get("last_updated", ""),
        })

    rows.sort(key=lambda r: r.get("last_updated", ""), reverse=True)

    stats = {
        "won":                sum(1 for r in rows if r["stage"] == "won"),
        "deployment_pending": sum(1 for r in rows if r["stage"] == "deployment_pending"),
        "live":               sum(1 for r in rows if r["stage"] == "live"),
        "total":              len(rows),
        "fully_ready":        sum(1 for r in rows if r["readiness_pct"] == 100),
    }

    return jsonify({"ok": True, "stats": stats, "rows": rows})


@app.route("/api/update_delivery_profile_by_key", methods=["POST"])
def api_update_delivery_profile_by_key():
    """
    Update delivery profile fields for a lead identified by lead_key string.
    Used by the delivery board where only the key (not a queue row) is available.

    Input:  { key, profile: { stage?, core_offer?, bundle_key?, selected_modules?, price?, agreement_status?, invoice_status?, offer_notes?, readiness? } }
    Output: { ok, delivery_profile }
    """
    d     = request.json or {}
    key   = (d.get("key") or "").strip()
    patch = d.get("profile")

    if not key:
        return jsonify({"ok": False, "error": "key is required"}), 400
    if not isinstance(patch, dict):
        return jsonify({"ok": False, "error": "profile must be an object"}), 400

    clean_patch: dict = {}
    record = _lm.get_all_records().get(key)
    current_profile = _normalize_delivery_profile(record.get("delivery_profile") if isinstance(record, dict) else None, record if isinstance(record, dict) else None)

    if "package_key" in patch:
        package_key = (patch.get("package_key") or "").strip().lower()
        if package_key:
            legacy_stack = _legacy_stack_for_package(package_key)
            if not legacy_stack:
                return jsonify({"ok": False, "error": "Invalid package_key"}), 400
            clean_patch.update(legacy_stack)

    if "core_offer" in patch:
        core_offer = (patch.get("core_offer") or "").strip().lower()
        if core_offer and core_offer not in _DELIVERY_CORE_KEYS:
            return jsonify({"ok": False, "error": "Invalid core_offer"}), 400
        clean_patch["core_offer"] = core_offer

    if "bundle_key" in patch:
        bundle_key = (patch.get("bundle_key") or "").strip().lower()
        if bundle_key and bundle_key not in _DELIVERY_BUNDLE_KEYS:
            return jsonify({"ok": False, "error": "Invalid bundle_key"}), 400
        clean_patch["bundle_key"] = bundle_key

    if "selected_modules" in patch:
        selected_modules = patch.get("selected_modules")
        if not isinstance(selected_modules, list):
            return jsonify({"ok": False, "error": "selected_modules must be an array"}), 400
        for item in selected_modules:
            if not isinstance(item, str) or item.strip().lower() not in _DELIVERY_SPECIALTY_KEYS:
                return jsonify({"ok": False, "error": "selected_modules contains invalid values"}), 400
        clean_modules = _normalize_selected_modules(selected_modules)
        clean_patch["selected_modules"] = clean_modules

    if "price" in patch:
        price = patch.get("price")
        if isinstance(price, (int, float)):
            clean_patch["price"] = str(price)
        elif isinstance(price, str):
            clean_patch["price"] = price.strip()[:80]
        elif price in (None, ""):
            clean_patch["price"] = ""
        else:
            return jsonify({"ok": False, "error": "price must be a string or number"}), 400

    if "agreement_status" in patch:
        agreement_status = patch.get("agreement_status")
        if not isinstance(agreement_status, str):
            return jsonify({"ok": False, "error": "agreement_status must be a string"}), 400
        clean_patch["agreement_status"] = agreement_status.strip()[:40]

    if "invoice_status" in patch:
        invoice_status = patch.get("invoice_status")
        if not isinstance(invoice_status, str):
            return jsonify({"ok": False, "error": "invoice_status must be a string"}), 400
        clean_patch["invoice_status"] = invoice_status.strip()[:40]

    if "offer_notes" in patch:
        offer_notes = patch.get("offer_notes")
        if not isinstance(offer_notes, str):
            return jsonify({"ok": False, "error": "offer_notes must be a string"}), 400
        clean_patch["offer_notes"] = offer_notes[:2000]
    if "artifact_links" in patch:
        clean_patch["artifact_links"] = _clean_link_list(patch.get("artifact_links"))
    if "credential_status" in patch:
        credential_status = patch.get("credential_status")
        if not isinstance(credential_status, str):
            return jsonify({"ok": False, "error": "credential_status must be a string"}), 400
        clean_patch["credential_status"] = credential_status.strip()[:80]
    if "handoff_status" in patch:
        handoff_status = patch.get("handoff_status")
        if not isinstance(handoff_status, str):
            return jsonify({"ok": False, "error": "handoff_status must be a string"}), 400
        clean_patch["handoff_status"] = handoff_status.strip()[:80]
    if "closeout_status" in patch:
        closeout_status = patch.get("closeout_status")
        if not isinstance(closeout_status, str):
            return jsonify({"ok": False, "error": "closeout_status must be a string"}), 400
        clean_patch["closeout_status"] = closeout_status.strip()[:80]
    if "revision_status" in patch:
        revision_status = patch.get("revision_status")
        if not isinstance(revision_status, str):
            return jsonify({"ok": False, "error": "revision_status must be a string"}), 400
        clean_patch["revision_status"] = revision_status.strip()[:80]
    if "revision_round" in patch:
        try:
            clean_patch["revision_round"] = max(0, int(patch.get("revision_round") or 0))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "revision_round must be a number"}), 400
    if "change_order_status" in patch:
        change_order_status = patch.get("change_order_status")
        if not isinstance(change_order_status, str):
            return jsonify({"ok": False, "error": "change_order_status must be a string"}), 400
        clean_patch["change_order_status"] = change_order_status.strip()[:80]
    if "change_order_needed" in patch:
        clean_patch["change_order_needed"] = _coerce_bool(patch.get("change_order_needed"))
    if "change_order_notes" in patch:
        change_order_notes = patch.get("change_order_notes")
        if not isinstance(change_order_notes, str):
            return jsonify({"ok": False, "error": "change_order_notes must be a string"}), 400
        clean_patch["change_order_notes"] = change_order_notes[:1000]
    if "blockers" in patch:
        clean_patch["blockers"] = _clean_string_list(patch.get("blockers"))
    if "next_step" in patch:
        next_step = patch.get("next_step")
        if not isinstance(next_step, str):
            return jsonify({"ok": False, "error": "next_step must be a string"}), 400
        clean_patch["next_step"] = next_step.strip()[:200]
    if "activation_packet_status" in patch:
        activation_packet_status = patch.get("activation_packet_status")
        if not isinstance(activation_packet_status, str):
            return jsonify({"ok": False, "error": "activation_packet_status must be a string"}), 400
        clean_patch["activation_packet_status"] = activation_packet_status.strip()[:80]

    if "stage" in patch:
        stage = (patch.get("stage") or "").strip().lower()
        if stage and stage not in _DELIVERY_STAGES:
            return jsonify({"ok": False, "error": "Invalid stage"}), 400
        clean_patch["stage"] = stage

    if "readiness" in patch:
        readiness = patch.get("readiness")
        if not isinstance(readiness, dict):
            return jsonify({"ok": False, "error": "readiness must be an object"}), 400
        clean_readiness = {}
        for rkey, value in readiness.items():
            if rkey not in _DELIVERY_READINESS_KEYS:
                continue
            clean_readiness[rkey] = bool(value)
        clean_patch["readiness"] = clean_readiness

    clean_patch, error = _finalize_delivery_stack_patch(clean_patch, current_profile)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    clean_patch = _finalize_activation_patch(clean_patch, current_profile)

    if not clean_patch:
        return jsonify({"ok": False, "error": "No valid fields in profile patch"}), 400

    record = _lm.update_delivery_profile_by_key(key, clean_patch)
    if record is None:
        return jsonify({"ok": False, "error": "Key not found in lead memory"}), 404

    profile = _normalize_delivery_profile(record.get("delivery_profile"))
    return jsonify({"ok": True, "delivery_profile": profile})


@app.route("/api/deploy_activation", methods=["GET", "POST"])
def api_deploy_activation():
    if request.method == "GET":
        d = request.args
    else:
        d = request.json or {}

    identity = d.get("identity") if isinstance(d.get("identity"), dict) else {}
    key = (d.get("key") or "").strip()
    if not key and identity:
        try:
            key = _lm.lead_key(identity)
        except Exception:
            key = ""

    if not key:
        return jsonify({"ok": False, "error": "key or identity is required"}), 400

    record = _lm.get_all_records().get(key)
    current_profile = _normalize_delivery_profile(
        record.get("delivery_profile") if isinstance(record, dict) else None,
        record if isinstance(record, dict) else identity,
    )

    if request.method == "GET":
        return jsonify({
            "ok": True,
            "key": key,
            "exists": bool(record),
            "identity": {
                "business_name": (record or {}).get("business_name", identity.get("business_name", "")),
                "city": (record or {}).get("city", identity.get("city", "")),
                "website": (record or {}).get("website", identity.get("website", "")),
                "phone": (record or {}).get("phone", identity.get("phone", "")),
            },
            "delivery_profile": current_profile,
        })

    patch = d.get("profile")
    if not isinstance(patch, dict):
        return jsonify({"ok": False, "error": "profile must be an object"}), 400

    clean_patch: dict = {}

    if "snapshot" in patch:
        snapshot = patch.get("snapshot")
        if not isinstance(snapshot, dict):
            return jsonify({"ok": False, "error": "snapshot must be an object"}), 400
        clean_patch["snapshot"] = _normalize_snapshot(snapshot)

    if "discovery" in patch:
        discovery = patch.get("discovery")
        if not isinstance(discovery, dict):
            return jsonify({"ok": False, "error": "discovery must be an object"}), 400
        clean_patch["discovery"] = _normalize_discovery(discovery)
    if "consult_builder" in patch:
        consult_builder = patch.get("consult_builder")
        if not isinstance(consult_builder, dict):
            return jsonify({"ok": False, "error": "consult_builder must be an object"}), 400
        clean_patch["consult_builder"] = _normalize_consult_builder(consult_builder)
    if "draft_recommendation" in patch:
        draft_recommendation = patch.get("draft_recommendation")
        if not isinstance(draft_recommendation, dict):
            return jsonify({"ok": False, "error": "draft_recommendation must be an object"}), 400
        clean_patch["draft_recommendation"] = dict(draft_recommendation)
    if "proposal_options" in patch:
        proposal_options = patch.get("proposal_options")
        if not isinstance(proposal_options, list):
            return jsonify({"ok": False, "error": "proposal_options must be an array"}), 400
        clean_patch["proposal_options"] = _normalize_proposal_options(proposal_options)
    for field in (
        "accepted_option_id",
        "accepted_option_status",
        "accepted_option_date",
        "accepted_option_label",
        "accepted_option_note",
        "accepted_scope_note",
        "accepted_assumptions",
    ):
        if field in patch:
            value = patch.get(field)
            if not isinstance(value, str):
                return jsonify({"ok": False, "error": f"{field} must be a string"}), 400
            if field == "accepted_option_status":
                status = value.strip().lower()
                if status and status not in _ACCEPTED_OPTION_STATUSES:
                    return jsonify({"ok": False, "error": "Invalid accepted_option_status"}), 400
                clean_patch[field] = status or "draft_only"
            elif field in {"accepted_option_note", "accepted_scope_note", "accepted_assumptions"}:
                clean_patch[field] = value.strip()[:1000]
            elif field == "accepted_option_label":
                clean_patch[field] = value.strip()[:120]
            else:
                clean_patch[field] = value.strip()[:80]
    if "consult_builder" in patch:
        consult_builder = patch.get("consult_builder")
        if not isinstance(consult_builder, dict):
            return jsonify({"ok": False, "error": "consult_builder must be an object"}), 400
        clean_patch["consult_builder"] = _normalize_consult_builder(consult_builder)
    if "draft_recommendation" in patch:
        draft_recommendation = patch.get("draft_recommendation")
        if not isinstance(draft_recommendation, dict):
            return jsonify({"ok": False, "error": "draft_recommendation must be an object"}), 400
        clean_patch["draft_recommendation"] = dict(draft_recommendation)

    if "core_offer" in patch:
        core_offer = (patch.get("core_offer") or "").strip().lower()
        if core_offer and core_offer not in _DELIVERY_CORE_KEYS:
            return jsonify({"ok": False, "error": "Invalid core_offer"}), 400
        clean_patch["core_offer"] = core_offer

    if "bundle_key" in patch:
        bundle_key = (patch.get("bundle_key") or "").strip().lower()
        if bundle_key and bundle_key not in _DELIVERY_BUNDLE_KEYS:
            return jsonify({"ok": False, "error": "Invalid bundle_key"}), 400
        clean_patch["bundle_key"] = bundle_key

    if "selected_modules" in patch:
        selected_modules = patch.get("selected_modules")
        if not isinstance(selected_modules, list):
            return jsonify({"ok": False, "error": "selected_modules must be an array"}), 400
        for item in selected_modules:
            if not isinstance(item, str) or item.strip().lower() not in _DELIVERY_SPECIALTY_KEYS:
                return jsonify({"ok": False, "error": "selected_modules contains invalid values"}), 400
        clean_patch["selected_modules"] = _normalize_selected_modules(selected_modules)

    if "price" in patch:
        price = patch.get("price")
        if isinstance(price, (int, float)):
            clean_patch["price"] = str(price)
        elif isinstance(price, str):
            clean_patch["price"] = price.strip()[:80]
        elif price in (None, ""):
            clean_patch["price"] = ""
        else:
            return jsonify({"ok": False, "error": "price must be a string or number"}), 400

    if "pricing_mode" in patch:
        pricing_mode = (patch.get("pricing_mode") or "").strip().lower()
        if pricing_mode and pricing_mode not in _DEPLOY_QUOTE_MODES:
            return jsonify({"ok": False, "error": "Invalid pricing_mode"}), 400
        clean_patch["pricing_mode"] = pricing_mode

    if "monthly_support" in patch:
        clean_patch["monthly_support"] = _coerce_bool(patch.get("monthly_support"))

    if "monthly_fee" in patch:
        monthly_fee = patch.get("monthly_fee")
        if isinstance(monthly_fee, (int, float)):
            clean_patch["monthly_fee"] = str(monthly_fee)
        elif isinstance(monthly_fee, str):
            clean_patch["monthly_fee"] = monthly_fee.strip()[:40]
        elif monthly_fee in (None, ""):
            clean_patch["monthly_fee"] = ""
        else:
            return jsonify({"ok": False, "error": "monthly_fee must be a string or number"}), 400

    if "agreement_status" in patch:
        agreement_status = patch.get("agreement_status")
        if not isinstance(agreement_status, str):
            return jsonify({"ok": False, "error": "agreement_status must be a string"}), 400
        clean_patch["agreement_status"] = agreement_status.strip()[:40]

    if "invoice_status" in patch:
        invoice_status = patch.get("invoice_status")
        if not isinstance(invoice_status, str):
            return jsonify({"ok": False, "error": "invoice_status must be a string"}), 400
        clean_patch["invoice_status"] = invoice_status.strip()[:40]

    if "deposit_status" in patch:
        deposit_status = patch.get("deposit_status")
        if not isinstance(deposit_status, str):
            return jsonify({"ok": False, "error": "deposit_status must be a string"}), 400
        clean_patch["deposit_status"] = deposit_status.strip()[:40]

    if "offer_notes" in patch:
        offer_notes = patch.get("offer_notes")
        if not isinstance(offer_notes, str):
            return jsonify({"ok": False, "error": "offer_notes must be a string"}), 400
        clean_patch["offer_notes"] = offer_notes[:2000]
    if "artifact_links" in patch:
        clean_patch["artifact_links"] = _clean_link_list(patch.get("artifact_links"))
    if "credential_status" in patch:
        credential_status = patch.get("credential_status")
        if not isinstance(credential_status, str):
            return jsonify({"ok": False, "error": "credential_status must be a string"}), 400
        clean_patch["credential_status"] = credential_status.strip()[:80]
    if "handoff_status" in patch:
        handoff_status = patch.get("handoff_status")
        if not isinstance(handoff_status, str):
            return jsonify({"ok": False, "error": "handoff_status must be a string"}), 400
        clean_patch["handoff_status"] = handoff_status.strip()[:80]
    if "closeout_status" in patch:
        closeout_status = patch.get("closeout_status")
        if not isinstance(closeout_status, str):
            return jsonify({"ok": False, "error": "closeout_status must be a string"}), 400
        clean_patch["closeout_status"] = closeout_status.strip()[:80]
    if "revision_status" in patch:
        revision_status = patch.get("revision_status")
        if not isinstance(revision_status, str):
            return jsonify({"ok": False, "error": "revision_status must be a string"}), 400
        clean_patch["revision_status"] = revision_status.strip()[:80]
    if "revision_round" in patch:
        try:
            clean_patch["revision_round"] = max(0, int(patch.get("revision_round") or 0))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "revision_round must be a number"}), 400
    if "change_order_status" in patch:
        change_order_status = patch.get("change_order_status")
        if not isinstance(change_order_status, str):
            return jsonify({"ok": False, "error": "change_order_status must be a string"}), 400
        clean_patch["change_order_status"] = change_order_status.strip()[:80]
    if "change_order_needed" in patch:
        clean_patch["change_order_needed"] = _coerce_bool(patch.get("change_order_needed"))
    if "change_order_notes" in patch:
        change_order_notes = patch.get("change_order_notes")
        if not isinstance(change_order_notes, str):
            return jsonify({"ok": False, "error": "change_order_notes must be a string"}), 400
        clean_patch["change_order_notes"] = change_order_notes[:1000]
    if "blockers" in patch:
        clean_patch["blockers"] = _clean_string_list(patch.get("blockers"))
    if "next_step" in patch:
        next_step = patch.get("next_step")
        if not isinstance(next_step, str):
            return jsonify({"ok": False, "error": "next_step must be a string"}), 400
        clean_patch["next_step"] = next_step.strip()[:200]
    if "activation_packet_status" in patch:
        activation_packet_status = patch.get("activation_packet_status")
        if not isinstance(activation_packet_status, str):
            return jsonify({"ok": False, "error": "activation_packet_status must be a string"}), 400
        clean_patch["activation_packet_status"] = activation_packet_status.strip()[:80]

    if "stage" in patch:
        stage = (patch.get("stage") or "").strip().lower()
        if stage and stage not in _DELIVERY_STAGES:
            return jsonify({"ok": False, "error": "Invalid stage"}), 400
        clean_patch["stage"] = stage

    if "readiness" in patch:
        readiness = patch.get("readiness")
        if not isinstance(readiness, dict):
            return jsonify({"ok": False, "error": "readiness must be an object"}), 400
        clean_readiness = {}
        for key_name, value in readiness.items():
            if key_name not in _DELIVERY_READINESS_KEYS:
                continue
            clean_readiness[key_name] = bool(value)
        clean_patch["readiness"] = clean_readiness

    clean_patch, error = _finalize_delivery_stack_patch(clean_patch, current_profile)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    clean_patch = _finalize_activation_patch(clean_patch, current_profile)

    record = _lm.upsert_delivery_profile_by_key(key, clean_patch, identity=identity)
    if not record:
        return jsonify({"ok": False, "error": "Failed to upsert delivery profile"}), 500

    profile = _normalize_delivery_profile(record.get("delivery_profile"), record)
    return jsonify({"ok": True, "key": key, "delivery_profile": profile, "identity": {
        "business_name": record.get("business_name", ""),
        "city": record.get("city", ""),
        "website": record.get("website", ""),
        "phone": record.get("phone", ""),
    }})


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
    from send.email_sender_agent import _send_email_via_gmail
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
        return jsonify({
            "ok": False,
            "error": "Row index/name mismatch — queue may have changed",
            "blocked_reason": "row_mismatch",
        }), 409

    fs = compute_followup_status(row)
    if fs["status"] != "due":
        return jsonify({"ok": False, "error": f"Follow-up not due (status: {fs['status']})"}), 400

    to_email = (row.get("to_email") or "").strip()
    if not to_email or "@" not in to_email:
        return jsonify({"ok": False, "error": "No valid email address for this row"}), 400

    touch_num = fs["touch_num"]
    name      = row.get("business_name", "").strip()
    try:
        plan = build_followup_plan(row, touch_num)
    except FollowupBlockedError as exc:
        return jsonify({
            "ok": False,
            "blocked": True,
            "blocked_reason": exc.reason,
            "error": str(exc),
        }), 422

    subject = plan["subject"]
    body = plan["body"]

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
    try:
        _lm.record_event(row, _lm.EVT_FOLLOWUP_SENT,
                         detail=f"touch={touch_num}; angle={plan['angle_family']}")
    except Exception as _lm_exc:
        log.warning("lead_memory event failed (followup_sent): %s", _lm_exc)
    log.info("send_followup ok: idx=%s name=%r touch=%d to=%s mid=%s",
             idx, name, touch_num, to_email, message_id)
    return jsonify({
        "ok": True,
        "touch_num": touch_num,
        "message_id": message_id,
        "angle_family": plan["angle_family"],
        "angle_label": plan["angle_label"],
    })


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
        if fs_info["touch_num"] and (r.get("to_email") or "").strip():
            try:
                plan = build_followup_plan(r, fs_info["touch_num"])
                entry.update({
                    "followup_copy_ready": True,
                    "followup_angle_family": plan["angle_family"],
                    "followup_angle_label": plan["angle_label"],
                    "followup_context_source": plan["context"].get("anchor_source", ""),
                })
            except FollowupBlockedError as exc:
                entry.update({
                    "followup_copy_ready": False,
                    "followup_blocked_reason": exc.reason,
                    "followup_blocked_message": str(exc),
                })
        if fdt < now: overdue.append(entry)
        elif fdt <= today_end: today.append(entry)
        elif fdt <= week_end: this_week.append(entry)
        else: upcoming.append(entry)
    for g in (overdue,today,this_week,upcoming): g.sort(key=lambda e:e["followup_dt"])
    return jsonify({"overdue":overdue,"today":today,"this_week":this_week,"upcoming":upcoming,
                    "counts":{"overdue":len(overdue),"today":len(today),"this_week":len(this_week),"upcoming":len(upcoming),"total":len(overdue)+len(today)+len(this_week)+len(upcoming)}})

TERRITORY_INDUSTRIES = [
    "plumbing", "hvac", "electrical", "roofing", "construction",
    "landscaping", "painting", "tree_service", "cleaning", "auto",
    "flooring", "concrete", "towing", "appliance_repair", "pressure_washing",
]

@app.route("/api/territory")
def api_territory(): return jsonify({"cities":_city_planner.get_industry_matrix(TERRITORY_INDUSTRIES),"industries":TERRITORY_INDUSTRIES})

@app.route("/api/territory/leads", methods=["POST"])
def api_territory_leads():
    """
    Return leads in the queue for a given city+industry combination.
    Input:  { city, state, industry }
    Output: { ok, leads: [{business_name, to_email, city, status, sent_at, approved, final_priority_score}] }
    """
    d        = request.json or {}
    city     = (d.get("city") or "").strip().lower()
    state    = (d.get("state") or "").strip().upper()
    industry = (d.get("industry") or "").strip().lower()
    is_area  = state == "AREA"

    rows = _read_pending()
    results = []
    for r in rows:
        row_city     = (r.get("city") or "").strip().lower()
        row_state    = (r.get("state") or "").strip().upper()
        row_industry = (r.get("industry") or r.get("search_industry") or "").strip().lower()

        # Area entries match by proximity using lat/lng stored in city field
        if is_area:
            lat_str, lng_str = city.split(",", 1) if "," in city else (None, None)
            try:
                clat = float(lat_str); clng = float(lng_str)
                rlat = float(r.get("lat") or 0); rlng = float(r.get("lng") or 0)
                if not rlat and not rlng:
                    continue
                # Within ~15km of the area center
                if abs(clat - rlat) > 0.14 or abs(clng - rlng) > 0.14:
                    continue
            except Exception:
                continue
        else:
            if row_city != city:
                continue
            if state and row_state != state:
                continue

        if industry and row_industry != industry:
            continue

        results.append({
            "business_name":  r.get("business_name", ""),
            "to_email":        r.get("to_email", ""),
            "city":            r.get("city", ""),
            "state":           r.get("state", ""),
            "industry":        r.get("industry", ""),
            "sent_at":         r.get("sent_at", ""),
            "approved":        r.get("approved", ""),
            "replied":         r.get("replied", ""),
            "final_priority_score": r.get("final_priority_score", ""),
            "website":         r.get("website", ""),
            "phone":           r.get("phone", ""),
        })

    return jsonify({"ok": True, "leads": results, "total": len(results)})


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

@app.route("/api/reverse_boundary")
def api_reverse_boundary():
    """
    Reverse geocode a lat/lng to the nearest political boundary at the given zoom level.
    zoom=8  → county
    zoom=10 → city
    zoom=13 → neighborhood/suburb
    Returns same shape as /api/boundary_search.
    """
    from urllib.request import urlopen, Request as URLRequest
    import json as _json
    try:
        lat = float(request.args.get("lat", ""))
        lng = float(request.args.get("lng", ""))
        zoom = int(request.args.get("zoom", "10"))
        zoom = max(6, min(14, zoom))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "lat, lng, zoom required"}), 400
    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?lat={lat}&lon={lng}&zoom={zoom}&format=json&polygon_geojson=1"
    )
    try:
        req = URLRequest(url, headers={"User-Agent": "Copperline/1.0 reverse-boundary"})
        with urlopen(req, timeout=10) as r:
            result = _json.loads(r.read().decode())
        if "error" in result:
            return jsonify({"ok": False, "error": result["error"]}), 200
        geo = result.get("geojson", {})
        bbox = result.get("boundingbox", [])
        center_lat = center_lng = tile_count = None
        if len(bbox) == 4:
            try:
                min_lat, max_lat = float(bbox[0]), float(bbox[1])
                min_lng, max_lng = float(bbox[2]), float(bbox[3])
                center_lat = round((min_lat + max_lat) / 2, 6)
                center_lng = round((min_lng + max_lng) / 2, 6)
                lat_tiles = max(1, round((max_lat - min_lat) / 0.014))
                lng_tiles = max(1, round((max_lng - min_lng) / 0.018))
                tile_count = lat_tiles * lng_tiles
            except (ValueError, TypeError):
                pass
        address = result.get("address", {})
        short_name = (
            address.get("neighbourhood") or
            address.get("suburb") or
            address.get("city") or
            address.get("town") or
            address.get("county") or
            result.get("display_name", "").split(",")[0]
        )
        return jsonify({
            "ok": True,
            "display_name": result.get("display_name", ""),
            "short_name": short_name,
            "type": result.get("type", ""),
            "class": result.get("class", ""),
            "geojson": geo,
            "bbox": bbox,
            "center_lat": center_lat,
            "center_lng": center_lng,
            "estimated_tiles": tile_count,
            "zoom_used": zoom,
        })
    except Exception as exc:
        log.error("reverse_boundary error: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/boundary_search")
def api_boundary_search():
    """
    Proxy Nominatim boundary search so the frontend avoids CORS issues.
    Returns simplified GeoJSON polygon + bbox + tiling metadata for a city or county.
    Query params: q (place name, required), state (2-letter, appended to q if not already in q)
    """
    from urllib.request import urlopen, Request as URLRequest
    import json as _json
    q = request.args.get("q", "").strip()
    state = request.args.get("state", "").strip()
    if not q:
        return jsonify({"ok": False, "error": "q is required"}), 400
    # Append state if provided and not already in query
    search_q = q if (state.lower() in q.lower()) else f"{q} {state}".strip()
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={search_q.replace(' ', '+')}"
        "&format=json&polygon_geojson=1&limit=5"
        "&countrycodes=us"
    )
    try:
        req = URLRequest(url, headers={"User-Agent": "Copperline/1.0 boundary-search"})
        with urlopen(req, timeout=10) as r:
            results = _json.loads(r.read().decode())
        # Filter to boundary/administrative types — skip road/poi results
        filtered = [
            r for r in results
            if r.get("class") in ("boundary", "place")
            and r.get("geojson")
        ]
        if not filtered:
            return jsonify({"ok": False, "error": f"No boundary found for '{q}'"}), 200
        best = filtered[0]
        geo = best.get("geojson", {})
        bbox = best.get("boundingbox", [])  # [min_lat, max_lat, min_lng, max_lng]
        # Compute center and rough tile grid from bbox
        center_lat = center_lng = tile_count = None
        if len(bbox) == 4:
            try:
                min_lat, max_lat, min_lng, max_lng = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
                center_lat = round((min_lat + max_lat) / 2, 6)
                center_lng = round((min_lng + max_lng) / 2, 6)
                # Estimate tile count at 800m radius (0.014 deg approx)
                lat_tiles = max(1, round((max_lat - min_lat) / 0.014))
                lng_tiles = max(1, round((max_lng - min_lng) / 0.018))
                tile_count = lat_tiles * lng_tiles
            except (ValueError, TypeError):
                pass
        return jsonify({
            "ok": True,
            "display_name": best.get("display_name", ""),
            "type": best.get("type", ""),
            "osm_type": best.get("osm_type", ""),
            "geojson": geo,
            "bbox": bbox,
            "center_lat": center_lat,
            "center_lng": center_lng,
            "estimated_tiles": tile_count,
        })
    except Exception as exc:
        log.error("boundary_search error: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


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
    log.info("opt_out name=%s",name)
    # Pass 44: persist durable do_not_contact memory
    try:
        _lm.record_suppression(rows[idx], "do_not_contact",
                               note="opt-out via operator action")
    except Exception as _lm_exc:
        log.warning("lead_memory record failed on opt_out: %s", _lm_exc)
    return jsonify({"ok":True})


# ── Pass 44: Durable Lead Memory + Suppression Registry ─────────────────────

@app.route("/api/suppress_lead", methods=["POST"])
def api_suppress_lead():
    """
    Record a suppression state for a lead.

    Input:  { index, business_name, state, note? }
            state must be one of: contacted, suppressed, deleted_intentionally,
                                  do_not_contact, hold
    Output: { ok, key, current_state, business_name }

    Does NOT remove the row from the queue — use /api/delete_row for that.
    Memory persists even after the queue row is removed.
    """
    d   = request.json or {}
    idx = d.get("index")
    business_name = (d.get("business_name") or "").strip()
    state         = (d.get("state") or "").strip()
    note          = (d.get("note") or "").strip()

    _VALID = {"contacted", "suppressed", "deleted_intentionally", "do_not_contact", "hold"}
    if not state or state not in _VALID:
        return jsonify({"ok": False, "error": f"state must be one of {sorted(_VALID)}"}), 400

    if idx is not None:
        rows = _read_pending()
        if isinstance(idx, int) and 0 <= idx < len(rows):
            row = rows[idx]
            if business_name and row.get("business_name","").strip().lower() != business_name.lower():
                return jsonify({"ok": False, "error": "Row index/name mismatch"}), 409
        else:
            # idx supplied but invalid — fall back to name-only lookup
            row = {"business_name": business_name}
    else:
        row = {"business_name": business_name}

    if not business_name and not row.get("business_name"):
        return jsonify({"ok": False, "error": "business_name required"}), 400

    try:
        record = _lm.record_suppression(row, state, note=note)
        log.info("suppress_lead: key=%s state=%s biz=%s", record["key"], state, business_name)
        return jsonify({
            "ok":            True,
            "key":           record["key"],
            "current_state": record["current_state"],
            "business_name": record.get("business_name", business_name),
        })
    except Exception as exc:
        log.error("suppress_lead error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/revive_lead", methods=["POST"])
def api_revive_lead():
    """
    Remove suppression for a lead — it will appear in fresh discovery again.

    Input:  { index?, business_name, note? }
            At minimum business_name must be provided.
    Output: { ok, key, current_state, business_name }
    """
    d   = request.json or {}
    idx = d.get("index")
    business_name = (d.get("business_name") or "").strip()
    note          = (d.get("note") or "").strip()

    if not business_name:
        return jsonify({"ok": False, "error": "business_name required"}), 400

    if idx is not None:
        rows = _read_pending()
        if isinstance(idx, int) and 0 <= idx < len(rows):
            row = rows[idx]
        else:
            row = {"business_name": business_name}
    else:
        row = {"business_name": business_name}

    try:
        record = _lm.revive_lead(row, note=note)
        log.info("revive_lead: key=%s biz=%s", record["key"], business_name)
        return jsonify({
            "ok":            True,
            "key":           record["key"],
            "current_state": record["current_state"],
            "business_name": record.get("business_name", business_name),
        })
    except Exception as exc:
        log.error("revive_lead error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/lead_memory")
def api_lead_memory():
    """
    Return all durable lead memory records.

    Query params:
        suppressed_only=1  — return only currently-suppressed leads
        q=<text>           — filter by business_name substring (case-insensitive)

    Response: { ok, total, records: [...] }
    """
    suppressed_only = request.args.get("suppressed_only","").strip() in ("1","true")
    q = request.args.get("q","").strip().lower()

    try:
        all_records = _lm.get_all_records()
        records = list(all_records.values())

        if suppressed_only:
            _SUPP = {"contacted","suppressed","deleted_intentionally","do_not_contact","hold"}
            records = [r for r in records if r.get("current_state") in _SUPP]

        if q:
            records = [r for r in records if q in (r.get("business_name") or "").lower()
                       or q in (r.get("city") or "").lower()
                       or q in (r.get("website") or "").lower()]

        records.sort(key=lambda r: r.get("last_updated",""), reverse=True)

        return jsonify({"ok": True, "total": len(records), "records": records})
    except Exception as exc:
        log.error("lead_memory error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/lead_memory/check", methods=["POST"])
def api_lead_memory_check():
    """
    Check whether a specific lead is suppressed.

    Input:  { business_name, website?, phone?, place_id? }
    Output: { ok, is_suppressed, current_state, key, record? }
    """
    d   = request.json or {}
    row = {
        "business_name": (d.get("business_name") or "").strip(),
        "website":       (d.get("website") or "").strip(),
        "phone":         (d.get("phone") or "").strip(),
        "place_id":      (d.get("place_id") or "").strip(),
        "city":          (d.get("city") or "").strip(),
    }
    if not row["business_name"] and not row["website"] and not row["phone"] and not row["place_id"]:
        return jsonify({"ok": False, "error": "At least one identity field required"}), 400

    key    = _lm.lead_key(row)
    record = _lm.get_record(row)
    supp   = _lm.is_suppressed(row)
    return jsonify({
        "ok":           True,
        "is_suppressed": supp,
        "current_state": record.get("current_state") if record else None,
        "key":          key,
        "record":       record,
    })


# ── Pass 47: Lead Timeline route ──────────────────────────────────────────────

@app.route("/api/lead_timeline", methods=["POST"])
def api_lead_timeline():
    """
    Return the full event+state timeline for a lead, sorted oldest-first.

    Input:  { business_name, website?, phone?, place_id?, city? }
    Output: { ok, key, total, timeline: [{type, label, ts, detail/note, ...}] }

    Uses lead_key() identity priority: place_id > website > phone > name+city.
    Returns { ok: True, total: 0, timeline: [] } when no memory record exists.
    """
    d   = request.json or {}
    row = {
        "business_name": (d.get("business_name") or "").strip(),
        "website":       (d.get("website")       or "").strip(),
        "phone":         (d.get("phone")         or "").strip(),
        "place_id":      (d.get("place_id")      or "").strip(),
        "city":          (d.get("city")          or "").strip(),
    }
    if not any(row.values()):
        return jsonify({"ok": False, "error": "At least one identity field required"}), 400
    try:
        key      = _lm.lead_key(row)
        timeline = _lm.get_timeline(row)
        return jsonify({"ok": True, "key": key, "total": len(timeline), "timeline": timeline})
    except Exception as exc:
        log.error("lead_timeline error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


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

# ── Observation-led draft generation (Pass 36) ───────────────────────────────

@app.route("/api/update_observation", methods=["POST"])
def api_update_observation():
    """
    Persist a business_specific_observation for a queue row.

    Input:  { index, business_name, observation }
    Output: { ok, observation }

    Does not alter subject/body/send state — observation-only write.
    """

    d             = request.json or {}
    idx           = d.get("index")
    business_name = (d.get("business_name") or "").strip()
    observation   = (d.get("observation") or "").strip()

    if idx is None or not isinstance(idx, int):
        return jsonify({"ok": False, "error": "index required (int)", "blocked_reason": "invalid_request"}), 400
    if not business_name:
        return jsonify({"ok": False, "error": "business_name required", "blocked_reason": "invalid_request"}), 400
    try:
        grade = validate_observation_text(observation)
    except ObservationValidationError as exc:
        return jsonify({"ok": False, "error": exc.message, "blocked_reason": exc.reason}), 400

    rows = _read_pending()
    if not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index"}), 400

    row = rows[idx]
    if row.get("business_name", "").strip().lower() != business_name.lower():
        return jsonify({"ok": False, "error": "Row index/name mismatch — queue may have changed"}), 409

    row["business_specific_observation"] = observation
    _write_pending(rows)
    log.info("update_observation: idx=%d biz=%s", idx, business_name)
    # Pass 47: record lifecycle event (also archives obs_history — Pass 49)
    try:
        _lm.record_event(rows[idx], _lm.EVT_OBSERVATION_ADDED,
                         detail=observation[:120])
    except Exception as _e:
        log.warning("lead_memory event failed (observation_added): %s", _e)

    obs_history_count = 0
    try:
        obs_history_count = len(_lm.get_obs_history(rows[idx]))
    except Exception:
        pass
    return jsonify({
        "ok": True,
        "observation": observation,
        "grade": grade,
        "obs_history_count": obs_history_count,
    })


@app.route("/api/generate_observation_candidate", methods=["POST"])
def api_generate_observation_candidate():
    """
    Build a grounded observation candidate from safe lead context only.

    Input:  { index, business_name }
    Output:
      ready -> { ok, blocked: False, candidate_text, family, confidence, grade, rationale, evidence, source_labels }
      blocked -> { ok, blocked: True, blocked_reason, blocked_message, evidence, source_labels }
    """
    d             = request.json or {}
    idx           = d.get("index")
    business_name = (d.get("business_name") or "").strip()

    if idx is None or not isinstance(idx, int):
        return jsonify({"ok": False, "error": "index required (int)", "blocked_reason": "invalid_request"}), 400
    if not business_name:
        return jsonify({"ok": False, "error": "business_name required", "blocked_reason": "invalid_request"}), 400

    rows = _read_pending()
    if not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index", "blocked_reason": "invalid_request"}), 400

    row = rows[idx]
    if row.get("business_name", "").strip().lower() != business_name.lower():
        return jsonify({"ok": False, "error": "Row index/name mismatch", "blocked_reason": "row_mismatch"}), 409

    prospect_row = _find_matching_prospect(row, _read_prospects())
    memory_record = _lm.get_record(row)

    try:
        candidate = build_observation_candidate(
            row,
            memory_record=memory_record,
            prospect_row=prospect_row,
        )
    except ObservationCandidateBlockedError as exc:
        return jsonify({
            "ok": True,
            "blocked": True,
            "blocked_reason": exc.reason,
            "blocked_message": exc.message,
            "evidence": exc.evidence,
            "source_labels": exc.source_labels,
            "confidence": exc.confidence,
            "family": exc.family,
        })
    except ObservationValidationError as exc:
        return jsonify({
            "ok": True,
            "blocked": True,
            "blocked_reason": exc.reason,
            "blocked_message": exc.message,
            "evidence": [],
            "source_labels": ["candidate_validation"],
        })
    except Exception as exc:
        log.warning("api_generate_observation_candidate error: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({
        "ok": True,
        "blocked": False,
        **candidate,
    })


@app.route("/api/refresh_observation_evidence", methods=["POST"])
def api_refresh_observation_evidence():
    """
    Refresh website/contact evidence for one lead, then retry observation candidate generation.

    Input:  { index, business_name }
    Output:
      ready -> { ok, blocked: False, candidate_text..., refresh: {...} }
      blocked -> { ok, blocked: True, blocked_reason, blocked_message, refresh: {...} }

    Single-lead only. Does not auto-save the observation or regenerate/send any draft.
    """
    d             = request.json or {}
    idx           = d.get("index")
    business_name = (d.get("business_name") or "").strip()

    if idx is None or not isinstance(idx, int):
        return jsonify({"ok": False, "error": "index required (int)", "blocked_reason": "invalid_request"}), 400
    if not business_name:
        return jsonify({"ok": False, "error": "business_name required", "blocked_reason": "invalid_request"}), 400

    rows = _read_pending()
    if not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index", "blocked_reason": "invalid_request"}), 400

    row = rows[idx]
    if row.get("business_name", "").strip().lower() != business_name.lower():
        return jsonify({"ok": False, "error": "Row index/name mismatch", "blocked_reason": "row_mismatch"}), 409

    memory_record = _lm.get_record(row)
    prospects, prospect_fieldnames = _read_prospects_with_fieldnames()
    prospect_idx = _find_matching_prospect_index(row, prospects)
    prospect_row = prospects[prospect_idx] if prospect_idx is not None else None

    try:
        refresh = refresh_observation_evidence(row, prospect_row=prospect_row)
    except Exception as exc:
        log.warning("api_refresh_observation_evidence error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

    row_updates = refresh.get("row_updates") or {}
    prospect_updates = refresh.get("prospect_updates") or {}

    for key, value in row_updates.items():
        row[key] = value
    if row_updates:
        _write_pending(rows)

    refreshed_prospect = prospect_row
    if prospect_idx is not None and prospect_updates:
        for key, value in prospect_updates.items():
            prospects[prospect_idx][key] = value
        _write_prospects(prospects, prospect_fieldnames)
        refreshed_prospect = prospects[prospect_idx]

    refresh_payload = {
        "summary": refresh.get("summary") or "",
        "website": refresh.get("website") or "",
        "website_source": refresh.get("website_source") or "",
        "evidence": refresh.get("evidence") or [],
        "source_labels": refresh.get("source_labels") or [],
        "updated_fields": refresh.get("updated_fields") or [],
        "prospect_updated_fields": refresh.get("prospect_updated_fields") or [],
        "row_updates": row_updates,
        "blocked": bool(refresh.get("blocked")),
        "blocked_reason": refresh.get("blocked_reason") or "",
        "blocked_message": refresh.get("blocked_message") or "",
    }

    try:
        candidate = build_observation_candidate(
            row,
            memory_record=memory_record,
            prospect_row=refreshed_prospect,
        )
    except ObservationCandidateBlockedError as exc:
        blocked_reason = exc.reason
        blocked_message = exc.message
        if refresh.get("blocked"):
            blocked_reason = refresh.get("blocked_reason") or blocked_reason
            blocked_message = refresh.get("blocked_message") or blocked_message
        return jsonify({
            "ok": True,
            "blocked": True,
            "blocked_reason": blocked_reason,
            "blocked_message": blocked_message,
            "evidence": (refresh.get("evidence") or []) + (exc.evidence or []),
            "source_labels": list(dict.fromkeys((refresh.get("source_labels") or []) + (exc.source_labels or []))),
            "confidence": exc.confidence,
            "family": exc.family,
            "refresh": refresh_payload,
        })
    except ObservationValidationError as exc:
        blocked_reason = refresh.get("blocked_reason") or exc.reason
        blocked_message = refresh.get("blocked_message") or exc.message
        return jsonify({
            "ok": True,
            "blocked": True,
            "blocked_reason": blocked_reason,
            "blocked_message": blocked_message,
            "evidence": refresh.get("evidence") or [],
            "source_labels": refresh.get("source_labels") or [],
            "refresh": refresh_payload,
        })
    except Exception as exc:
        log.warning("api_refresh_observation_evidence candidate error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc), "refresh": refresh_payload}), 500

    return jsonify({
        "ok": True,
        "blocked": False,
        **{
            **candidate,
            "evidence": (refresh.get("evidence") or []) + (candidate.get("evidence") or []),
            "source_labels": list(dict.fromkeys((refresh.get("source_labels") or []) + (candidate.get("source_labels") or []))),
        },
        "refresh": refresh_payload,
    })


@app.route("/api/obs_grade", methods=["POST"])
def api_obs_grade():
    """
    Grade an observation text without persisting it.

    Input:  { observation }
    Output: { ok, grade: { grade, label, tone, message, chars, words } }

    Safe to call on every keystroke — reads nothing, writes nothing.
    """
    d   = request.json or {}
    obs = (d.get("observation") or "").strip()
    try:
        grade = _lm.grade_observation(obs)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "grade": grade})


@app.route("/api/obs_history", methods=["POST"])
def api_obs_history():
    """
    Return the observation revision history for a lead.

    Input:  { business_name, website?, phone?, place_id?, city? }
    Output: { ok, key, obs_history: [...], current_observation, grade }

    obs_history entries: [ { ts, prior, text }, ... ]  oldest-first.
    grade is computed from current_observation (or empty-string grade if none).
    """
    d = request.json or {}
    row = {
        "business_name": (d.get("business_name") or "").strip(),
        "website":       (d.get("website")       or "").strip(),
        "phone":         (d.get("phone")          or "").strip(),
        "place_id":      (d.get("place_id")       or "").strip(),
        "city":          (d.get("city")            or "").strip(),
    }
    if not row["business_name"] and not row["website"] and not row["phone"] and not row["place_id"]:
        return jsonify({"ok": False, "error": "At least one identity field required"}), 400

    try:
        obs_history = _lm.get_obs_history(row)
        record      = _lm.get_record(row)
        key         = _lm.lead_key(row)
        current_obs = (record or {}).get("current_observation", "")
        # Fall back to last history entry if current_observation not yet set
        if not current_obs and obs_history:
            current_obs = obs_history[-1].get("text", "")
        grade = _lm.grade_observation(current_obs)
    except Exception as exc:
        log.warning("api_obs_history error: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({
        "ok":                  True,
        "key":                 key,
        "current_observation": current_obs,
        "obs_history":         obs_history,
        "grade":               grade,
    })


@app.route("/api/bulk_regenerate", methods=["POST"])
def api_bulk_regenerate():
    """
    Regenerate drafts for all stale queue rows (or a supplied list of indices).
    For each row: generate observation candidate → apply → regenerate draft.
    Skips rows that are sent, do-not-contact, or blocked from candidate generation.

    Input:  { indices?: [int, ...], mode?: "stale" | "all_unsent" }
            If indices not provided, defaults to mode="stale" (all rows needing draft refresh).
    Output: { ok, total, regenerated, skipped, errors, results: [{index, name, status}] }
    """
    from outreach.email_draft_agent import (
        draft_email, draft_social_messages,
        ObservationMissingError, DraftInvalidError,
    )
    from outreach.observation_candidate_agent import (
        build_observation_candidate, ObservationCandidateBlockedError,
    )

    d       = request.json or {}
    mode    = d.get("mode", "stale")
    indices = d.get("indices")  # optional explicit list

    rows = _read_pending()
    prospect_rows = _read_prospects()

    # Build target list
    if indices is not None:
        targets = [(i, rows[i]) for i in indices if 0 <= i < len(rows)]
    elif mode == "all_unsent":
        targets = [(i, r) for i, r in enumerate(rows) if not r.get("sent_at") and r.get("to_email")]
    else:  # stale — needs draft refresh
        def _needs_refresh(row):
            if row.get("sent_at"): return False
            if row.get("do_not_contact") == "true": return False
            is_stale = str(row.get("draft_version", "")).strip() != "v18"
            has_no_obs = not (row.get("business_specific_observation") or "").strip()
            has_subject = bool((row.get("subject") or "").strip())
            return is_stale or (has_subject and has_no_obs)
        targets = [(i, r) for i, r in enumerate(rows) if _needs_refresh(r)]

    results = []
    regenerated = 0
    skipped = 0
    errors = 0

    for idx, row in targets:
        name = (row.get("business_name") or "").strip()
        try:
            # Step 1: get or use existing observation
            obs = (row.get("business_specific_observation") or "").strip()
            if len(obs) < 10:
                prospect_row = _find_matching_prospect(row, prospect_rows)
                memory_record = _lm.get_record(row)
                try:
                    candidate = build_observation_candidate(
                        row, memory_record=memory_record, prospect_row=prospect_row,
                    )
                    # Handle both dataclass and dict return shapes
                    ctext = (
                        candidate.candidate_text if hasattr(candidate, 'candidate_text')
                        else candidate.get('candidate_text', '')
                    )
                    obs = (ctext or '').strip()
                    if obs:
                        rows[idx]["business_specific_observation"] = obs
                        rows[idx]["obs_source"] = "auto_bulk"
                except ObservationCandidateBlockedError:
                    obs = ""  # Fallback draft will handle it

            # Step 2: regenerate draft (tuple return: subject, body)
            new_subject, new_body = draft_email(rows[idx], 3, observation=obs or None)
            new_dm, _, _ = draft_social_messages(rows[idx], new_body, observation=obs or None)

            rows[idx]["subject"]                   = new_subject
            rows[idx]["body"]                      = new_body
            rows[idx]["facebook_dm_draft"]         = new_dm
            rows[idx]["instagram_dm_draft"]        = new_dm
            rows[idx]["contact_form_message"]      = new_dm
            rows[idx]["social_dm_text"]            = new_dm
            rows[idx]["draft_version"]             = "v18"
            rows[idx]["draft_type"]                = "observation" if obs else "industry_fallback"
            rows[idx]["draft_regenerated_at"]      = __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

            results.append({"index": idx, "name": name, "status": "ok"})
            regenerated += 1

        except (ObservationMissingError, DraftInvalidError) as exc:
            results.append({"index": idx, "name": name, "status": f"blocked: {exc}"})
            errors += 1
        except Exception as exc:
            log.error("bulk_regenerate row %d %s: %s", idx, name, exc, exc_info=True)
            results.append({"index": idx, "name": name, "status": f"error: {exc}"})
            errors += 1

    # Write all changes in one pass
    _write_pending(rows)

    log.info("bulk_regenerate: total=%d regenerated=%d skipped=%d errors=%d",
             len(targets), regenerated, skipped, errors)
    return jsonify({
        "ok": True,
        "total": len(targets),
        "regenerated": regenerated,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    })


@app.route("/api/regenerate_draft", methods=["POST"])
def api_regenerate_draft():
    """
    Regenerate first-touch email + social drafts for a queue row using the stored observation.

    Input:  { index, business_name }
            Optionally: { observation } to set-and-regenerate in one step.
    Output: { ok, subject, body, dm_draft, observation }

    Generation is blocked if observation is missing or invalid.
    Returns a structured error with reason if blocked.
    """
    from outreach.email_draft_agent import (
        draft_email,
        draft_social_messages,
        ObservationMissingError,
        DraftInvalidError,
    )

    d             = request.json or {}
    idx           = d.get("index")
    business_name = (d.get("business_name") or "").strip()
    obs_override  = (d.get("observation") or "").strip() or None

    if idx is None or not isinstance(idx, int):
        return jsonify({"ok": False, "error": "index required (int)", "blocked": True}), 400
    if not business_name:
        return jsonify({"ok": False, "error": "business_name required", "blocked": True}), 400

    rows = _read_pending()
    if not (0 <= idx < len(rows)):
        return jsonify({"ok": False, "error": "Invalid index", "blocked": True}), 400

    row = rows[idx]
    if row.get("business_name", "").strip().lower() != business_name.lower():
        return jsonify({"ok": False, "error": "Row index/name mismatch", "blocked": True}), 409

    # Resolve observation: override > stored field
    observation = obs_override or row.get("business_specific_observation", "").strip() or None

    if not observation:
        return jsonify({
            "ok": False,
            "blocked": True,
            "blocked_reason": "observation_missing",
            "error": (
                "Draft generation blocked: no observation on file for this business. "
                "Add a specific business observation first."
            ),
        }), 400

    try:
        validate_observation_text(observation)
    except ObservationValidationError as exc:
        return jsonify({
            "ok": False,
            "blocked": True,
            "blocked_reason": exc.reason,
            "error": exc.message,
        }), 400

    # Persist override immediately if one was passed
    if obs_override:
        row["business_specific_observation"] = obs_override

    try:
        subject, body = draft_email(row, int(row.get("final_priority_score") or 0), observation=observation)
        dm, _, _ = draft_social_messages(row, body, observation=observation)
    except ObservationMissingError as exc:
        return jsonify({
            "ok": False,
            "blocked": True,
            "blocked_reason": "observation_missing",
            "error": str(exc),
        }), 400
    except DraftInvalidError as exc:
        return jsonify({
            "ok": False,
            "blocked": False,
            "blocked_reason": "draft_invalid",
            "error": str(exc),
        }), 422
    except Exception as exc:
        log.error("regenerate_draft error: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500

    # Write regenerated drafts back to queue
    row["subject"]              = subject
    row["body"]                 = body
    row["facebook_dm_draft"]    = dm
    row["instagram_dm_draft"]   = dm
    row["contact_form_message"] = dm
    row["social_dm_text"]       = dm
    row["draft_version"]        = "v9"
    _write_pending(rows)

    log.info("regenerate_draft: idx=%d biz=%s", idx, business_name)
    # Pass 47: record lifecycle event
    try:
        _lm.record_event(rows[idx], _lm.EVT_DRAFT_REGENERATED,
                         detail=f"obs={observation[:80]}")
    except Exception as _e:
        log.warning("lead_memory event failed (draft_regenerated): %s", _e)
    return jsonify({
        "ok":          True,
        "subject":     subject,
        "body":        body,
        "dm_draft":    dm,
        "observation": observation,
    })


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


@app.before_request
def _start_scheduler_for_requests() -> None:
    if os.getenv("COPPERLINE_DISABLE_SCHEDULER", "").strip().lower() in {"1", "true", "yes"}:
        return
    _start_scheduler_once()


def _running_from_reloader() -> bool:
    try:
        from werkzeug.serving import is_running_from_reloader
        return bool(is_running_from_reloader())
    except Exception:
        return False


if os.getenv("COPPERLINE_DISABLE_SCHEDULER", "").strip().lower() not in {"1", "true", "yes"} and _running_from_reloader():
    _start_scheduler_once()


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
