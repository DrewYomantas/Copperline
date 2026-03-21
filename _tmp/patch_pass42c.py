"""
Pass 42 -- cleanup patch.
Applies the two missing pieces:
1. _leadRecord field extensions (hasWebsite, hasPhone, isStale, isReadyScheduled)
2. _leadQualBucket + _leadStatusMeta function definitions
Preconditions: _queueStateMeta + _mapPanelQualification already rewritten (from patch_pass42b.py).
"""

PATH = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

changes = []

# ── 1. Extend _leadRecord contact section ───────────────────────────────────

OLD_CONTACT = (
    "  const hasContact   = hasEmail || hasFacebook || hasInstagram || hasForm;\n"
    "  const bestChannel  = hasEmail ? 'email' : hasFacebook ? 'facebook' : hasInstagram ? 'instagram' : hasForm ? 'form' : 'none';"
)
NEW_CONTACT = (
    "  const hasContact   = hasEmail || hasFacebook || hasInstagram || hasForm;\n"
    "  const bestChannel  = hasEmail ? 'email' : hasFacebook ? 'facebook' : hasInstagram ? 'instagram' : hasForm ? 'form' : 'none';\n"
    "  // Pass 42: hasWebsite + hasPhone for _leadQualBucket\n"
    "  const hasWebsite   = !!(website.trim());\n"
    "  const hasPhone     = !!(phone.replace(/\\D/g,'').length >= 7);"
)
if OLD_CONTACT in src:
    src = src.replace(OLD_CONTACT, NEW_CONTACT, 1)
    changes.append("_leadRecord: hasWebsite + hasPhone added")
else:
    print("WARNING: _leadRecord contact block not found")

# ── 2. Extend _leadRecord workflow section ───────────────────────────────────

OLD_WORKFLOW = (
    "  const draftVersion = row.draft_version   || '';\n"
    "  const isLegacyDraft = !!draftVersion && draftVersion !== 'v9';"
)
NEW_WORKFLOW = (
    "  const draftVersion = row.draft_version   || '';\n"
    "  const isLegacyDraft = !!draftVersion && draftVersion !== 'v9';\n"
    "  // Pass 42: isStale + isReadyScheduled for _leadStatusMeta\n"
    "  const isStale          = !isSent && !!(typeof status_draft_version !== 'undefined' && status_draft_version && draftVersion && draftVersion !== status_draft_version);\n"
    "  const isReadyScheduled = !!(isScheduled && row.is_ready);"
)
if OLD_WORKFLOW in src:
    src = src.replace(OLD_WORKFLOW, NEW_WORKFLOW, 1)
    changes.append("_leadRecord: isStale + isReadyScheduled added")
else:
    print("WARNING: _leadRecord workflow block not found")

# ── 3. Add hasWebsite, hasPhone, isStale, isReadyScheduled to return object ──

OLD_RETURN_CONTACT = (
    "    // Contact\n"
    "    email, facebookUrl, instagramUrl, formUrl,\n"
    "    hasEmail, hasFacebook, hasInstagram, hasForm, hasContact, bestChannel,"
)
NEW_RETURN_CONTACT = (
    "    // Contact\n"
    "    email, facebookUrl, instagramUrl, formUrl,\n"
    "    hasEmail, hasFacebook, hasInstagram, hasForm, hasContact, bestChannel,\n"
    "    hasWebsite, hasPhone,"
)
if OLD_RETURN_CONTACT in src:
    src = src.replace(OLD_RETURN_CONTACT, NEW_RETURN_CONTACT, 1)
    changes.append("_leadRecord return: hasWebsite + hasPhone added")
else:
    print("WARNING: _leadRecord return contact block not found")

OLD_RETURN_WORKFLOW = (
    "    // Workflow status\n"
    "    isSent, isApproved, isScheduled, isReplied, isDNC, isLegacyDraft,\n"
    "    status, statusTone, draftVersion, nextAction,"
)
NEW_RETURN_WORKFLOW = (
    "    // Workflow status\n"
    "    isSent, isApproved, isScheduled, isReplied, isDNC, isLegacyDraft,\n"
    "    isStale, isReadyScheduled,\n"
    "    status, statusTone, draftVersion, nextAction,"
)
if OLD_RETURN_WORKFLOW in src:
    src = src.replace(OLD_RETURN_WORKFLOW, NEW_RETURN_WORKFLOW, 1)
    changes.append("_leadRecord return: isStale + isReadyScheduled added")
else:
    print("WARNING: _leadRecord return workflow block not found")

# ── 4. Inject _leadQualBucket + _leadStatusMeta before Stage 2B header ───────

ANCHOR = "// V2 Stage 2B - Unified Workspace Header"
HELPERS = """// ═══════════════════════════════════════════════════════════════════════════
// V2 Stage 2E — Shared Qualification + Status Meta Helpers
// ═══════════════════════════════════════════════════════════════════════════

/**
 * _leadQualBucket(record, extras)
 * Shared qualification bucket logic derived from _leadRecord.
 * Returns { key, label, order, tone, reasons }
 * extras: optional { score, oppScore, rating, reviewCount, contactability }
 */
function _leadQualBucket(record, extras) {
  if (!record) return { key: 'weak', label: 'Weak / skip', order: 3, tone: 'weak', reasons: [] };
  const r = record;
  const score       = (extras && extras.score    != null) ? extras.score    : r.priorityScore;
  const oppScore    = (extras && extras.oppScore  != null) ? extras.oppScore  : r.opportunityScore;
  const rating      = (extras && extras.rating      != null) ? Number(extras.rating)      : 0;
  const reviewCount = (extras && extras.reviewCount != null) ? Number(extras.reviewCount) : 0;
  const contactability = ((extras && extras.contactability) || '').trim().toLowerCase();

  const hasEmail    = r.hasEmail;
  const hasWebsite  = r.hasWebsite;
  const hasPhone    = r.hasPhone;
  const isSent      = r.isSent;
  const isApproved  = r.isApproved;
  const isScheduled = r.isScheduled;

  const strongSignals = score >= 4 || oppScore >= 60 || (rating >= 4.5 && reviewCount >= 20);
  const usableSignals = score >= 3 || oppScore >= 35 || (rating >= 4.1 && reviewCount >= 8);
  const highContactability   = contactability.includes('high');
  const mediumContactability = highContactability || contactability.includes('medium');
  const lowScore = score > 0 && score <= 2;

  let key = 'weak', label = 'Weak / skip', order = 3, tone = 'weak';

  if (isSent) {
    key = 'closed'; label = 'Sent / closed'; order = 4; tone = 'closed';
  } else if (hasEmail && (isApproved || isScheduled || strongSignals || highContactability || (hasWebsite && hasPhone))) {
    key = 'ready'; label = 'Ready now'; order = 0; tone = 'ready';
  } else if (!hasEmail && (hasWebsite || hasPhone) && (strongSignals || usableSignals || mediumContactability)) {
    key = 'needs-contact'; label = 'Needs contact info'; order = 2; tone = 'needs-contact';
  } else if (hasEmail || ((hasWebsite || hasPhone) && (usableSignals || mediumContactability))) {
    key = 'maybe'; label = 'Maybe later'; order = 1; tone = 'maybe';
  }

  const reasons = [];
  if (hasEmail)                    reasons.push('Email ready');
  else if (hasWebsite && hasPhone) reasons.push('Web + phone only');
  else if (hasPhone)               reasons.push('Phone only');
  else if (hasWebsite)             reasons.push('Website only');
  else                             reasons.push('No contact path');

  if (score >= 4)       reasons.push('Score ' + score);
  else if (lowScore)    reasons.push(score ? 'Low score ' + score : 'Low score');
  else if (score === 3) reasons.push('Mid score');

  if (!hasEmail)               reasons.push('Needs email');
  if (!hasWebsite)             reasons.push('No website');
  if (!hasPhone && !hasEmail)  reasons.push('No direct contact');
  if ((rating >= 4.5 && reviewCount >= 20) || (rating >= 4.1 && reviewCount >= 8)) {
    reasons.push(rating.toFixed(1) + '\\u2605/' + Math.round(reviewCount));
  }
  if (highContactability) reasons.push('High contactability');

  return { key, label, order, tone, reasons: Array.from(new Set(reasons)).slice(0, 3) };
}

/**
 * _leadStatusMeta(record)
 * Shared status badge/label/subline/detail/tone from _leadRecord.
 * Same return shape as _queueStateMeta: { badgeClass, label, title, subline, detail, tone }
 */
function _leadStatusMeta(record) {
  if (!record) return { badgeClass: 'badge-pending', label: 'Pending', title: '', subline: '', detail: '', tone: 'info' };
  const r = record;
  if (r.isReplied) return { badgeClass: 'badge-replied', label: 'Replied',  title: 'Reply received',    subline: 'Conversation active',      detail: 'No send action needed',          tone: 'info' };
  if (r.isSent)    return { badgeClass: 'badge-sent',    label: 'Sent',     title: 'Already sent',       subline: 'Completed send',            detail: 'No further queue action',        tone: 'info' };
  if (r.isStale)   return { badgeClass: 'badge-stale',   label: 'Stale',    title: 'Old copy - regenerate before sending', subline: 'Needs refresh before send', detail: 'Draft version is behind current prompt', tone: 'wait' };
  if (r.isScheduled && !r.isReadyScheduled) {
    const relative = r.sendAfter ? (typeof _formatSendAfter === 'function'      ? _formatSendAfter(r.sendAfter)      : r.sendAfter) : '';
    const exact    = r.sendAfter ? (typeof _formatSendAfterExact === 'function' ? _formatSendAfterExact(r.sendAfter) : r.sendAfter) : '';
    return { badgeClass: 'badge-scheduled', label: 'Scheduled', title: 'Scheduled for ' + (exact || r.sendAfter), subline: 'Waits until ' + (relative || r.sendAfter), detail: (exact || '') + ' - not in Send Approved yet', tone: 'wait' };
  }
  if (r.isReadyScheduled) {
    const exact = r.sendAfter ? (typeof _formatSendAfterExact === 'function' ? _formatSendAfterExact(r.sendAfter) : r.sendAfter) : '';
    return { badgeClass: 'badge-ready', label: 'Ready Now', title: 'Scheduled window reached at ' + (exact || r.sendAfter), subline: 'Scheduled time reached', detail: (exact || '') + ' - included in Send Approved now', tone: 'ready' };
  }
  if (r.isApproved) return { badgeClass: 'badge-approved', label: 'Approved', title: 'Approved and ready to send now', subline: 'Ready to send now', detail: 'Included in Send Approved immediately', tone: 'ready' };
  return { badgeClass: 'badge-pending', label: 'Pending', title: 'Still needs operator approval', subline: 'Needs approval before send', detail: 'Not in Send Approved yet', tone: 'info' };
}

"""

if ANCHOR in src and "_leadQualBucket" not in src:
    src = src.replace(ANCHOR, HELPERS + ANCHOR, 1)
    changes.append("_leadQualBucket + _leadStatusMeta injected")
elif "_leadQualBucket" in src:
    print("INFO: _leadQualBucket already present, skipping injection")
else:
    print("WARNING: Stage 2B anchor not found")

# ── 5. Write ──────────────────────────────────────────────────────────────────

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\n{len(changes)} changes applied:")
for c in changes:
    print(f"  + {c}")
