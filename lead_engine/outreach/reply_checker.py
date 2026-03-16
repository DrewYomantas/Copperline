"""
reply_checker.py — Gmail IMAP reply detection for Copperline outreach
======================================================================
Polls the operator's Gmail inbox for replies to sent cold emails,
matches them back to prospects in pending_emails.csv, flags them as
'replied', logs every event, and fires optional webhook notifications.

Credentials used:
  GMAIL_ADDRESS      — the sending Gmail account (same as email_sender_agent)
  GMAIL_APP_PASSWORD — Gmail App Password (same as email_sender_agent)

Optional:
  REPLY_WEBHOOK_URL  — if set, POSTs a JSON payload to this URL on each reply

Run manually:
  python lead_engine/outreach/reply_checker.py

Or call from dashboard via POST /api/check_replies.
"""
from __future__ import annotations

import csv
import email
import imaplib
import json
import logging
import os
import time
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
try:
    from urllib.request import urlopen, Request as URLRequest
    from urllib.error import URLError
except ImportError:
    pass

log = logging.getLogger("copperline.replies")

BASE_DIR = Path(__file__).resolve().parent.parent
PENDING_CSV   = BASE_DIR / "queue" / "pending_emails.csv"
PROSPECTS_CSV = BASE_DIR / "data" / "prospects.csv"
REPLIES_LOG   = BASE_DIR / "logs" / "replies.log"

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SENT_MAILBOXES = ['"[Gmail]/Sent Mail"', '"[Gmail]/Sent"', 'Sent', '"Sent Mail"']


# ---------------------------------------------------------------------------
# Pending CSV helpers
# ---------------------------------------------------------------------------

PENDING_COLUMNS = [
    "business_name", "city", "state", "website", "phone", "contact_method",
    "industry", "to_email", "subject", "body", "approved", "sent_at",
    "approval_reason", "scoring_reason", "final_priority_score", "automation_opportunity",
    "do_not_contact", "draft_version",
    "facebook_url", "instagram_url", "contact_form_url",
    "social_channels", "social_dm_text",
    "facebook_dm_draft", "instagram_dm_draft", "contact_form_message",
    "lead_insight_sentence", "lead_insight_signals", "opportunity_score",
    "last_contact_channel", "last_contacted_at", "contact_attempt_count",
    "contact_result", "next_followup_at", "campaign_key",
    "message_id", "replied", "replied_at", "reply_snippet",
    "conversation_notes", "conversation_next_step",
    "send_after",
]


def _read_pending() -> List[Dict[str, str]]:
    if not PENDING_CSV.exists():
        return []
    with PENDING_CSV.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        return [{col: row.get(col, "") for col in PENDING_COLUMNS} for row in reader]


def _write_pending(rows: List[Dict[str, str]]) -> None:
    PENDING_CSV.parent.mkdir(parents=True, exist_ok=True)
    with PENDING_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PENDING_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _read_prospects() -> Tuple[List[str], List[Dict]]:
    if not PROSPECTS_CSV.exists():
        return [], []
    with PROSPECTS_CSV.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def _write_prospects(fieldnames: List[str], rows: List[Dict]) -> None:
    with PROSPECTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# IMAP helpers
# ---------------------------------------------------------------------------

def _decode_header_value(raw: str) -> str:
    """Safely decode an RFC2047-encoded email header to a plain string."""
    parts = decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _get_text_body(msg: email.message.Message) -> str:
    """Extract the first plaintext body part from a parsed email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace") if payload else ""
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace") if payload else ""
    return ""


def _connect_imap() -> imaplib.IMAP4_SSL:
    """Open an authenticated IMAP connection using env credentials."""
    address  = os.getenv("GMAIL_ADDRESS", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    if not address or not password:
        raise RuntimeError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set to check replies."
        )
    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    conn.login(address, password)
    return conn


def _fetch_recent_inbox_messages(
    conn: imaplib.IMAP4_SSL,
    max_messages: int = 100,
) -> List[email.message.Message]:
    """
    Fetch the most recent `max_messages` messages from INBOX.
    Returns a list of parsed email.message.Message objects.
    Only fetches headers + body — does not mark as read.
    """
    conn.select("INBOX", readonly=True)
    _, data = conn.search(None, "ALL")
    if not data or not data[0]:
        return []

    all_ids = data[0].split()
    # Take the most recent max_messages (last N ids)
    recent_ids = all_ids[-max_messages:]
    messages = []

    for uid in recent_ids:
        try:
            _, msg_data = conn.fetch(uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if isinstance(raw, bytes):
                msg = email.message_from_bytes(raw)
                messages.append(msg)
        except Exception as exc:
            log.debug("Failed to fetch message %s: %s", uid, exc)

    return messages


def _select_sent_mailbox(conn: imaplib.IMAP4_SSL) -> Optional[str]:
    """Pick the first available Sent mailbox variant and select it readonly."""
    for mailbox in SENT_MAILBOXES:
        try:
            status, _ = conn.select(mailbox, readonly=True)
            if status == "OK":
                return mailbox
        except Exception:
            continue
    return None


def _fetch_recent_sent_messages(
    conn: imaplib.IMAP4_SSL,
    max_messages: int = 150,
    lookback_hours: int = 72,
) -> List[email.message.Message]:
    """
    Fetch recent sent messages from Gmail Sent mailbox.
    Applies a UTC lookback window to keep reconciliation narrow.
    """
    mailbox = _select_sent_mailbox(conn)
    if not mailbox:
        return []

    _, data = conn.search(None, "ALL")
    if not data or not data[0]:
        return []

    all_ids = data[0].split()
    recent_ids = all_ids[-max_messages:]
    cutoff = datetime.now(timezone.utc).timestamp() - (lookback_hours * 3600)
    messages: List[email.message.Message] = []

    for uid in recent_ids:
        try:
            _, msg_data = conn.fetch(uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, bytes):
                continue
            msg = email.message_from_bytes(raw)
            msg_date = msg.get("Date", "")
            if msg_date:
                try:
                    dt = parsedate_to_datetime(msg_date)
                    if dt is not None:
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if dt.timestamp() < cutoff:
                            continue
                except Exception:
                    # If date parsing fails, keep candidate and let strict key matching decide.
                    pass
            messages.append(msg)
        except Exception as exc:
            log.debug("Failed to fetch sent message %s: %s", uid, exc)

    return messages


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

def _build_sent_index(pending_rows: List[Dict]) -> Dict[str, Dict]:
    """
    Build two lookup indexes from the pending queue.

    Returns a dict with two sub-dicts:
      'by_message_id': { "<message-id>" : pending_row }
      'by_email':      { "prospect@email.com" : pending_row }

    Only includes rows that have been sent (sent_at is set) and not yet
    marked as replied.
    """
    by_mid: Dict[str, Dict]   = {}
    by_email: Dict[str, Dict] = {}

    for row in pending_rows:
        if not row.get("sent_at"):
            continue  # not yet sent
        if row.get("replied", "").lower() == "true":
            continue  # already flagged

        mid = (row.get("message_id") or "").strip().lower()
        if mid:
            by_mid[mid] = row

        addr = (row.get("to_email") or "").strip().lower()
        if addr and "@" in addr:
            by_email[addr] = row

    return {"by_message_id": by_mid, "by_email": by_email}


def _match_reply(
    msg: email.message.Message,
    index: Dict,
    operator_address: str,
) -> Optional[Dict]:
    """
    Try to match an inbox message to a sent outreach row.

    Match strategy (in priority order):
    1. In-Reply-To or References header matches a stored Message-ID
    2. From address of the inbox message matches a prospect's to_email

    Only considers messages addressed TO the operator (i.e., genuine replies).
    Returns the matched pending row dict, or None.
    """
    # Must be addressed to us
    to_field = _decode_header_value(msg.get("To", "")).lower()
    if operator_address.lower() not in to_field:
        return None

    # Strategy 1: header-based matching (most reliable)
    for header in ("In-Reply-To", "References"):
        raw = msg.get(header, "")
        if not raw:
            continue
        for mid in raw.split():
            mid_clean = mid.strip().strip("<>").lower()
            if mid_clean in index["by_message_id"]:
                return index["by_message_id"][mid_clean]

    # Strategy 2: sender address matches a prospect we emailed
    from_field = _decode_header_value(msg.get("From", "")).lower()
    for prospect_email, row in index["by_email"].items():
        if prospect_email in from_field:
            return row

    return None


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

def _log_reply_event(business_name: str, from_addr: str, snippet: str) -> None:
    """Append a reply event to the local replies log file."""
    REPLIES_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] REPLY | {business_name} | from={from_addr} | snippet={snippet[:120]!r}\n"
    with REPLIES_LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    # Always print to console so the operator sees it in the terminal
    print(f"\n  ★ REPLY RECEIVED — {business_name}")
    print(f"    From   : {from_addr}")
    print(f"    Snippet: {snippet[:120]}")
    print()
    log.info("Reply received: business=%s from=%s", business_name, from_addr)


def _fire_webhook(business_name: str, from_addr: str, snippet: str, replied_at: str) -> None:
    """POST reply data to REPLY_WEBHOOK_URL if configured. Fails silently."""
    webhook_url = os.getenv("REPLY_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return
    payload = json.dumps({
        "event": "outreach_reply",
        "business_name": business_name,
        "from": from_addr,
        "snippet": snippet[:500],
        "replied_at": replied_at,
    }).encode("utf-8")
    try:
        req = URLRequest(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=8) as r:
            log.info("Webhook fired: status=%d url=%s", r.status, webhook_url)
    except Exception as exc:
        log.warning("Webhook failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Core public function
# ---------------------------------------------------------------------------

def check_for_replies(max_messages: int = 100) -> Dict:
    """
    Poll Gmail INBOX for replies to sent outreach emails.

    For each reply found:
    - Marks pending_emails.csv row: replied=true, replied_at=<iso>, reply_snippet
    - Updates prospects.csv row: status=replied
    - Logs to logs/replies.log
    - Prints to console
    - POSTs to REPLY_WEBHOOK_URL if configured

    Returns a summary dict:
      { "checked": int, "new_replies": int, "errors": [str], "replies": [dict] }

    Safe to call repeatedly — already-replied rows are skipped.
    Never raises — all errors are caught and returned in the errors list.
    """
    summary: Dict = {"checked": 0, "new_replies": 0, "errors": [], "replies": []}

    operator_address = os.getenv("GMAIL_ADDRESS", "").strip()
    if not operator_address:
        summary["errors"].append("GMAIL_ADDRESS not set — cannot check replies.")
        return summary

    # Read current queue state
    pending_rows = _read_pending()
    index = _build_sent_index(pending_rows)

    if not index["by_message_id"] and not index["by_email"]:
        log.info("No sent+unread prospects to match against — skipping IMAP check.")
        return summary

    # Connect and fetch
    try:
        conn = _connect_imap()
    except Exception as exc:
        summary["errors"].append(f"IMAP connection failed: {exc}")
        return summary

    try:
        messages = _fetch_recent_inbox_messages(conn, max_messages=max_messages)
        summary["checked"] = len(messages)
    except Exception as exc:
        summary["errors"].append(f"IMAP fetch failed: {exc}")
        messages = []
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    # Match each inbox message to a pending row
    now_iso = datetime.now(timezone.utc).isoformat()
    matched_keys: set = set()  # prevent double-counting in one run

    for msg in messages:
        try:
            matched_row = _match_reply(msg, index, operator_address)
            if matched_row is None:
                continue

            row_key = (matched_row.get("business_name", ""), matched_row.get("to_email", ""))
            if row_key in matched_keys:
                continue
            matched_keys.add(row_key)

            # Extract reply metadata
            from_addr = _decode_header_value(msg.get("From", ""))
            body_text  = _get_text_body(msg)
            snippet    = body_text.strip()[:300].replace("\n", " ")
            replied_at = now_iso

            # Update the pending row in-place
            matched_row["replied"]      = "true"
            matched_row["replied_at"]   = replied_at
            matched_row["reply_snippet"] = snippet

            business_name = matched_row.get("business_name", "unknown")

            # Notify
            _log_reply_event(business_name, from_addr, snippet)
            _fire_webhook(business_name, from_addr, snippet, replied_at)

            summary["new_replies"] += 1
            summary["replies"].append({
                "business_name": business_name,
                "from": from_addr,
                "snippet": snippet[:200],
                "replied_at": replied_at,
            })

        except Exception as exc:
            log.warning("Error processing message: %s", exc)
            summary["errors"].append(str(exc))

    # Persist changes if any replies were found
    if summary["new_replies"] > 0:
        _write_pending(pending_rows)
        _update_prospects_replied(
            {r["business_name"] for r in summary["replies"]}
        )

    return summary


def reconcile_sent_mail(max_messages: int = 150, lookback_hours: int = 72) -> Dict:
    """
    Reconcile queue rows with Gmail Sent messages after interrupted dashboard sessions.

    Matching key: (recipient email + subject), optionally narrowed by a recent lookback.
    Safety: only considers rows where sent_at and message_id are both blank;
    ambiguous keys are skipped.
    """
    summary: Dict = {
        "checked_sent_messages": 0,
        "updated_rows": 0,
        "matched": [],
        "skipped_ambiguous": 0,
        "errors": [],
    }

    pending_rows = _read_pending()
    if not pending_rows:
        return summary

    # Candidate queue rows: approved + unsent only.
    key_to_indexes: Dict[Tuple[str, str], List[int]] = {}
    for idx, row in enumerate(pending_rows):
        if (row.get("approved", "").strip().lower() != "true"):
            continue
        if (row.get("sent_at") or "").strip() or (row.get("message_id") or "").strip():
            continue
        to_email = (row.get("to_email") or "").strip().lower()
        subject = (row.get("subject") or "").strip()
        if not to_email or not subject:
            continue
        key_to_indexes.setdefault((to_email, subject), []).append(idx)

    if not key_to_indexes:
        return summary

    try:
        conn = _connect_imap()
    except Exception as exc:
        summary["errors"].append(f"IMAP connection failed: {exc}")
        return summary

    try:
        sent_messages = _fetch_recent_sent_messages(
            conn,
            max_messages=max_messages,
            lookback_hours=lookback_hours,
        )
        summary["checked_sent_messages"] = len(sent_messages)
    except Exception as exc:
        summary["errors"].append(f"Sent mailbox fetch failed: {exc}")
        sent_messages = []
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    sent_matches: Dict[Tuple[str, str], List[email.message.Message]] = {}
    for msg in sent_messages:
        to_field = _decode_header_value(msg.get("To", "")).strip().lower()
        subject = _decode_header_value(msg.get("Subject", "")).strip().lower()
        if not to_field or not subject:
            continue
        for key in key_to_indexes.keys():
            if key[0] in to_field and key[1].strip().lower() == subject:
                sent_matches.setdefault(key, []).append(msg)

    now_iso = datetime.now(timezone.utc).isoformat()
    touched = False
    for key, indexes in key_to_indexes.items():
        matched_messages = sent_matches.get(key, [])
        # Ambiguous if multiple queue rows share same key OR multiple sent messages match key.
        if len(indexes) != 1 or len(matched_messages) != 1:
            if matched_messages:
                summary["skipped_ambiguous"] += len(indexes)
            continue

        idx = indexes[0]
        msg = matched_messages[0]
        pending_rows[idx]["sent_at"] = now_iso
        msg_mid = (msg.get("Message-ID") or "").strip()
        if msg_mid and not (pending_rows[idx].get("message_id") or "").strip():
            pending_rows[idx]["message_id"] = msg_mid
        summary["updated_rows"] += 1
        summary["matched"].append({
            "index": idx,
            "business_name": pending_rows[idx].get("business_name", ""),
            "to_email": pending_rows[idx].get("to_email", ""),
            "subject": pending_rows[idx].get("subject", ""),
        })
        touched = True

    if touched:
        _write_pending(pending_rows)

    return summary


def _update_prospects_replied(business_names: set) -> None:
    """Set status=replied in prospects.csv for matched businesses."""
    if not business_names:
        return
    names_lower = {n.strip().lower() for n in business_names}
    fieldnames, rows = _read_prospects()
    if "status" not in fieldnames:
        fieldnames.append("status")
    for row in rows:
        if row.get("business_name", "").strip().lower() in names_lower:
            row["status"] = "replied"
    _write_prospects(fieldnames, rows)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Check Gmail for replies to outreach emails.")
    parser.add_argument("--max", type=int, default=100,
                        help="Max inbox messages to scan (default: 100)")
    args = parser.parse_args()

    print(f"\nChecking Gmail inbox for outreach replies (scanning last {args.max} messages)…\n")
    result = check_for_replies(max_messages=args.max)

    print(f"  Messages scanned : {result['checked']}")
    print(f"  New replies found: {result['new_replies']}")
    if result["replies"]:
        print()
        for r in result["replies"]:
            print(f"  ★ {r['business_name']}")
            print(f"    From   : {r['from']}")
            print(f"    Snippet: {r['snippet'][:100]}")
            print()
    if result["errors"]:
        print("  Errors:")
        for e in result["errors"]:
            print(f"    - {e}")
    print()


if __name__ == "__main__":
    main()
