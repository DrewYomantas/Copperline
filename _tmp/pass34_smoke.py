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
        subject: `Subject for ${name}`,
        body: `Body for ${name}`,
        to_email: `${name.toLowerCase().replace(/[^a-z0-9]+/g, '')}@example.com`,
        approved: 'false',
        send_after: '',
        sent_at: '',
        do_not_contact: 'false',
        ...extra,
      });
      loadAll = async () => {};
      toast = (msg, type) => { window.__toasts = window.__toasts || []; window.__toasts.push({ msg, type }); };
      loadStats = async () => {};
      switchPage = () => {};
      confirm = () => true;
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
          if (row) {
            if (Object.prototype.hasOwnProperty.call(body, 'send_after')) {
              row.send_after = body.send_after || '';
              return { ok: true, send_after: row.send_after };
            }
            row.send_after = '2026-03-18 08:00';
            return { ok: true, send_after: row.send_after };
          }
          return { ok: true, send_after: '' };
        }
        if (path === '/api/delete_row') return { ok: true };
        if (path === '/api/opt_out_row') return { ok: true };
        return { ok: true };
      };
      const rows = [
        mk('Alpha HVAC'),
        mk('Bravo Plumbing', { approved: 'true', send_after: '2026-03-18 08:00' }),
        mk('Charlie Electric', { approved: 'true' }),
        mk('Delta Roofing', { to_email: '', approved: 'false' }),
        mk('Echo Garage'),
      ];
      allRows = rows;
      filteredRows = rows.slice();
      currentFilter = 'all';
      renderTable();
      _mrpOpenRowsInOutreach(rows);
    }
    """)
    page.wait_for_timeout(400)

    state0 = page.evaluate("""() => ({ overlay: document.getElementById('panel-overlay').className, title: document.getElementById('panel-session-title').textContent, pos: document.getElementById('panel-pos').textContent, biz: document.getElementById('panel-biz-title').textContent, count: allRows.length, toast: (window.__toasts||[]).slice(-1)[0] || null })""")
    assert 'open' in state0['overlay'], state0
    assert 'Discovery review subset' in state0['title'], state0
    assert '1 / 5' in state0['pos'], state0

    page.get_by_role('button', name='Approve + Next').click()
    page.wait_for_timeout(120)
    assert 'Bravo Plumbing' in (page.locator('#panel-biz-title').text_content() or '')

    page.get_by_role('button', name='Unschedule + Next').click()
    page.wait_for_timeout(120)
    assert 'Charlie Electric' in (page.locator('#panel-biz-title').text_content() or '')

    page.keyboard.press('Shift+S')
    page.wait_for_timeout(120)
    assert 'Delta Roofing' in (page.locator('#panel-biz-title').text_content() or '')

    page.keyboard.press('N')
    page.wait_for_timeout(120)
    assert 'Echo Garage' in (page.locator('#panel-biz-title').text_content() or '')

    page.locator('#panel-overlay').click(position={'x': 10, 'y': 10})
    page.wait_for_timeout(80)
    assert page.locator('#panel-overlay').evaluate("el => el.classList.contains('open')")

    state = page.evaluate("""
    () => ({
      rows: allRows.map(r => ({ name: r.business_name, approved: r.approved, send_after: r.send_after })),
      apiCalls: (window.__apiCalls || []).length,
      sessionMeta: document.getElementById('panel-session-meta')?.textContent || '',
      searchAreaGridVisible: /Search Area Grid/i.test(document.body.textContent || ''),
    })
    """)

    assert state['rows'][0]['approved'] == 'true', state
    assert state['rows'][1]['send_after'] == '', state
    assert state['rows'][2]['send_after'] == '2026-03-18 08:00', state
    assert state['searchAreaGridVisible'], state
    assert '5 in set' in state['sessionMeta'], state
    assert not errors, errors

    print('PASS34_SMOKE_OK')
    print(json.dumps(state, indent=2))
    browser.close()

