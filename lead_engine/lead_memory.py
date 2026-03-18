"""
lead_memory.py
Durable Lead Memory + Suppression Registry — Pass 44

Persists suppression/contact state for leads independently from the queue CSV.
Deleting a queue row does NOT erase this memory.

Storage: lead_engine/data/lead_memory.json  (gitignored via .gitignore pattern)

Lead identity key priority (mirrors _leadKey in index.html):
  1. Normalized website domain  (most stable, ~90% coverage)
  2. Digits-only phone           (~99% coverage)
  3. normalized_name|normalized_city  (100% fallback)

Suppression states:
  contacted            — outreach was sent (at least one real send)
  suppressed           — operator explicitly suppressed without a more specific reason
  deleted_intentionally — row was removed from queue by the operator
  do_not_contact       — business must not be reached (opt-out or explicit block)
  hold                 — not now, revisit later
  revived              — was suppressed but operator intentionally un-suppressed

Revived records retain their history. The most-recent entry determines whether
a lead is currently suppressed.
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
