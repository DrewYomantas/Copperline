const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', err => errors.push(String(err)));
  await page.goto('http://127.0.0.1:5000', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#panel-overlay');
  await page.evaluate(() => {
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
  });

  await page.waitForTimeout(300);
  const sessionTitle = await page.locator('#panel-session-title').textContent();
  if (!sessionTitle.includes('Discovery review subset')) throw new Error(`Unexpected session title: ${sessionTitle}`);
  const pos1 = await page.locator('#panel-pos').textContent();
  if (!pos1.includes('1 / 5')) throw new Error(`Unexpected initial position: ${pos1}`);

  await page.getByRole('button', { name: /Approve \+ Next/i }).click();
  await page.waitForTimeout(120);
  if (!(await page.locator('#panel-biz-title').textContent()).includes('Bravo Plumbing')) throw new Error('Approve + Next did not advance');

  await page.getByRole('button', { name: /Unschedule \+ Next/i }).click();
  await page.waitForTimeout(120);
  if (!(await page.locator('#panel-biz-title').textContent()).includes('Charlie Electric')) throw new Error('Unschedule + Next did not advance');

  await page.keyboard.press('Shift+S');
  await page.waitForTimeout(120);
  if (!(await page.locator('#panel-biz-title').textContent()).includes('Delta Roofing')) throw new Error('Shift+S schedule+next did not advance');

  await page.keyboard.press('N');
  await page.waitForTimeout(120);
  if (!(await page.locator('#panel-biz-title').textContent()).includes('Echo Garage')) throw new Error('N skip did not advance');

  await page.locator('#panel-overlay').click({ position: { x: 10, y: 10 } });
  await page.waitForTimeout(80);
  const overlayOpen = await page.locator('#panel-overlay').evaluate(el => el.classList.contains('open'));
  if (!overlayOpen) throw new Error('Overlay click closed the panel unexpectedly');

  const state = await page.evaluate(() => ({
    rows: allRows.map(r => ({ name: r.business_name, approved: r.approved, send_after: r.send_after })),
    apiCalls: window.__apiCalls || [],
    sessionMeta: document.getElementById('panel-session-meta')?.textContent || '',
    searchAreaGridVisible: !!Array.from(document.querySelectorAll('button')).find(btn => /Search Area Grid/i.test(btn.textContent || '')),
  }));

  if (state.rows[0].approved !== 'true') throw new Error('Alpha HVAC was not approved');
  if (state.rows[1].send_after) throw new Error('Bravo Plumbing remained scheduled after unschedule');
  if (!state.rows[2].send_after) throw new Error('Charlie Electric was not scheduled');
  if (!state.searchAreaGridVisible) throw new Error('Search Area Grid control missing');
  if (!/5 in set/i.test(state.sessionMeta)) throw new Error(`Unexpected session meta: ${state.sessionMeta}`);
  if (errors.length) throw new Error(`Page errors: ${errors.join(' | ')}`);

  console.log('PASS34_SMOKE_OK');
  console.log(JSON.stringify({ apiCalls: state.apiCalls.length, sessionMeta: state.sessionMeta }, null, 2));
  await browser.close();
})().catch(async err => {
  console.error('PASS34_SMOKE_FAIL');
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
