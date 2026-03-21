"""
Pass 42 patch -- part 2.
Applies: _leadQualBucket+_leadStatusMeta injection, _queueStateMeta rewrite, _mapPanelQualification rewrite.
The _leadRecord extensions were already applied in part 1 (patch_pass42.py).
Uses direct string replacement throughout to avoid regex escaping issues.
"""

PATH = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

original_len = len(src)
changes = []

# ─────────────────────────────────────────────────────────────────────────────
# 1. Inject _leadQualBucket + _leadStatusMeta before Stage 2B header
# ─────────────────────────────────────────────────────────────────────────────

ANCHOR = "// V2 Stage 2B - Unified Workspace Header"

SHARED_HELPERS = """// ═══════════════════════════════════════════════════════════════════════════
// V2 Stage 2E — Shared Qualification + Status Meta Helpers
// ═══════════════════════════════════════════════════════════════════════════

/**
 * _leadQualBucket(record, extras)
 * Qualification bucket from _leadRecord + optional biz-only extras.
 * Returns { key, label, order, tone, reasons }
 * extras: { score, oppScore, rating, reviewCount, contactability }
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
    reasons.push(rating.toFixed(1) + '\u2605/' + Math.round(reviewCount));
  }
  if (highContactability) reasons.push('High contactability');

  return { key, label, order, tone, reasons: Array.from(new Set(reasons)).slice(0, 3) };
}

/**
 * _leadStatusMeta(record)
 * Status badge/label/subline/detail/tone from _leadRecord.
 * Same return shape as _queueStateMeta: { badgeClass, label, title, subline, detail, tone }
 */
function _leadStatusMeta(record) {
  if (!record) return { badgeClass: 'badge-pending', label: 'Pending', title: '', subline: '', detail: '', tone: 'info' };
  const r = record;
  if (r.isReplied) return { badgeClass: 'badge-replied', label: 'Replied', title: 'Reply received', subline: 'Conversation active', detail: 'No send action needed', tone: 'info' };
  if (r.isSent)    return { badgeClass: 'badge-sent',    label: 'Sent',    title: 'Already sent',   subline: 'Completed send',        detail: 'No further queue action', tone: 'info' };
  if (r.isStale)   return { badgeClass: 'badge-stale',   label: 'Stale',   title: 'Old copy - regenerate before sending', subline: 'Needs refresh before send', detail: 'Draft version is behind current prompt', tone: 'wait' };
  if (r.isScheduled && !r.isReadyScheduled) {
    const fmt = typeof _formatSendAfter === 'function';
    const relative = r.sendAfter ? (fmt ? _formatSendAfter(r.sendAfter) : r.sendAfter) : '';
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

if ANCHOR in src and "Stage 2E" not in src:
    src = src.replace(ANCHOR, SHARED_HELPERS + ANCHOR, 1)
    changes.append("_leadQualBucket + _leadStatusMeta injected before Stage 2B header")
else:
    print("WARNING: anchor not found or Stage 2E already present")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Rewrite _queueStateMeta as thin wrapper over _leadStatusMeta
#    Strategy: find the function body by unique start+end markers and replace.
# ─────────────────────────────────────────────────────────────────────────────

# Unique start and end markers
QSM_START = "function _queueStateMeta(row) {"
# The function ends with the Pending return
QSM_END = (
    "  return {\n"
    "    badgeClass: 'badge-pending',\n"
    "    label: 'Pending',\n"
    "    title: 'Still needs operator approval',\n"
    "    subline: 'Needs approval before send',\n"
    "    detail: 'Not in Send Approved yet',\n"
    "    tone: 'info',\n"
    "  };\n"
    "}"
)

NEW_QSM = """function _queueStateMeta(row) {
  // Pass 42: thin wrapper over _leadStatusMeta. Same return shape preserved.
  return _leadStatusMeta(_leadRecord(row));
}"""

start_idx = src.find(QSM_START)
end_idx   = src.find(QSM_END)
if start_idx >= 0 and end_idx >= start_idx:
    end_idx += len(QSM_END)
    src = src[:start_idx] + NEW_QSM + src[end_idx:]
    changes.append("_queueStateMeta rewritten as thin wrapper over _leadStatusMeta")
else:
    print(f"WARNING: _queueStateMeta block not bounded (start={start_idx}, end={end_idx})")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Rewrite _mapPanelQualification as thin wrapper over _leadRecord + _leadQualBucket
# ─────────────────────────────────────────────────────────────────────────────

MPQ_START = "function _mapPanelQualification(item, qrow) {"
# End marker: the unique last line of the return
MPQ_END = "  return {\n    key,\n    label,\n    order,\n    tone,\n    hasEmail,\n    hasWebsite,\n    hasPhone,\n    score,\n    lowScore,\n    isSent,\n    isApproved,\n    isScheduled,\n    reasons: Array.from(new Set(reasons)).slice(0, 3),\n  };\n}"

NEW_MPQ = """function _mapPanelQualification(item, qrow) {
  // Pass 42: delegates to _leadQualBucket via _leadRecord.
  // Biz-only extras (rating, reviewCount, contactability) passed through separately.
  const baseInput = qrow || { business_name: item.biz.name || '', city: item.biz.city || '', website: item.biz.website || '', phone: item.biz.phone || '', to_email: item.biz.email || '' };
  const record = _leadRecord(baseInput);

  // Override contact fields with biz-object values if stronger
  const mergedRecord = Object.assign({}, record, {
    hasEmail:   !!((item.biz.email   || record.email   || '').trim().includes('@')),
    hasWebsite: !!((item.biz.website || record.website || '').trim()),
    hasPhone:   (((item.biz.phone    || record.phone   || '').replace(/\D/g, '')).length >= 7),
    priorityScore:    _mapPanelItemScore(item, qrow),
    opportunityScore: _mapPanelNumber(
      qrow && (qrow.opp_score ?? qrow.opportunity_score),
      item.biz.opp_score ?? item.biz.opportunity_score
    ),
  });

  const extras = {
    score:           mergedRecord.priorityScore,
    oppScore:        mergedRecord.opportunityScore,
    rating:          _mapPanelNumber(qrow && qrow.rating, item.biz.rating),
    reviewCount:     _mapPanelNumber(qrow && (qrow.review_count ?? qrow.reviews), item.biz.review_count ?? item.biz.reviews),
    contactability:  String((qrow && qrow.contactability) || item.biz.contactability || ''),
  };

  const bucket = _leadQualBucket(mergedRecord, extras);

  return {
    key:         bucket.key,
    label:       bucket.label,
    order:       bucket.order,
    tone:        bucket.tone,
    hasEmail:    mergedRecord.hasEmail,
    hasWebsite:  mergedRecord.hasWebsite,
    hasPhone:    mergedRecord.hasPhone,
    score:       mergedRecord.priorityScore,
    lowScore:    mergedRecord.priorityScore > 0 && mergedRecord.priorityScore <= 2,
    isSent:      mergedRecord.isSent,
    isApproved:  mergedRecord.isApproved,
    isScheduled: mergedRecord.isScheduled,
    reasons:     bucket.reasons,
  };
}"""

mpq_start = src.find(MPQ_START)
mpq_end   = src.find(MPQ_END)
if mpq_start >= 0 and mpq_end >= mpq_start:
    mpq_end += len(MPQ_END)
    src = src[:mpq_start] + NEW_MPQ + src[mpq_end:]
    changes.append("_mapPanelQualification rewritten as thin wrapper over _leadRecord + _leadQualBucket")
else:
    print(f"WARNING: _mapPanelQualification block not bounded (start={mpq_start}, end={mpq_end})")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Write
# ─────────────────────────────────────────────────────────────────────────────

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\n{len(changes)}/3 changes applied:")
for c in changes:
    print(f"  + {c}")
print(f"File: {original_len} -> {len(src)} chars (+{len(src)-original_len})")
