from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import urlparse

from discovery.prospect_discovery_agent import (
    dedupe_key_for_prospect,
    load_prospects_from_csv,
    clean_website_for_key,
)
from intelligence.website_scan_agent import scan_website, generate_lead_insight
from outreach.email_draft_agent import draft_email, draft_social_messages, DRAFT_VERSION
from scoring.opportunity_scoring_agent import score_opportunity, compute_numeric_score
from send.email_sender_agent import count_send_eligible_rows, is_real_send
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Placeholder patterns — body containing these should never be auto-approved
# ---------------------------------------------------------------------------
_PLACEHOLDER_RE = re.compile(
    r"\{[a-z_]+\}|PLACEHOLDER|TODO|FIXME|<INSERT|lorem ipsum",
    re.IGNORECASE
)

PENDING_COLUMNS = [
    "business_name", "city", "state", "website", "phone", "contact_method",
    "industry", "to_email", "subject", "body", "approved", "sent_at",
    "approval_reason",          # NEW: "safe_autopilot" | "manual" | ""
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

BASE_DIR              = Path(__file__).resolve().parent
DEFAULT_PROSPECTS_CSV = BASE_DIR / "data"  / "prospects.csv"
DEFAULT_PENDING_CSV   = BASE_DIR / "queue" / "pending_emails.csv"

# ---------------------------------------------------------------------------
# Email validation helpers (local — mirrors queue_integrity logic)
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_ASSET_FRAGS = (".webp", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".css", ".js")


def _is_valid_email(email: str) -> bool:
    if not email:
        return False
    e = email.strip().lower()
    if any(f in e for f in _ASSET_FRAGS):
        return False
    return bool(_EMAIL_RE.match(e))


def _domain_looks_valid(website: str) -> bool:
    """Return True if the website has a real-looking domain (not blank, not gstatic, etc.)."""
    if not website:
        return True   # no website is OK — not an invalid domain
    try:
        parsed = urlparse(website)
        host = parsed.netloc.lower().replace("www.", "")
        if not host or "." not in host:
            return False
        bad = {"gstatic.com", "googleusercontent.com", "example.com", "localhost"}
        return not any(host.endswith(b) for b in bad)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Phase A — Safe Autopilot
# ---------------------------------------------------------------------------

def safe_autopilot_eligible(row: Dict[str, str]) -> bool:
    """
    Return True if a newly-drafted row passes ALL autopilot safety checks.
    If True, the caller sets approved="true" and approval_reason="safe_autopilot".

    Checks (all must pass):
      1. to_email present and format-valid (not asset filename)
      2. No prior real send (sent_at AND message_id both empty)
      3. domain looks valid (not gstatic / googleusercontent / etc.)
      4. subject present and non-empty
      5. body present, no placeholder tokens, reasonable length (20–400 words)
      6. Required fields present (business_name, city, state)
      7. do_not_contact is not "true"
    """
    # 1. Valid email
    email = (row.get("to_email") or "").strip()
    if not _is_valid_email(email):
        return False

    # 2. No prior real send
    if (row.get("sent_at") or "").strip() or (row.get("message_id") or "").strip():
        return False

    # 3. Domain valid
    if not _domain_looks_valid(row.get("website", "")):
        return False

    # 4. Subject
    if not (row.get("subject") or "").strip():
        return False

    # 5. Body — placeholder check and word count
    body = (row.get("body") or "").strip()
    if not body:
        return False
    if _PLACEHOLDER_RE.search(body):
        return False
    word_count = len(body.split())
    if word_count < 20 or word_count > 400:
        return False

    # 6. Required fields
    if not (row.get("business_name", "").strip() and
            row.get("city", "").strip() and
            row.get("state", "").strip()):
        return False

    # 7. Not opted out
    if row.get("do_not_contact", "").strip().lower() == "true":
        return False

    return True


def _read_pending_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        return [{col: row.get(col, "") for col in PENDING_COLUMNS} for row in reader]


def _write_pending_rows(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_rows = [{col: row.get(col, "") for col in PENDING_COLUMNS} for row in rows]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PENDING_COLUMNS)
        writer.writeheader()
        writer.writerows(safe_rows)


def _is_scannable_website(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run lead_engine CSV-to-draft pipeline.")
    parser.add_argument("--input", default=str(DEFAULT_PROSPECTS_CSV))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-scan", action="store_true")
    return parser.parse_args()


def _update_prospect_status(input_path: Path, drafted_names: Set[str]) -> None:
    if not input_path.exists() or not drafted_names:
        return
    with input_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader     = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows       = list(reader)
    # Strip None keys from fieldnames (can appear when a row has more columns
    # than the header — overflow columns are keyed as None by csv.DictReader).
    fieldnames = [c for c in fieldnames if c is not None]
    if "status" not in fieldnames:
        fieldnames.append("status")
    for row in rows:
        # Drop None key from any row dict before writing
        row.pop(None, None)
        name = row.get("business_name", "").strip().lower()
        if name in drafted_names and row.get("status", "") == "new":
            row["status"] = "drafted"
    with input_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _build_queue_dedupe_sets(
    pending_rows: List[Dict[str, str]]
) -> Tuple[Set, Set, Set]:
    """Build (dedupe_keys, email_set, domain_set) from existing queue rows."""
    dedupe_keys: Set[Tuple[str, str]] = set()
    email_set:   Set[str] = set()
    domain_set:  Set[str] = set()
    for row in pending_rows:
        dedupe_keys.add(dedupe_key_for_prospect(row))
        email = (row.get("to_email") or "").strip().lower()
        if email:
            email_set.add(email)
        domain = clean_website_for_key(row.get("website", ""))
        if domain:
            domain_set.add(domain)
    return dedupe_keys, email_set, domain_set


def run(input_csv: str | Path = DEFAULT_PROSPECTS_CSV, limit: int = 0, skip_scan: bool = False) -> None:
    input_path = Path(input_csv)
    prospects  = load_prospects_from_csv(input_path)
    if limit > 0:
        prospects = prospects[:limit]

    prospects = [p for p in prospects if p.get("status", "new") in ("", "new")]
    directory_skipped = sum(1 for p in prospects if p.get("contactability","") == "directory_or_ambiguous")
    prospects = [p for p in prospects if p.get("contactability","") != "directory_or_ambiguous"]

    pending_rows = _read_pending_rows(DEFAULT_PENDING_CSV)
    existing_keys, existing_emails, existing_domains = _build_queue_dedupe_sets(pending_rows)

    drafted = 0
    autopilot_approved = 0
    skipped = 0
    skipped_duplicate = 0
    websites_scanned  = 0
    drafted_names: Set[str] = set()
    contactability_counts: Dict[str, int] = {}

    for prospect in prospects:
        key = dedupe_key_for_prospect(prospect)
        if not key[0]:
            skipped += 1
            continue
        if key in existing_keys:
            skipped_duplicate += 1
            continue
        prospect_domain = clean_website_for_key(prospect.get("website", ""))
        if prospect_domain and prospect_domain in existing_domains:
            print(f"  [domain-dedupe] skip {prospect.get('business_name','')} — domain already in queue")
            skipped_duplicate += 1
            continue
        prospect_email = (prospect.get("to_email") or "").strip().lower()
        if prospect_email and prospect_email in existing_emails:
            print(f"  [email-dedupe] skip {prospect.get('business_name','')} — email already in queue")
            skipped_duplicate += 1
            continue

        website = prospect.get("website", "")
        scan_result = {"has_contact_form": False, "has_chat_widget": False,
                       "has_online_booking_keywords": False, "has_email_visible": False}

        already_scanned = bool((prospect.get("automation_opportunity") or "").strip())
        if not skip_scan and not already_scanned and _is_scannable_website(website):
            websites_scanned += 1
            scan_result = scan_website(website)
        elif already_scanned:
            scan_result["automation_opportunity"] = prospect.get("automation_opportunity", "unknown")

        final_priority_score, scoring_reason = score_opportunity(prospect, scan_result)

        try:
            subject, body = draft_email(prospect, final_priority_score)
        except ValueError:
            skipped += 1
            continue

        try:
            fb_draft, ig_draft, form_msg = draft_social_messages(prospect, body)
        except Exception:
            fb_draft, ig_draft, form_msg = "", "", ""

        try:
            insight_sentence, insight_signals = generate_lead_insight(scan_result)
        except Exception:
            insight_sentence, insight_signals = "", []

        numeric_score = compute_numeric_score({
            **prospect,
            "to_email":        prospect.get("to_email", "").strip(),
            "contact_form_url": prospect.get("contact_form_url", "").strip(),
            "facebook_url":    prospect.get("facebook_url", "").strip(),
            "instagram_url":   prospect.get("instagram_url", "").strip(),
            "automation_opportunity": scan_result.get("automation_opportunity", "unknown"),
        })

        to_email = prospect.get("to_email", "").strip()
        c_label  = prospect.get("contactability", "unknown")
        contactability_counts[c_label] = contactability_counts.get(c_label, 0) + 1

        # ── Build the new row ─────────────────────────────────────────────
        new_row = {
            "business_name":         prospect.get("business_name", "").strip(),
            "city":                  prospect.get("city", "").strip(),
            "state":                 prospect.get("state", "").strip(),
            "website":               website.strip(),
            "phone":                 prospect.get("phone", "").strip(),
            "contact_method":        prospect.get("contact_method", "").strip(),
            "industry":              prospect.get("industry", "").strip(),
            "to_email":              to_email,
            "subject":               subject,
            "body":                  body,
            "approved":              "false",
            "sent_at":               "",
            "approval_reason":       "",   # filled below if autopilot fires
            "scoring_reason":        scoring_reason,
            "final_priority_score":  str(final_priority_score),
            "automation_opportunity": scan_result.get("automation_opportunity", "unknown"),
            "do_not_contact":        prospect.get("do_not_contact", ""),
            "draft_version":         DRAFT_VERSION,
            "facebook_url":          prospect.get("facebook_url", "").strip(),
            "instagram_url":         prospect.get("instagram_url", "").strip(),
            "contact_form_url":      prospect.get("contact_form_url", "").strip(),
            "social_channels":       prospect.get("social_channels", "").strip(),
            "social_dm_text":        prospect.get("social_dm_text", "").strip(),
            "facebook_dm_draft":     fb_draft,
            "instagram_dm_draft":    ig_draft,
            "contact_form_message":  form_msg,
            "lead_insight_sentence": insight_sentence,
            "lead_insight_signals":  "|".join(insight_signals) if isinstance(insight_signals, list) else str(insight_signals),
            "opportunity_score":     str(numeric_score),
            "last_contact_channel":  "",
            "last_contacted_at":     "",
            "contact_attempt_count": "0",
            "contact_result":        "",
            "next_followup_at":      "",
            "campaign_key":          "",
            "message_id":            "",
            "replied":               "",
            "replied_at":            "",
            "reply_snippet":         "",
            "conversation_notes":    "",
            "conversation_next_step": "",
        }

        # ── Phase A: Safe Autopilot ───────────────────────────────────────
        # Evaluate AFTER the row is fully built so all fields are present.
        # Sets approved="true" and approval_reason="safe_autopilot" when
        # all seven safety checks pass. Otherwise row stays approved="false".
        if safe_autopilot_eligible(new_row):
            new_row["approved"]        = "true"
            new_row["approval_reason"] = "safe_autopilot"
            autopilot_approved += 1

        pending_rows.append(new_row)

        # Update dedupe sets so in-run subsequent rows are checked too
        existing_keys.add(key)
        if prospect_domain:
            existing_domains.add(prospect_domain)
        if to_email:
            existing_emails.add(to_email.lower())

        drafted_names.add(prospect.get("business_name", "").strip().lower())
        drafted += 1

    _write_pending_rows(DEFAULT_PENDING_CSV, pending_rows)
    _update_prospect_status(input_path, drafted_names)

    approved_ready         = count_send_eligible_rows(DEFAULT_PENDING_CSV)
    contactability_summary = " ".join(f"{k}={v}" for k, v in sorted(contactability_counts.items()))
    print(
        "RUN SUMMARY "
        f"input={input_path} loaded={len(prospects)} scanned={websites_scanned} "
        f"drafted={drafted} autopilot_approved={autopilot_approved} "
        f"skipped={skipped} skipped_duplicate={skipped_duplicate} "
        f"directory_skipped={directory_skipped} "
        f"approved-ready={approved_ready} contactability=[{contactability_summary}] "
        f"queue={DEFAULT_PENDING_CSV}"
    )


def main() -> None:
    args = _parse_args()
    run(input_csv=args.input, limit=args.limit, skip_scan=args.skip_scan)


if __name__ == "__main__":
    main()
