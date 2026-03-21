"""
Pass 36 verification — observation-led outreach rewrite.
Runs against the live email_draft_agent without touching any protected systems.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lead_engine'))

from outreach.email_draft_agent import (
    DRAFT_VERSION,
    draft_email,
    draft_social_messages,
    validate_draft,
    ObservationMissingError,
    DraftInvalidError,
    _is_generic_observation,
    _require_observation,
)

PASS = 0
FAIL = 0

def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  OK   {label}")
        PASS += 1
    else:
        print(f"  FAIL {label}" + (f" -- {detail}" if detail else ""))
        FAIL += 1

print("\n=== Pass 36 Verification ===\n")

# --- 1. DRAFT_VERSION ---
check("DRAFT_VERSION is v9", DRAFT_VERSION == "v9")

# --- 2. Missing observation blocks email generation ---
prospect_no_obs = {"business_name": "Rockford Plumbing", "city": "Rockford", "state": "IL"}
try:
    draft_email(prospect_no_obs, 3)
    check("draft_email blocks when observation missing", False, "Should have raised ObservationMissingError")
except ObservationMissingError as e:
    check("draft_email blocks when observation missing", True)
except Exception as e:
    check("draft_email blocks when observation missing", False, str(e))

# --- 3. Missing observation blocks DM generation ---
try:
    draft_social_messages(prospect_no_obs, "")
    check("draft_social_messages blocks when observation missing", False, "Should have raised ObservationMissingError")
except ObservationMissingError:
    check("draft_social_messages blocks when observation missing", True)
except Exception as e:
    check("draft_social_messages blocks when observation missing", False, str(e))

# --- 4. Generic observation is rejected ---
try:
    _require_observation("noticed you do landscaping")
    # _require_observation itself won't catch generic — but _is_generic_observation will
    is_gen = _is_generic_observation("noticed you do landscaping")
    check("Generic observation detected correctly", is_gen)
except ObservationMissingError:
    check("Generic observation detected correctly", True)

# --- 5. Short observation is rejected ---
try:
    _require_observation("snow")
    check("Short observation blocked", False, "Should have raised")
except ObservationMissingError:
    check("Short observation blocked", True)

# --- 6. Valid observation produces a draft ---
prospect_with_obs = {
    "business_name": "Rockford Plumbing",
    "city": "Rockford",
    "state": "IL",
    "industry": "plumbing",
    "business_specific_observation": "saw they're juggling snow removal contracts alongside their regular plumbing work — pretty mixed seasonal lineup",
}
try:
    subj, body = draft_email(prospect_with_obs, 3)
    check("draft_email succeeds with valid observation", True)
    check("Subject is non-empty", bool(subj))
    check("Body is non-empty", bool(body))
    check("Body contains sign-off", "- Drew" in body)
    word_count = len(body.replace("- Drew", "").split())
    check(f"Body word count reasonable (got {word_count})", word_count < 100)
    print(f"\n    Subject: {subj}")
    print(f"    Body:\n{body}\n")
except Exception as e:
    check("draft_email succeeds with valid observation", False, str(e))

# --- 7. Observation materially appears in draft ---
obs_token = "snow"
check(
    "Observation token appears in draft body",
    obs_token in body.lower(),
    f"'snow' not found in: {body[:120]}"
)

# --- 8. Draft does not contain banned words ---
BANNED_CHECK = [
    "optimize", "streamline", "automate", "automation", "lead gen",
    "scale", "book a call", "schedule a call", "free audit",
    "business growth", "autopilot", "never miss a lead",
]
banned_hits = [w for w in BANNED_CHECK if w in body.lower()]
check("No banned words in draft", not banned_hits, f"Found: {banned_hits}")

# --- 9. DM generation with observation ---
try:
    dm, _, _ = draft_social_messages(prospect_with_obs, body)
    check("draft_social_messages succeeds with observation", True)
    check("DM is non-empty", bool(dm))
    check("DM observation token appears", obs_token in dm.lower(), f"token not in: {dm[:120]}")
    check("DM has no links", "https://" not in dm and "http://" not in dm)
    print(f"\n    DM:\n{dm}\n")
except Exception as e:
    check("draft_social_messages succeeds with observation", False, str(e))

# --- 10. Validation layer rejects banned words ---
try:
    validate_draft("hey — we can automate your lead gen. book a call now.", "some observation here")
    check("validate_draft rejects banned words", False, "Should have raised DraftInvalidError")
except DraftInvalidError as e:
    check("validate_draft rejects banned words", True)

# --- 11. Validation layer rejects links ---
try:
    validate_draft("saw your lineup https://example.com click here to book", "saw your lineup")
    check("validate_draft rejects links", False, "Should have raised DraftInvalidError")
except DraftInvalidError:
    check("validate_draft rejects links", True)

# --- 12. Validation layer rejects pricing ---
try:
    validate_draft("we charge $199 per month for our system", "we charge per month")
    check("validate_draft rejects pricing", False)
except DraftInvalidError:
    check("validate_draft rejects pricing", True)

# --- 13. Controlled variation — 3 businesses get different variants ---
businesses = [
    {"business_name": "Alpha HVAC", "city": "Rockford", "state": "IL", "industry": "hvac",
     "business_specific_observation": "noticed they run both residential installs and commercial service calls — pretty wide scope for a two-person shop"},
    {"business_name": "Beta Roofing", "city": "Chicago", "state": "IL", "industry": "roofing",
     "business_specific_observation": "saw most of their recent posts are smaller repair jobs not full re-roofs — looks like a repair-first operation"},
    {"business_name": "Gamma Garage", "city": "Peoria", "state": "IL", "industry": "garage_door",
     "business_specific_observation": "saw they advertise both commercial and residential installs on the same homepage without separating them"},
]
variants_seen = set()
all_ok = True
for p in businesses:
    try:
        s, b = draft_email(p, 3)
        # Variation check: first ~15 words of body should differ
        snippet = " ".join(b.split()[:15])
        variants_seen.add(snippet)
    except Exception as e:
        all_ok = False
        print(f"    variant error for {p['business_name']}: {e}")

check("Controlled variations produce distinct openings", len(variants_seen) >= 2,
      f"Only {len(variants_seen)} distinct variants from 3 businesses")
check("All 3 businesses generated without error", all_ok)

# --- 14. prospect field observation (not arg) is used ---
prospect_field_obs = {
    "business_name": "Delta Electric",
    "city": "Joliet",
    "state": "IL",
    "industry": "electrical",
    "business_specific_observation": "saw they specialize in panel upgrades for older homes — narrow but clear niche",
}
try:
    s2, b2 = draft_email(prospect_field_obs, 3)
    check("Observation from prospect field works", True)
    check("Field obs token in body", "panel" in b2.lower() or "niche" in b2.lower() or "older" in b2.lower(),
          f"none found in: {b2[:100]}")
except Exception as e:
    check("Observation from prospect field works", False, str(e))

# --- Summary ---
print(f"\n=== Results: {PASS} passed, {FAIL} failed ===\n")
if FAIL > 0:
    sys.exit(1)
