"""
Pass 42 -- V2 Stage 2E: Qualification + Status Derivation Unification

Changes:
1. Add hasWebsite, hasPhone, isStale, isReadyScheduled to _leadRecord
2. Add _leadQualBucket(record, item) -- shared qualification bucket logic
3. Add _leadStatusMeta(record) -- shared status badge/label/subline/detail/tone
4. Wire _mapPanelQualification through _leadRecord + _leadQualBucket
5. Wire _queueStateMeta through _leadStatusMeta
"""
import re

PATH = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

original_len = len(src)
changes = []

# ─────────────────────────────────────────────────────────────────────────────
# 1. Extend _leadRecord to add hasWebsite, hasPhone, isStale, isReadyScheduled
#    These are computed inline in _mapPanelQualification and _queueStateMeta.
#    Adding them to _leadRecord means all callers can read them from one place.
# ─────────────────────────────────────────────────────────────────────────────

OLD_CONTACT_BLOCK = (
    "  // Contact channels\n"
    "  const email        = row.to_email         || b.email          || '';\n"
    "  const facebookUrl  = row.facebook_url     || b.facebook_url   || '';\n"
    "  const instagramUrl = row.instagram_url    || b.instagram_url  || '';\n"
    "  const formUrl      = row.contact_form_url || b.contact_form_url || '';\n"
    "  const hasEmail     = email.includes('@');\n"
    "  const hasFacebook  = !!facebookUrl.trim();\n"
    "  const hasInstagram = !!instagramUrl.trim();\n"
    "  const hasForm      = !!formUrl.trim();\n"
    "  const hasContact   = hasEmail || hasFacebook || hasInstagram || hasForm;\n"
    "  const bestChannel  = hasEmail ? 'email' : hasFacebook ? 'facebook' : hasInstagram ? 'instagram' : hasForm ? 'form' : 'none';"
)
NEW_CONTACT_BLOCK = (
    "  // Contact channels\n"
    "  const email        = row.to_email         || b.email          || '';\n"
    "  const facebookUrl  = row.facebook_url     || b.facebook_url   || '';\n"
    "  const instagramUrl = row.instagram_url    || b.instagram_url  || '';\n"
    "  const formUrl      = row.contact_form_url || b.contact_form_url || '';\n"
    "  const hasEmail     = email.includes('@');\n"
    "  const hasFacebook  = !!facebookUrl.trim();\n"
    "  const hasInstagram = !!instagramUrl.trim();\n"
    "  const hasForm      = !!formUrl.trim();\n"
    "  const hasContact   = hasEmail || hasFacebook || hasInstagram || hasForm;\n"
    "  const bestChannel  = hasEmail ? 'email' : hasFacebook ? 'facebook' : hasInstagram ? 'instagram' : hasForm ? 'form' : 'none';\n"
    "  // Pass 42: hasWebsite + hasPhone added so _mapPanelQualification can read from record\n"
    "  const hasWebsite   = !!(website.trim());\n"
    "  const hasPhone     = !!(phone.replace(/\\D/g,'').length >= 7);"
)

if OLD_CONTACT_BLOCK in src:
    src = src.replace(OLD_CONTACT_BLOCK, NEW_CONTACT_BLOCK, 1)
    changes.append("_leadRecord: hasWebsite + hasPhone added to contact section")
else:
    print("WARNING: _leadRecord contact block not found exactly")

OLD_WORKFLOW_BLOCK = (
    "  // Workflow status\n"
    "  const isSent       = !!(row.sent_at      || '').trim();\n"
    "  const isApproved   = !!(String(row.approved || '').toLowerCase() === 'true') && !isSent;\n"
    "  const isScheduled  = !!(row.send_after   || '').trim() && !isSent;\n"
    "  const isReplied    = !!(String(row.replied  || '').toLowerCase() === 'true');\n"
    "  const isDNC        = !!(String(row.do_not_contact || '').toLowerCase() === 'true');\n"
    "  const draftVersion = row.draft_version   || '';\n"
    "  const isLegacyDraft = !!draftVersion && draftVersion !== 'v9';"
)
NEW_WORKFLOW_BLOCK = (
    "  // Workflow status\n"
    "  const isSent       = !!(row.sent_at      || '').trim();\n"
    "  const isApproved   = !!(String(row.approved || '').toLowerCase() === 'true') && !isSent;\n"
    "  const isScheduled  = !!(row.send_after   || '').trim() && !isSent;\n"
    "  const isReplied    = !!(String(row.replied  || '').toLowerCase() === 'true');\n"
    "  const isDNC        = !!(String(row.do_not_contact || '').toLowerCase() === 'true');\n"
    "  const draftVersion = row.draft_version   || '';\n"
    "  const isLegacyDraft = !!draftVersion && draftVersion !== 'v9';\n"
    "  // Pass 42: isStale + isReadyScheduled added for _queueStateMeta to read from record\n"
    "  const isStale         = !isSent && !!(typeof status_draft_version !== 'undefined' && status_draft_version && draftVersion && draftVersion !== status_draft_version);\n"
    "  const isReadyScheduled = !!(isScheduled && row.is_ready);"
)

if OLD_WORKFLOW_BLOCK in src:
    src = src.replace(OLD_WORKFLOW_BLOCK, NEW_WORKFLOW_BLOCK, 1)
    changes.append("_leadRecord: isStale + isReadyScheduled added to workflow section")
else:
    print("WARNING: _leadRecord workflow block not found exactly")

# Also add hasWebsite, hasPhone to the returned object
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
    changes.append("_leadRecord return: hasWebsite + hasPhone added to returned object")
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
    changes.append("_leadRecord return: isStale + isReadyScheduled added to returned object")
else:
    print("WARNING: _leadRecord return workflow block not found")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Add _leadQualBucket(record, extras) and _leadStatusMeta(record)
#    Inject them after _leadRecord, before _renderLeadWorkspaceHeader
# ─────────────────────────────────────────────────────────────────────────────

SHARED_HELPERS = """
// ═══════════════════════════════════════════════════════════════════════════
// V2 Stage 2E — Shared Qualification + Status Meta Helpers
// Both Discovery and Pipeline derive meaning from these shared helpers.
// ═══════════════════════════════════════════════════════════════════════════

/**
 * _leadQualBucket(record, extras)
 *
 * Qualification bucket classification shared between Discovery and Pipeline.
 * Returns: { key, label, order, tone, reasons }
 *
 * record   — a _leadRecord() result
 * extras   — optional { score, oppScore, rating, reviewCount, contactability }
 *            from biz-object fields not present in queue rows. Pass null/undefined
 *            to use record values only (Pipeline / queue-row context).
 *
 * Bucket keys: 'ready' | 'maybe' | 'needs-contact' | 'weak' | 'closed'
 */
function _leadQualBucket(record, extras) {
  if (!record) return { key: 'weak', label: 'Weak / skip', order: 3, tone: 'weak', reasons: [] };
  const r = record;

  // Merge biz-side extras with record values; record wins if extras absent
  const score    = (extras && extras.score    != null) ? extras.score    : r.priorityScore;
  const oppScore = (extras && extras.oppScore != null) ? extras.oppScore : r.opportunityScore;
  const rating      = (extras && extras.rating      != null) ? extras.rating      : 0;
  const reviewCount = (extras && extras.reviewCount != null) ? extras.reviewCount : 0;
  const contactability = ((extras && extras.contactability) || '').trim().toLowerCase();

  const hasEmail   = r.hasEmail;
  const hasWebsite = r.hasWebsite;
  const hasPhone   = r.hasPhone;
  const isSent     = r.isSent;
  const isApproved = r.isApproved;
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

  if (score >= 4)       reasons.push(`Score ${score}`);
  else if (lowScore)    reasons.push(score ? `Low score ${score}` : 'Low score');
  else if (score === 3) reasons.push('Mid score');

  if (!hasEmail)               reasons.push('Needs email');
  if (!hasWebsite)             reasons.push('No website');
  if (!hasPhone && !hasEmail)  reasons.push('No direct contact');
  if ((rating >= 4.5 && reviewCount >= 20) || (rating >= 4.1 && reviewCount >= 8)) {
    reasons.push(`${rating.toFixed(1)}\\u2605/${Math.round(reviewCount)}`);
  }
  if (highContactability) reasons.push('High contactability');

  return { key, label, order, tone, reasons: Array.from(new Set(reasons)).slice(0, 3) };
}

/**
 * _leadStatusMeta(record)
 *
 * Shared status badge/label/subline/detail/tone derivation.
 * Used by both _queueStateMeta (Pipeline) and any Discovery context needing
 * a status description beyond the simple pill.
 *
 * Returns: { badgeClass, label, title, subline, detail, tone }
 *
 * Note: isReadyScheduled and schedule formatting require row.is_ready and
 * _formatSendAfter. These are read from record.isReadyScheduled and
 * record.sendAfter when available.
 */
function _leadStatusMeta(record) {
  if (!record) return { badgeClass: 'badge-pending', label: 'Pending', title: '', subline: '', detail: '', tone: 'info' };
  const r = record;

  if (r.isReplied) {
    return { badgeClass: 'badge-replied', label: 'Replied', title: 'Reply received', subline: 'Conversation active', detail: 'No send action needed', tone: 'info' };
  }
  if (r.isSent) {
    return { badgeClass: 'badge-sent', label: 'Sent', title: 'Already sent', subline: 'Completed send', detail: 'No further queue action', tone: 'info' };
  }
  if (r.isStale) {
    return { badgeClass: 'badge-stale', label: 'Stale', title: 'Old copy - regenerate before sending', subline: 'Needs refresh before send', detail: 'Draft version is behind current prompt', tone: 'wait' };
  }
  if (r.isScheduled && !r.isReadyScheduled) {
    const relative = r.sendAfter ? (typeof _formatSendAfter === 'function' ? _formatSendAfter(r.sendAfter) : r.sendAfter) : '';
    const exact    = r.sendAfter ? (typeof _formatSendAfterExact === 'function' ? _formatSendAfterExact(r.sendAfter) : r.sendAfter) : '';
    return {
      badgeClass: 'badge-scheduled',
      label: 'Scheduled',
      title: `Scheduled for ${exact || r.sendAfter}`,
      subline: `Waits until ${relative || r.sendAfter}`,
      detail: `${exact} - not in Send Approved yet`,
      tone: 'wait',
    };
  }
  if (r.isReadyScheduled) {
    const exact = r.sendAfter ? (typeof _formatSendAfterExact === 'function' ? _formatSendAfterExact(r.sendAfter) : r.sendAfter) : '';
    return {
      badgeClass: 'badge-ready',
      label: 'Ready Now',
      title: `Scheduled window reached at ${exact || r.sendAfter}`,
      subline: 'Scheduled time reached',
      detail: `${exact} - included in Send Approved now`,
      tone: 'ready',
    };
  }
  if (r.isApproved) {
    return { badgeClass: 'badge-approved', label: 'Approved', title: 'Approved and ready to send now', subline: 'Ready to send now', detail: 'Included in Send Approved immediately', tone: 'ready' };
  }
  return { badgeClass: 'badge-pending', label: 'Pending', title: 'Still needs operator approval', subline: 'Needs approval before send', detail: 'Not in Send Approved yet', tone: 'info' };
}
"""

ANCHOR_WORKSPACE = "// ═══════════════════════════════════════════════════════════════════════════\n// V2 Stage 2B — Unified Workspace Panel Header"
if ANCHOR_WORKSPACE in src:
    src = src.replace(ANCHOR_WORKSPACE, SHARED_HELPERS + ANCHOR_WORKSPACE, 1)
    changes.append("_leadQualBucket + _leadStatusMeta injected before workspace header")
else:
    print("WARNING: Stage 2B header anchor not found")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Wire _queueStateMeta through _leadStatusMeta
#    Replace the full body with a thin wrapper that calls _leadStatusMeta
# ─────────────────────────────────────────────────────────────────────────────

OLD_QUEUE_STATE_META = re.compile(
    r"function _queueStateMeta\(row\) \{.*?^}",
    re.DOTALL | re.MULTILINE
)

NEW_QUEUE_STATE_META = """function _queueStateMeta(row) {
  // Pass 42: delegates to _leadStatusMeta via _leadRecord.
  // Preserves exact same return shape { badgeClass, label, title, subline, detail, tone }.
  // isStale requires status_draft_version (module-level); isReadyScheduled requires row.is_ready.
  // Both are now computed in _leadRecord and readable here.
  const record = _leadRecord(row);
  return _leadStatusMeta(record);
}"""

if OLD_QUEUE_STATE_META.search(src):
    src = OLD_QUEUE_STATE_META.sub(NEW_QUEUE_STATE_META, src, count=1)
    changes.append("_queueStateMeta rewritten as thin wrapper over _leadStatusMeta")
else:
    print("WARNING: _queueStateMeta body not matched")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Wire _mapPanelQualification through _leadRecord + _leadQualBucket
#    Replace the full body with calls that use the shared helpers while
#    still passing biz-only extras (rating, reviewCount, contactability).
# ─────────────────────────────────────────────────────────────────────────────

OLD_QUAL = re.compile(
    r"function _mapPanelQualification\(item, qrow\) \{.*?^}",
    re.DOTALL | re.MULTILINE
)

NEW_QUAL = """function _mapPanelQualification(item, qrow) {
  // Pass 42: delegates to _leadQualBucket via _leadRecord.
  // Biz-only extras (rating, reviewCount, contactability) are passed through
  // since they are not present in queue rows.
  const record = qrow ? _leadRecord(qrow) : _leadRecord({ name: item.biz.name || '', city: item.biz.city || '' });

  // Merge biz-side contact/score overrides with record for accuracy
  // (biz object may have fresher email/website/phone than the queue row in some discovery runs)
  const merged = Object.assign({}, record, {
    hasEmail:   !!(( item.biz.email || record.email || '').trim().includes('@')),
    hasWebsite: !!(( item.biz.website || record.website || '').trim()),
    hasPhone:   !!(( item.biz.phone  || record.phone  || '').replace(/\\D/g,'').length >= 7),
    priorityScore:    _mapPanelItemScore(item, qrow),
    opportunityScore: _mapPanelNumber(
      qrow && (qrow.opp_score ?? qrow.opportunity_score),
      item.biz.opp_score ?? item.biz.opportunity_score
    ),
  });

  const extras = {
    score:           merged.priorityScore,
    oppScore:        merged.opportunityScore,
    rating:          _mapPanelNumber(qrow && qrow.rating, item.biz.rating),
    reviewCount:     _mapPanelNumber(
      qrow && (qrow.review_count ?? qrow.reviews),
      item.biz.review_count ?? item.biz.reviews
    ),
    contactability:  String((qrow && qrow.contactability) || item.biz.contactability || ''),
  };

  const bucket = _leadQualBucket(merged, extras);

  // Return shape compatible with all existing callers
  return {
    key:         bucket.key,
    label:       bucket.label,
    order:       bucket.order,
    tone:        bucket.tone,
    hasEmail:    merged.hasEmail,
    hasWebsite:  merged.hasWebsite,
    hasPhone:    merged.hasPhone,
    score:       merged.priorityScore,
    lowScore:    merged.priorityScore > 0 && merged.priorityScore <= 2,
    isSent:      merged.isSent,
    isApproved:  merged.isApproved,
    isScheduled: merged.isScheduled,
    reasons:     bucket.reasons,
  };
}"""

if OLD_QUAL.search(src):
    src = OLD_QUAL.sub(NEW_QUAL, src, count=1)
    changes.append("_mapPanelQualification rewritten as thin wrapper over _leadRecord + _leadQualBucket")
else:
    print("WARNING: _mapPanelQualification body not matched")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Write
# ─────────────────────────────────────────────────────────────────────────────

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\n{len(changes)}/8 target changes applied:")
for c in changes:
    print(f"  + {c}")
print(f"File: {original_len} -> {len(src)} chars (+{len(src)-original_len})")
