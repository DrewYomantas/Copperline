"""
lead_memory.py
Durable Lead Memory + Suppression Registry — Pass 44
Lead Timeline / Lifecycle Event Spine — Pass 47

Persists suppression/contact state and lifecycle event history for leads
independently from the queue CSV. Deleting a queue row does NOT erase this memory.

Storage: lead_engine/data/lead_memory.json

Each lead record contains a single history[] list. Two entry types coexist:

  type "state"  — state-transition entries written by record_suppression().
                  These update current_state on the record.

  type "event"  — lifecycle event entries written by record_event().
                  These do NOT update current_state. They add narrative detail.

Event types (EVT_*):
  EVT_DRAFTED           — a draft was created for this lead
  EVT_OBSERVATION_ADDED — a business-specific observation was saved
  EVT_DRAFT_REGENERATED — draft was regenerated using an observation
  EVT_REPLIED           — lead replied to outreach
  EVT_NOTE_ADDED        — operator added a conversation note
  EVT_FOLLOWUP_SENT     — a follow-up message was sent
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

BASE_DIR   = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "data" / "lead_memory.json"

_SUPPRESSED_STATES = {"contacted", "suppressed", "deleted_intentionally", "do_not_contact", "hold"}
_ALL_STATES        = _SUPPRESSED_STATES | {"revived"}

_lock = Lock()


# ---------------------------------------------------------------------------
# Identity key helpers  (mirrors JS _leadKey logic)
# ---------------------------------------------------------------------------

_BLANK = {"", "unknown", "n/a", "na", "none", "null", "-", "--"}
_PUNCT = re.compile(r"[^\w\s]")
_NAME_NOISE = {
    "llc", "inc", "corp", "co", "ltd", "company", "companies",
    "plumbing", "plumber", "sewer", "drain", "heating", "cooling",
    "hvac", "electric", "electrical", "locksmith", "roofing",
    "services", "service", "solutions", "group", "the", "and",
}


def _norm(v: str | None) -> str:
    t = (v or "").strip()
    return "" if t.lower() in _BLANK else t


def _norm_website(w: str | None) -> str:
    raw = _norm(w)
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        from urllib.parse import urlparse
        host = urlparse(raw).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip("/")


def _norm_phone(p: str | None) -> str:
    digits = re.sub(r"\D", "", _norm(p) or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) >= 7 else ""


def _norm_name(n: str | None) -> str:
    raw = _PUNCT.sub(" ", (_norm(n) or "").lower())
    tokens = [t for t in raw.split() if t not in _NAME_NOISE]
    return " ".join(tokens).strip()


def lead_key(row: dict) -> str:
    """
    Compute the strongest available lead identity key from a queue row or
    a discovery biz object.  Same priority as frontend _leadKey().
    """
    # place_id is the most stable when present (Google Places canonical ID)
    pid = _norm(row.get("place_id"))
    if pid:
        return f"pid:{pid}"

    w = _norm_website(row.get("website") or row.get("url") or "")
    if w:
        return f"web:{w}"

    ph = _norm_phone(row.get("phone") or "")
    if ph:
        return f"ph:{ph}"

    name = _norm_name(row.get("business_name") or row.get("name") or "")
    city = (_norm(row.get("city")) or "").lower()
    return f"nc:{name}|{city}"


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not MEMORY_FILE.exists():
        return {}
    try:
        with MEMORY_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = MEMORY_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(MEMORY_FILE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_suppression(
    row: dict,
    state: str,
    *,
    note: str = "",
    operator: str = "operator",
) -> dict:
    """
    Add a suppression/state entry for a lead.

    Args:
        row:      Queue row or biz object (needs business_name/city at minimum).
        state:    One of _ALL_STATES.
        note:     Optional free-text note.
        operator: Who performed the action (default "operator").

    Returns the full memory record for this lead.
    """
    if state not in _ALL_STATES:
        raise ValueError(f"Invalid state {state!r}. Must be one of {sorted(_ALL_STATES)}")

    key = lead_key(row)
    entry = {
        "state":     state,
        "ts":        _now_iso(),
        "operator":  operator,
        "note":      note,
        "business_name": _norm(row.get("business_name") or row.get("name") or ""),
        "city":      _norm(row.get("city") or ""),
        "website":   _norm(row.get("website") or ""),
        "phone":     _norm(row.get("phone") or ""),
    }

    with _lock:
        data = _load()
        record = data.setdefault(key, {"key": key, "history": []})
        record["history"].append(entry)
        record["current_state"]   = state
        record["last_updated"]    = entry["ts"]
        record["business_name"]   = entry["business_name"] or record.get("business_name", "")
        record["city"]            = entry["city"] or record.get("city", "")
        record["website"]         = entry["website"] or record.get("website", "")
        record["phone"]           = entry["phone"] or record.get("phone", "")
        _save(data)
        return record


def revive_lead(row: dict, *, note: str = "", operator: str = "operator") -> dict:
    """
    Remove suppression for a lead.  Adds a 'revived' entry to history.
    The lead will pass discovery filters again after this call.
    """
    return record_suppression(row, "revived", note=note, operator=operator)


def is_suppressed(row: dict) -> bool:
    """
    Return True if the lead's current memory state is a suppression state.
    Returns False if the lead has no memory record, or if current_state is 'revived'.
    """
    key = lead_key(row)
    with _lock:
        data = _load()
    record = data.get(key)
    if not record:
        return False
    return record.get("current_state") in _SUPPRESSED_STATES


def get_record(row: dict) -> Optional[dict]:
    """Return the full memory record for a lead, or None if not in memory."""
    key = lead_key(row)
    with _lock:
        data = _load()
    return data.get(key)


def get_all_records() -> dict:
    """Return the full memory dict keyed by lead_key."""
    with _lock:
        return _load()


def get_suppressed_keys() -> set:
    """
    Return the set of lead keys that are currently suppressed.
    Used for fast O(1) filtering during discovery.
    """
    with _lock:
        data = _load()
    return {
        k for k, v in data.items()
        if v.get("current_state") in _SUPPRESSED_STATES
    }


def suppressed_identity_sets() -> tuple[set, set, set]:
    """
    Return three sets for fast multi-signal discovery filtering:
        (suppressed_websites, suppressed_phones, suppressed_name_city_pairs)

    These are extracted from all suppressed records so the caller can
    cross-check individual signal fields without recomputing keys.
    """
    with _lock:
        data = _load()

    websites, phones, name_cities = set(), set(), set()
    for v in data.values():
        if v.get("current_state") not in _SUPPRESSED_STATES:
            continue
        key = v.get("key", "")
        if key.startswith("web:"):
            websites.add(key[4:])
        elif key.startswith("ph:"):
            phones.add(key[3:])
        elif key.startswith("nc:"):
            name_cities.add(key[3:])
        # place_id keys — also add to a web-style check won't help, but
        # we still check via lead_key() lookup which covers pid: keys
    return websites, phones, name_cities


# ---------------------------------------------------------------------------
# Pass 47: Lifecycle event spine
# ---------------------------------------------------------------------------

# Event type constants — use these instead of bare strings at call sites.
EVT_DRAFTED           = "drafted"
EVT_OBSERVATION_ADDED = "observation_added"
EVT_DRAFT_REGENERATED = "draft_regenerated"
EVT_REPLIED           = "replied"
EVT_NOTE_ADDED        = "note_added"
EVT_FOLLOWUP_SENT     = "followup_sent"

_ALL_EVENT_TYPES = {
    EVT_DRAFTED, EVT_OBSERVATION_ADDED, EVT_DRAFT_REGENERATED,
    EVT_REPLIED, EVT_NOTE_ADDED, EVT_FOLLOWUP_SENT,
}

# Human-readable labels for UI rendering
_EVENT_LABELS = {
    EVT_DRAFTED:           "Draft created",
    EVT_OBSERVATION_ADDED: "Observation saved",
    EVT_DRAFT_REGENERATED: "Draft regenerated",
    EVT_REPLIED:           "Replied",
    EVT_NOTE_ADDED:        "Note added",
    EVT_FOLLOWUP_SENT:     "Follow-up sent",
}

# Labels for state-transition entries (used in timeline rendering)
_STATE_LABELS = {
    "contacted":             "Contacted",
    "suppressed":            "Suppressed",
    "deleted_intentionally": "Removed from queue",
    "do_not_contact":        "Opted out",
    "hold":                  "Put on hold",
    "revived":               "Revived",
}


def record_event(
    row: dict,
    event_type: str,
    *,
    detail: str = "",
    operator: str = "operator",
) -> Optional[dict]:
    """
    Append a lifecycle event to a lead's history without changing current_state.

    Creates the lead record if it doesn't exist yet (identity-only record with
    no current_state set, so is_suppressed() still returns False for it).

    Args:
        row:        Queue row or biz object.
        event_type: One of the EVT_* constants.
        detail:     Optional free-text context (observation snippet, note excerpt, etc.)
        operator:   Who triggered the event.

    Returns the updated memory record, or None if the write fails silently.
    """
    if event_type not in _ALL_EVENT_TYPES:
        raise ValueError(f"Unknown event_type {event_type!r}. Use EVT_* constants.")

    key = lead_key(row)
    entry = {
        "type":        "event",
        "event_type":  event_type,
        "label":       _EVENT_LABELS.get(event_type, event_type),
        "ts":          _now_iso(),
        "operator":    operator,
        "detail":      detail,
        "business_name": _norm(row.get("business_name") or row.get("name") or ""),
        "city":        _norm(row.get("city") or ""),
    }

    try:
        with _lock:
            data = _load()
            record = data.setdefault(key, {
                "key":          key,
                "history":      [],
                "business_name": _norm(row.get("business_name") or row.get("name") or ""),
                "city":         _norm(row.get("city") or ""),
                "website":      _norm(row.get("website") or ""),
                "phone":        _norm(row.get("phone") or ""),
            })
            record["history"].append(entry)
            record["last_updated"] = entry["ts"]
            # Refresh identity fields if richer data is now available
            record["business_name"] = entry["business_name"] or record.get("business_name", "")
            record["city"]          = entry["city"] or record.get("city", "")
            record["website"]       = _norm(row.get("website") or "") or record.get("website", "")
            record["phone"]         = _norm(row.get("phone") or "") or record.get("phone", "")
            _save(data)
            return record
    except Exception:
        return None


def get_timeline(row: dict) -> list:
    """
    Return the full event+state history for a lead, sorted oldest-first.

    Each entry is the raw dict from history[] with an added 'label' field
    for display, and a normalized 'type' field ('state' or 'event').

    State-transition entries written before Pass 47 lack an explicit 'type'
    field — these are back-filled as 'state' here so callers don't need to
    handle the legacy shape.

    Returns [] if the lead has no memory record.
    """
    record = get_record(row)
    if not record:
        return []

    timeline = []
    for entry in record.get("history", []):
        e = dict(entry)
        # Back-fill type for pre-Pass-47 state-transition entries
        if "type" not in e:
            e["type"] = "state"
        # Back-fill label
        if "label" not in e:
            if e["type"] == "state":
                e["label"] = _STATE_LABELS.get(e.get("state", ""), e.get("state", ""))
            else:
                e["label"] = _EVENT_LABELS.get(e.get("event_type", ""), e.get("event_type", ""))
        timeline.append(e)

    # Sort oldest-first by timestamp
    timeline.sort(key=lambda e: e.get("ts", ""))
    return timeline
