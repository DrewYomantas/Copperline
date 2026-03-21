"""
V2 Stage 2 patch — Unified Lead Record Backbone + Workspace Panel header.
Adds _leadKey, _leadRecord, _leadResolve, _renderLeadWorkspaceHeader.
Wires shared header into mrp-modal and fillPanel.
Pure additive JS injection into index.html.
"""
import re, os

PATH = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

original_len = len(src)
changes = []

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2A — Core backbone: _leadKey, _leadRecord, _leadResolve
# Inject immediately after _mapBizRunKey (line ~6013) which is the last
# key-related utility before the grid planning functions.
# ─────────────────────────────────────────────────────────────────────────────

BACKBONE = r"""
// ═══════════════════════════════════════════════════════════════════════════
// V2 Stage 2A — Unified Lead Record Backbone
// Gives Discovery and Pipeline a single canonical record shape for a business.
// ═══════════════════════════════════════════════════════════════════════════

/**
 * _leadKey(input) — stable identity key from either a biz object or a queue row.
 * Priority: place_id → website → phone → name+city.
 * Produces the same key regardless of which side the input comes from.
 */
function _leadKey(input) {
  if (!input) return '';
  // place_id: only on biz objects from map results
  const placeId = (input.place_id || '').trim();
  if (placeId) return 'pid:' + placeId.toLowerCase();
  // website: normalize to bare host+path, present on both biz and queue row
  const rawSite = input.website || '';
  const normSite = _mapNormalizeWebsite ? _mapNormalizeWebsite(rawSite) : rawSite.toLowerCase().replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '');
  if (normSite) return 'web:' + normSite;
  // phone: normalize to digits
  const rawPhone = input.phone || '';
  const normPhone = _mapNormalizePhone ? _mapNormalizePhone(rawPhone) : rawPhone.replace(/\D/g, '');
  if (normPhone && normPhone.length >= 7) return 'phone:' + normPhone;
  // name+city fallback
  const name = (input.name || input.business_name || '').trim().toLowerCase().replace(/\s+/g, ' ');
  const city = (input.city || '').trim().toLowerCase();
  return 'nc:' + name + '|' + city;
}

/**
 * _leadResolve(input) — returns { biz, qrow, key } from either a biz object or queue row.
 * Populates whichever half is missing. Never mutates either object.
 */
function _leadResolve(input) {
  if (!input) return { biz: null, qrow: null, key: '' };
  const isBiz = !!(input.name || (!input.business_name && input.lat !== undefined));
  const isRow = !!(input.business_name !== undefined && !isBiz) || !!(input.subject !== undefined);

  let biz  = isBiz  ? input : null;
  let qrow = !isBiz ? input : null;

  // Resolve biz → qrow via allRows lookup
  if (biz && !qrow && typeof _mrpResolveRow === 'function') {
    qrow = _mrpResolveRow(biz);
  }
  // Resolve qrow → biz: synthesize a minimal biz shape from the queue row
  if (!biz && qrow) {
    biz = {
      name:           qrow.business_name || '',
      city:           qrow.city          || '',
      website:        qrow.website        || '',
      phone:          qrow.phone          || '',
      email:          qrow.to_email       || '',
      facebook_url:   qrow.facebook_url   || '',
      instagram_url:  qrow.instagram_url  || '',
      contact_form_url: qrow.contact_form_url || '',
      industry:       qrow.industry       || '',
      lat: null, lng: null, place_id: '',
    };
  }

  const key = _leadKey(biz || qrow);
  return { biz, qrow, key };
}

/**
 * _leadRecord(input) — canonical normalized record from either input type.
 * Returns one flat object covering all six concerns:
 *   identity, contact, qualification, workflow status, draft, history.
 * Safe to call with null — returns an empty record.
 */
function _leadRecord(input) {
  const { biz, qrow } = _leadResolve(input);
  const row = qrow || {};
  const b   = biz  || {};

  // Identity
  const name     = row.business_name || b.name         || '';
  const city     = row.city          || b.city          || '';
  const state    = row.state         || b.state         || '';
  const website  = row.website       || b.website       || '';
  const phone    = row.phone         || b.phone         || '';
  const industry = row.industry      || b.industry      || '';

  // Contact channels
  const email        = row.to_email         || b.email          || '';
  const facebookUrl  = row.facebook_url     || b.facebook_url   || '';
  const instagramUrl = row.instagram_url    || b.instagram_url  || '';
  const formUrl      = row.contact_form_url || b.contact_form_url || '';
  const hasEmail     = email.includes('@');
  const hasFacebook  = !!facebookUrl.trim();
  const hasInstagram = !!instagramUrl.trim();
  const hasForm      = !!formUrl.trim();
  const hasContact   = hasEmail || hasFacebook || hasInstagram || hasForm;
  const bestChannel  = hasEmail ? 'email' : hasFacebook ? 'facebook' : hasInstagram ? 'instagram' : hasForm ? 'form' : 'none';

  // Qualification
  const priorityScore  = parseInt(row.final_priority_score  || b.priority_score  || b.score || 0) || 0;
  const opportunityScore = parseInt(row.opportunity_score   || b.opp_score       || 0) || 0;
  const scoringReason  = row.scoring_reason || '';

  // Workflow status
  const isSent       = !!(row.sent_at      || '').trim();
  const isApproved   = !!(String(row.approved || '').toLowerCase() === 'true') && !isSent;
  const isScheduled  = !!(row.send_after   || '').trim() && !isSent;
  const isReplied    = !!(String(row.replied  || '').toLowerCase() === 'true');
  const isDNC        = !!(String(row.do_not_contact || '').toLowerCase() === 'true');
  const draftVersion = row.draft_version   || '';
  const isLegacyDraft = !!draftVersion && draftVersion !== 'v9';

  // Compute primary status label
  let status, statusTone;
  if (isDNC)        { status = 'Do Not Contact'; statusTone = 'blocked'; }
  else if (isSent && isReplied) { status = 'Replied';     statusTone = 'replied'; }
  else if (isSent)  { status = 'Sent';           statusTone = 'sent'; }
  else if (isScheduled) { status = 'Scheduled';  statusTone = 'scheduled'; }
  else if (isApproved)  { status = 'Approved';   statusTone = 'approved'; }
  else if (row.subject) { status = 'Drafted';    statusTone = 'drafted'; }
  else              { status = 'Discovered';     statusTone = 'new'; }

  // Next recommended action
  let nextAction = '';
  if (isDNC) nextAction = '';
  else if (isSent && isReplied) nextAction = 'Manage reply';
  else if (isSent) nextAction = 'Wait for reply';
  else if (isScheduled) nextAction = 'Sending ' + (row.send_after ? _formatSendAfter(row.send_after) : 'soon');
  else if (isApproved && hasEmail) nextAction = 'Send email';
  else if (isApproved) nextAction = 'Send via ' + bestChannel;
  else if (row.subject && isLegacyDraft) nextAction = 'Add observation + regenerate draft';
  else if (row.subject && !row.business_specific_observation) nextAction = 'Add observation + regenerate draft';
  else if (row.subject) nextAction = 'Review + approve';
  else if (!hasContact) nextAction = 'Find contact info';
  else nextAction = 'Generate draft';

  // Draft
  const subject         = row.subject              || '';
  const body            = row.body                 || '';
  const facebookDraft   = row.facebook_dm_draft    || row.social_dm_text || '';
  const observation     = row.business_specific_observation || '';

  // History markers
  const sentAt            = row.sent_at              || '';
  const repliedAt         = row.replied_at           || '';
  const replySnippet      = row.reply_snippet        || '';
  const contactAttempts   = parseInt(row.contact_attempt_count || 0) || 0;
  const lastContactedAt   = row.last_contacted_at    || '';
  const sendAfter         = row.send_after            || '';
  const messageId         = row.message_id            || '';
  const conversationNotes = row.conversation_notes    || '';
  const nextStep          = row.conversation_next_step || '';
  const rowIndex          = row.index !== undefined ? row.index : (Array.isArray(allRows) ? allRows.indexOf(row) : -1);

  return {
    // Identity
    name, city, state, website, phone, industry,
    // Contact
    email, facebookUrl, instagramUrl, formUrl,
    hasEmail, hasFacebook, hasInstagram, hasForm, hasContact, bestChannel,
    // Qualification
    priorityScore, opportunityScore, scoringReason,
    // Workflow status
    isSent, isApproved, isScheduled, isReplied, isDNC, isLegacyDraft,
    status, statusTone, draftVersion, nextAction,
    // Draft
    subject, body, facebookDraft, observation,
    // History
    sentAt, repliedAt, replySnippet, contactAttempts, lastContactedAt,
    sendAfter, messageId, conversationNotes, nextStep,
    // Internal refs
    rowIndex,
    _qrow: qrow,
    _biz:  biz,
  };
}
"""

# Inject after the closing brace of _mapBizRunKey
ANCHOR = "function _mapCurrentResultKeySet() {"
if ANCHOR in src:
    src = src.replace(ANCHOR, BACKBONE + ANCHOR, 1)
    changes.append("Stage 2A: _leadKey + _leadRecord + _leadResolve injected after _mapBizRunKey")
else:
    print("WARNING: _mapCurrentResultKeySet anchor not found")

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2B — Shared workspace header renderer
# ─────────────────────────────────────────────────────────────────────────────

WORKSPACE_HEADER = r"""
// ═══════════════════════════════════════════════════════════════════════════
// V2 Stage 2B — Unified Workspace Header
// Single renderer for business identity + status + channels + next action.
// Used by both mrp-modal and the Pipeline panel (fillPanel).
// ═══════════════════════════════════════════════════════════════════════════

const _STATUS_TONE_STYLES = {
  replied:   'background:rgba(184,115,51,.18);color:var(--copper);border:1px solid rgba(184,115,51,.3)',
  sent:      'background:rgba(62,207,114,.12);color:var(--green);border:1px solid rgba(62,207,114,.2)',
  scheduled: 'background:rgba(245,166,35,.13);color:var(--amber);border:1px solid rgba(245,166,35,.25)',
  approved:  'background:rgba(79,142,247,.12);color:var(--blue);border:1px solid rgba(79,142,247,.2)',
  drafted:   'background:var(--surface3);color:var(--muted);border:1px solid var(--border)',
  new:       'background:var(--surface3);color:var(--muted);border:1px solid var(--border)',
  blocked:   'background:rgba(231,76,60,.12);color:#e74c3c;border:1px solid rgba(231,76,60,.2)',
};

/**
 * _renderLeadWorkspaceHeader(record) — returns an HTML string.
 * Renders: name, city/state/industry, status badge, contact channels,
 * priority score, observation hint, next action.
 * Compact and scannable. Does not include edit controls.
 */
function _renderLeadWorkspaceHeader(record) {
  if (!record) return '';
  const r = record;
  const esc = typeof escHtml === 'function' ? escHtml : v => String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // Status badge
  const toneStyle = _STATUS_TONE_STYLES[r.statusTone] || _STATUS_TONE_STYLES.new;
  const statusBadge = `<span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;letter-spacing:.04em;${toneStyle}">${esc(r.status)}</span>`;

  // Channel badges
  const chParts = [];
  if (r.hasEmail)     chParts.push(`<span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;background:var(--surface3);border:1px solid var(--border);color:var(--muted)">✉ Email</span>`);
  if (r.hasFacebook)  chParts.push(`<a href="${esc(r.facebookUrl)}" target="_blank" style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;background:rgba(66,103,178,.15);border:1px solid rgba(66,103,178,.25);color:#7b9fd4;text-decoration:none">f FB</a>`);
  if (r.hasInstagram) chParts.push(`<a href="${esc(r.instagramUrl)}" target="_blank" style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;background:rgba(188,42,141,.12);border:1px solid rgba(188,42,141,.2);color:#c06;text-decoration:none">◎ IG</a>`);
  if (r.hasForm)      chParts.push(`<a href="${esc(r.formUrl)}" target="_blank" style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;background:var(--surface3);border:1px solid var(--border);color:var(--muted);text-decoration:none">⊟ Form</a>`);
  if (!r.hasContact)  chParts.push(`<span style="font-size:9px;color:var(--dim)">No channel found</span>`);
  const channels = chParts.join(' ');

  // Score chip
  const scoreHtml = r.priorityScore
    ? `<span style="display:inline-block;padding:1px 7px;border-radius:3px;font-size:10px;font-weight:700;background:var(--surface3);border:1px solid var(--border);color:var(--text);font-family:var(--mono)" title="${esc(r.scoringReason)}">★ ${r.priorityScore}</span>`
    : '';

  // Industry
  const industryHtml = r.industry
    ? `<span style="font-size:10px;color:var(--muted);margin-left:4px">${esc(r.industry)}</span>`
    : '';

  // Next action
  const nextHtml = r.nextAction
    ? `<div style="margin-top:5px;font-size:10px;color:var(--muted)">Next: <strong style="color:var(--text)">${esc(r.nextAction)}</strong></div>`
    : '';

  // Observation hint (compact — just a tag if present)
  const obsHtml = r.observation
    ? `<span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;background:rgba(184,115,51,.1);border:1px solid rgba(184,115,51,.2);color:var(--copper);margin-left:4px" title="${esc(r.observation)}">obs</span>`
    : '';

  return `<div class="lws-header" style="padding:0 0 8px">
    <div style="display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;margin-bottom:3px">
      ${statusBadge}
      ${scoreHtml}
      ${obsHtml}
    </div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">
      ${esc(r.city)}${r.state ? ', ' + esc(r.state) : ''}${industryHtml}
    </div>
    <div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">
      ${channels}
    </div>
    ${nextHtml}
  </div>`;
}
"""

# Inject before the first occurrence of function _panelMakeKey
ANCHOR2 = "function _panelMakeKey(row) {"
if ANCHOR2 in src:
    src = src.replace(ANCHOR2, WORKSPACE_HEADER + ANCHOR2, 1)
    changes.append("Stage 2B: _renderLeadWorkspaceHeader + _STATUS_TONE_STYLES injected")
else:
    print("WARNING: _panelMakeKey anchor not found")

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2B — Wire shared header into fillPanel (Pipeline panel)
# Replace the current panel-meta innerHTML build (city/phone/website) with a
# call that builds the same meta + adds the status/channels/next-action strip.
# The existing panel-meta div is kept; we just enrich it.
# ─────────────────────────────────────────────────────────────────────────────

OLD_META = re.compile(
    r"(  const parts = \[\];\s*\n)"
    r"(  if \(row\.city\) parts\.push.*?\n)"
    r"(  if \(row\.phone\) parts\.push.*?\n)"
    r"(  if \(row\.website\) parts\.push.*?\n)"
    r"(  if \(row\.scan_note\) parts\.push.*?\n)"
    r"  document\.getElementById\('panel-meta'\)\.innerHTML = parts\.join\(''\);",
    re.DOTALL
)
NEW_META = (
    "  // V2 Stage 2B: build shared workspace header from unified record\n"
    "  const _lwsRecord = _leadRecord(row);\n"
    "  const _lwsMeta = document.getElementById('panel-meta');\n"
    "  if (_lwsMeta) {\n"
    "    const parts = [];\n"
    "    if (row.city) parts.push(`<span>📍 ${escHtml(row.city)}, ${escHtml(row.state)}</span>`);\n"
    "    if (row.phone) parts.push(`<span>📞 ${escHtml(row.phone)}</span>`);\n"
    "    if (row.website) parts.push(`<span>🌐 <a href=\"${escHtml(row.website)}\" target=\"_blank\">${escHtml(row.website)}</a></span>`);\n"
    "    if (row.scan_note) parts.push(`<span style=\"color:var(--dim);font-style:italic;font-size:11px\">🔍 ${escHtml(row.scan_note)}</span>`);\n"
    "    _lwsMeta.innerHTML = _renderLeadWorkspaceHeader(_lwsRecord) + parts.join('');\n"
    "  }"
)

if OLD_META.search(src):
    src = OLD_META.sub(NEW_META, src, count=1)
    changes.append("Stage 2B: fillPanel panel-meta wired through _renderLeadWorkspaceHeader")
else:
    print("WARNING: panel-meta build pattern not matched — trying simpler injection")
    # Simpler fallback: just inject the header call right after document.getElementById('panel-meta').innerHTML
    SIMPLE_ANCHOR = "  document.getElementById('panel-meta').innerHTML = parts.join('');"
    if SIMPLE_ANCHOR in src:
        src = src.replace(
            SIMPLE_ANCHOR,
            "  document.getElementById('panel-meta').innerHTML = _renderLeadWorkspaceHeader(_leadRecord(row)) + parts.join('');",
            1
        )
        changes.append("Stage 2B: fillPanel panel-meta wired (simple injection)")
    else:
        print("WARNING: panel-meta simple anchor not found either")

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2B — Wire shared header into mrp-modal header block (_mrpPreview)
# The modal currently only shows title + email in the header.
# We add the workspace header strip below the title row.
# ─────────────────────────────────────────────────────────────────────────────

OLD_MODAL_HEADER = (
    "  document.getElementById('mrp-modal-title').textContent = bizName;\n"
    "  document.getElementById('mrp-modal-sub').textContent   = email;"
)
NEW_MODAL_HEADER = (
    "  document.getElementById('mrp-modal-title').textContent = bizName;\n"
    "  document.getElementById('mrp-modal-sub').textContent   = email;\n"
    "  // V2 Stage 2B: inject unified workspace header into modal\n"
    "  const _mrpHdrEl = document.getElementById('mrp-modal-lws-header');\n"
    "  if (_mrpHdrEl) {\n"
    "    const _mrpRecord = _leadRecord(qrow || { business_name: bizName, to_email: email });\n"
    "    _mrpHdrEl.innerHTML = _renderLeadWorkspaceHeader(_mrpRecord);\n"
    "  }"
)
if OLD_MODAL_HEADER in src:
    src = src.replace(OLD_MODAL_HEADER, NEW_MODAL_HEADER, 1)
    changes.append("Stage 2B: _mrpPreview header wired through _renderLeadWorkspaceHeader")
else:
    print("WARNING: mrp-modal-title textContent anchor not found")

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2B — Add lws-header div to mrp-modal HTML
# Insert after the mrp-modal-sub div in the modal header section.
# ─────────────────────────────────────────────────────────────────────────────

OLD_MODAL_HTML = (
    '        <div class="mrp-modal-title" id="mrp-modal-title"></div>\n'
    '        <div class="mrp-modal-sub" id="mrp-modal-sub"></div>'
)
NEW_MODAL_HTML = (
    '        <div class="mrp-modal-title" id="mrp-modal-title"></div>\n'
    '        <div class="mrp-modal-sub" id="mrp-modal-sub"></div>\n'
    '        <div id="mrp-modal-lws-header" style="margin-top:6px"></div>'
)
if OLD_MODAL_HTML in src:
    src = src.replace(OLD_MODAL_HTML, NEW_MODAL_HTML, 1)
    changes.append("Stage 2B: mrp-modal-lws-header div added to modal HTML")
else:
    print("WARNING: mrp-modal HTML title+sub anchor not found")

# ─────────────────────────────────────────────────────────────────────────────
# Write
# ─────────────────────────────────────────────────────────────────────────────

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\n{len(changes)}/{len(changes)} changes applied:")
for c in changes:
    print(f"  + {c}")
print(f"File: {original_len} -> {len(src)} chars (+{len(src)-original_len})")
