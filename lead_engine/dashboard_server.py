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
from send.email_sender_agent import process_pending_emails, is_real_send, send_next_due_email, CSV_WRITE_LOCK, _is_send_eligible
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
    if send_after_raw:
        try:
            send_after_due = now_local >= _datetime.fromisoformat(send_after_raw)
        except ValueError:
            send_after_parse_error = True

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
    }
    return jsonify(payload)

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
    from intelligence.observation_candidate_agent import (
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
                # Try to generate observation candidate
                prospect_row = _find_matching_prospect(row, prospect_rows)
                memory_record = _lm.get_record(row)
                try:
                    candidate = build_observation_candidate(
                        row, memory_record=memory_record, prospect_row=prospect_row,
                    )
                    obs = candidate.candidate_text.strip()
                    if obs:
                        rows[idx]["business_specific_observation"] = obs
                        rows[idx]["obs_source"] = "auto_bulk"
                except ObservationCandidateBlockedError:
                    # No observation available — fallback draft will handle it
                    obs = ""

            # Step 2: regenerate draft
            prospect_row = _find_matching_prospect(row, prospect_rows)
            new_email    = draft_email(rows[idx], obs)
            new_social   = draft_social_messages(rows[idx], obs)

            rows[idx]["subject"]                   = new_email["subject"]
            rows[idx]["body"]                      = new_email["body"]
            rows[idx]["facebook_dm_draft"]         = new_social.get("facebook_dm", "")
            rows[idx]["instagram_dm_draft"]        = new_social.get("instagram_dm", "")
            rows[idx]["contact_form_message"]      = new_social.get("contact_form_message", "")
            rows[idx]["social_dm_text"]            = new_social.get("facebook_dm", "")
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
