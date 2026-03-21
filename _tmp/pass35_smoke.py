import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda err: errors.append(str(err)))
    page.goto('http://127.0.0.1:5000', wait_until='domcontentloaded')
    page.wait_for_selector('#panel-overlay')
    page.wait_for_timeout(1200)
    page.evaluate("""
    () => {
      const mk = (name, extra = {}) => ({
        business_name: name,
        city: 'Austin',
        state: 'TX',
        industry: 'hvac',
        website: 'https://example.com',
        phone: '555-111-2222',
        score: '88',
        final_priority_score: '4',
        subject: `Subject for ${name}`,
        body: `Body for ${name}`,
        to_email: `${name.toLowerCase().replace(/[^a-z0-9]+/g, '')}@example.com`,
        approved: 'false',
        send_after: '',
        sent_at: '',
        replied: 'false',
        draft_version: status_draft_version || 'v1',
        do_not_contact: 'false',
        is_ready: false,
        ...extra,
      });
      loadAll = async () => {};
      loadStats = async () => {};
      switchPage = () => {};
      confirm = () => true;
      toast = (msg, type) => { window.__toasts = window.__toasts || []; window.__toasts.push({ msg, type }); };
      api = async (path, body = {}) => {
        window.__apiCalls = window.__apiCalls || [];
        window.__apiCalls.push({ path, body });
        const idx = body.index;
        const row = Number.isInteger(idx) ? allRows[idx] : null;
        if (path === '/api/approve_row') {
          if (row) row.approved = 'true';
          return { ok: true };
        }
        if (path === '/api/unapprove_row') {
          if (row) row.approved = 'false';
          return { ok: true };
        }
        if (path === '/api/schedule_email') {
          if (!row) return { ok: true, send_after: '' };
          if (Object.prototype.hasOwnProperty.call(body, 'send_after')) {
            row.send_after = body.send_after || '';
            row.is_ready = false;
            return { ok: true, send_after: row.send_after };
          }
          row.send_after = body.days_ahead === 1 ? '2026-03-18T07:30:00' : '2026-03-19T07:30:00';
          row.is_ready = false;
          return { ok: true, send_after: row.send_after };
        }
        return { ok: true };
      };

      allRows = [
        mk('Alpha HVAC', { approved: 'true', is_ready: false }),
        mk('Bravo Plumbing', { approved: 'true', send_after: '2026-03-18T07:30:00', is_ready: false }),
        mk('Charlie Electric', { approved: 'true', send_after: '2026-03-17T07:30:00', is_ready: true }),
        mk('Delta Roofing', { approved: 'false', to_email: '', is_ready: false }),
        mk('Echo Garage', { sent_at: '2026-03-16T10:00:00', approved: 'true', is_ready: false }),
      ];
      filteredRows = [];
      currentFilter = 'approved';
      renderTable();
    }
    """)

    body_text = page.locator('body').text_content() or ''
    assert 'Search Area Grid' in body_text

    note_text = page.locator('#queue-timeline-note').text_content() or ''
    assert 'Approved queue:' in note_text, note_text

    status_text = page.locator('tbody tr').first.locator('.td-status').text_content() or ''
    assert 'Approved' in status_text and 'Ready to send now' in status_text, status_text

    page.evaluate("setFilter('scheduled', document.querySelector('[data-filter=scheduled]'))")
    page.wait_for_timeout(100)
    sched_note = page.locator('#queue-timeline-note').text_content() or ''
    assert 'Scheduled queue:' in sched_note and 'Tomorrow morning' in sched_note, sched_note

    row_texts = page.locator('tbody tr .td-status').all_text_contents()
    assert any('Scheduled' in txt and 'Waits until' in txt for txt in row_texts), row_texts
    assert any('Ready Now' in txt and 'Scheduled time reached' in txt for txt in row_texts), row_texts

    page.evaluate("openPanel(Math.max(0, filteredRows.findIndex(r => !r.is_ready)), filteredRows, 'Schedule clarity smoke')")
    page.wait_for_timeout(120)
    panel_info = page.locator('#panel-schedule-info').text_content() or ''
    assert 'Scheduled for' in panel_info and 'stays out of Send Approved' in panel_info, panel_info

    page.locator('#panel-schedule-info .btn-sched-act').first.click()
    page.wait_for_timeout(120)
    panel_info_after_unschedule = page.locator('#panel-schedule-info').text_content() or ''
    assert 'Ready to send now' in panel_info_after_unschedule, panel_info_after_unschedule

    page.evaluate("setFilter('approved', document.querySelector('[data-filter=approved]'))")
    page.wait_for_timeout(100)
    page.evaluate("openPanel(0, filteredRows, 'Schedule clarity smoke')")
    page.wait_for_timeout(120)
    button_text = page.locator('#panel-schedule-btn').text_content() or ''
    assert 'Tomorrow Morning' in button_text, button_text
    page.locator('#panel-schedule-btn').click()
    page.wait_for_timeout(120)
    panel_info_after_schedule = page.locator('#panel-schedule-info').text_content() or ''
    assert 'Scheduled for' in panel_info_after_schedule, panel_info_after_schedule

    state = page.evaluate("""
    () => ({
      rows: allRows.map(r => ({ name: r.business_name, approved: r.approved, send_after: r.send_after, is_ready: !!r.is_ready })),
      lastToast: (window.__toasts || []).slice(-1)[0] || null,
      timelineNote: document.getElementById('queue-timeline-note')?.textContent || '',
    })
    """)

    assert state['rows'][0]['send_after'] == '2026-03-18T07:30:00', state
    assert state['rows'][1]['send_after'] == '', state
    assert state['lastToast'] and 'waits until that time' in state['lastToast']['msg'], state
    assert not errors, errors

    print('PASS35_SMOKE_OK')
    print(json.dumps(state, indent=2))
    browser.close()

