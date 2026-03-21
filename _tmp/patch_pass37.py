import re, sys

PATH = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

original_len = len(src)
changes = []

# ---------------------------------------------------------------------------
# 1. panelApprove + panelUnapprove -- add pending state + inject helpers
# ---------------------------------------------------------------------------
OLD1 = re.compile(
    r'async function panelApprove\(\) \{.*?toast\(\'Approved [^)]*\);\s*\}',
    re.DOTALL
)
NEW1 = """// Pass 37 -- pending-state helpers
function _btnPending(btn, label) {
  if (!btn) return; btn.disabled = true; btn._p37label = btn.textContent; btn.textContent = label;
}
function _btnRestore(btn) {
  if (!btn) return; btn.disabled = false;
  if (btn._p37label !== undefined) { btn.textContent = btn._p37label; delete btn._p37label; }
}

async function panelApprove() {
  const row = _panelCurrentRow(); if (!row) return;
  if (!row.to_email) { toast('Add a To Email first','err'); return; }
  const gi = allRows.indexOf(row);
  const btn = document.getElementById('panel-approve-btn');
  _btnPending(btn, 'Approving...');
  try {
    await api('/api/approve_row',{index:gi});
    row.approved='true'; fillPanel(row,panelIdx,_panelCurrentRows().length); renderTable(); loadStats();
    toast('Approved','ok');
  } catch(e) { toast('Approve failed','err'); }
  _btnRestore(btn);
}"""
m = OLD1.search(src)
if m:
    src = src[:m.start()] + NEW1 + src[m.end():]
    changes.append("panelApprove -- pending state + helpers")
else:
    print("WARNING: panelApprove not matched")

# ---------------------------------------------------------------------------
# 2. panelUnapprove -- add pending state
# ---------------------------------------------------------------------------
OLD2 = re.compile(
    r'async function panelUnapprove\(\) \{.*?toast\(\'Approval removed[^)]*\);\s*\}',
    re.DOTALL
)
NEW2 = """async function panelUnapprove() {
  const row = _panelCurrentRow(); if (!row) return;
  const gi = allRows.indexOf(row);
  const btn = document.getElementById('panel-unapprove-btn');
  _btnPending(btn, 'Removing...');
  try {
    await api('/api/unapprove_row',{index:gi});
    row.approved='false'; fillPanel(row,panelIdx,_panelCurrentRows().length); renderTable(); loadStats();
    toast('Approval removed -- back to pending review','info');
  } catch(e) { toast('Unapprove failed','err'); }
  _btnRestore(btn);
}"""
m = OLD2.search(src)
if m:
    src = src[:m.start()] + NEW2 + src[m.end():]
    changes.append("panelUnapprove -- pending state")
else:
    print("WARNING: panelUnapprove not matched")

# ---------------------------------------------------------------------------
# 3. mrp-modal HTML -- replace pre/div body with editable textarea + input
# ---------------------------------------------------------------------------
OLD3 = re.compile(
    r'<div class="mrp-modal-body">.*?</div>\s*<div class="mrp-modal-ftr" id="mrp-modal-ftr"></div>',
    re.DOTALL
)
NEW3 = """<div class="mrp-modal-body">
      <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:4px">Subject</div>
      <input id="mrp-modal-subject-input" type="text" style="width:100%;box-sizing:border-box;background:var(--surface2);border:1px solid var(--border);border-radius:var(--rs);color:var(--text);font-size:12px;padding:6px 9px;margin-bottom:10px;font-family:var(--sans)">
      <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:4px">Message</div>
      <textarea id="mrp-modal-email-body" style="width:100%;box-sizing:border-box;background:var(--surface2);border:1px solid var(--border);border-radius:var(--rs);color:var(--text);font-size:12px;padding:8px 9px;font-family:var(--mono,monospace);line-height:1.6;resize:vertical;min-height:140px"></textarea>
      <div id="mrp-modal-save-status" style="font-size:10px;color:var(--muted);margin-top:5px;min-height:14px"></div>
    </div>
    <div class="mrp-modal-ftr" id="mrp-modal-ftr"></div>"""
m = OLD3.search(src)
if m:
    src = src[:m.start()] + NEW3 + src[m.end():]
    changes.append("mrp-modal HTML -- editable subject input + textarea")
else:
    print("WARNING: mrp-modal HTML not matched")

# ---------------------------------------------------------------------------
# 4. _mrpPreview -- full replacement with editable + save + unschedule
# ---------------------------------------------------------------------------
OLD4 = re.compile(
    r'// Pass 24 [^\n]*\nfunction _mrpPreview\(biz, qrow\) \{.*?\nfunction _mrpModalClose',
    re.DOTALL
)
NEW4 = """// Pass 24/37 -- inline preview: editable subject/body, save, unschedule
function _mrpPreview(biz, qrow) {
  const modal = document.getElementById('mrp-modal');
  if (!modal) return;
  const email     = qrow.to_email || biz.email || '(no email)';
  const idx       = qrow.index;
  const bizName   = biz.name;
  const isSent    = !!(qrow.sent_at || '').trim();
  const isApproved  = (qrow.approved || '').toLowerCase() === 'true';
  const isScheduled = !!(qrow.send_after || '').trim() && !isSent;

  document.getElementById('mrp-modal-title').textContent = bizName;
  document.getElementById('mrp-modal-sub').textContent   = email;

  const subInp = document.getElementById('mrp-modal-subject-input');
  const bodyTa = document.getElementById('mrp-modal-email-body');
  const saveStatus = document.getElementById('mrp-modal-save-status');

  if (subInp) { subInp.value = qrow.subject || ''; subInp.disabled = isSent; }
  if (bodyTa) { bodyTa.value = qrow.body    || ''; bodyTa.disabled = isSent; }
  if (saveStatus) saveStatus.textContent = '';

  const ftr = document.getElementById('mrp-modal-ftr');
  ftr.innerHTML = '';

  if (!isSent) {
    const btnSave = document.createElement('button');
    btnSave.className = 'btn btn-secondary';
    btnSave.style.fontSize = '12px';
    btnSave.textContent = 'Save Edits';
    btnSave.onclick = async () => {
      const newSubj = subInp ? subInp.value.trim() : '';
      const newBody = bodyTa ? bodyTa.value : '';
      if (!newSubj) { if (saveStatus) saveStatus.textContent = 'Subject cannot be empty.'; return; }
      _btnPending(btnSave, 'Saving...');
      if (saveStatus) saveStatus.textContent = '';
      try {
        const res = await api('/api/update_row', { index: idx, updates: { subject: newSubj, body: newBody } });
        if (!res || res.ok === false) { if (saveStatus) saveStatus.textContent = 'Save failed.'; }
        else {
          qrow.subject = newSubj; qrow.body = newBody;
          await loadAll(); _mapRenderPanel();
          if (saveStatus) saveStatus.textContent = 'Saved.';
          setTimeout(() => { if (saveStatus) saveStatus.textContent = ''; }, 2000);
        }
      } catch(e) { if (saveStatus) saveStatus.textContent = 'Save error.'; }
      _btnRestore(btnSave);
    };
    ftr.appendChild(btnSave);

    if (!isApproved) {
      const btnA = document.createElement('button');
      btnA.className = 'btn btn-success'; btnA.style.fontSize = '12px'; btnA.textContent = 'Approve';
      btnA.onclick = async () => {
        _btnPending(btnA, 'Approving...');
        await _mrpApprove(biz, idx);
        _mrpModalClose();
      };
      ftr.appendChild(btnA);
    }

    if (isScheduled) {
      const btnU = document.createElement('button');
      btnU.className = 'btn btn-ghost'; btnU.style.fontSize = '12px'; btnU.textContent = 'Unschedule';
      btnU.onclick = async () => {
        _btnPending(btnU, 'Removing...');
        try {
          await api('/api/schedule_email', { index: idx, business_name: bizName, send_after: '' });
          qrow.send_after = ''; await loadAll(); _mapRenderPanel();
          toast('Unscheduled -- back in ready-now queue', 'ok');
          _mrpModalClose();
        } catch(e) { toast('Unschedule failed','err'); }
        _btnRestore(btnU);
      };
      ftr.appendChild(btnU);
    } else {
      const btnS = document.createElement('button');
      btnS.className = 'btn btn-ghost'; btnS.style.fontSize = '12px'; btnS.textContent = 'Schedule Tomorrow';
      btnS.onclick = async () => {
        _btnPending(btnS, 'Scheduling...');
        await _mrpSchedule(biz, idx);
        _btnRestore(btnS); _mrpModalClose();
      };
      ftr.appendChild(btnS);
    }

    const btnD = document.createElement('button');
    btnD.className = 'btn btn-danger'; btnD.style.fontSize = '12px'; btnD.textContent = 'Delete';
    btnD.onclick = async () => {
      if (!confirm('Delete "' + bizName + '"?')) return;
      await api('/api/delete_row', { index: idx });
      await loadAll(); _mapRenderPanel(); _mrpModalClose();
    };
    ftr.appendChild(btnD);
  }

  const btnClose = document.createElement('button');
  btnClose.className = 'btn btn-ghost'; btnClose.style.fontSize = '12px'; btnClose.textContent = 'Close';
  btnClose.onclick = _mrpModalClose;
  ftr.appendChild(btnClose);

  modal.classList.add('open');
}

function _mrpModalClose"""
m = OLD4.search(src)
if m:
    src = src[:m.start()] + NEW4 + src[m.end() - len("function _mrpModalClose"):]
    changes.append("_mrpPreview -- editable + Save + Unschedule")
else:
    print("WARNING: _mrpPreview pattern not matched")

# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nDone. {len(changes)}/4 changes applied:")
for ch in changes:
    print(f"  + {ch}")
print(f"File: {original_len} -> {len(src)} chars")
