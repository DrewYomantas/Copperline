const { test, expect } = require('playwright/test');

test('pass34 review throughput smoke', async ({ page }) => {
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
  await expect(page.locator('#panel-session-title')).toHaveText(/Discovery review subset/);
  await expect(page.locator('#panel-pos')).toHaveText(/1 \/ 5/);

  await page.getByRole('button', { name: /Approve \+ Next/i }).click();
  await expect(page.locator('#panel-biz-title')).toHaveText(/Bravo Plumbing/);

  await page.getByRole('button', { name: /Unschedule \+ Next/i }).click();
  await expect(page.locator('#panel-biz-title')).toHaveText(/Charlie Electric/);

  await page.keyboard.press('Shift+S');
  await expect(page.locator('#panel-biz-title')).toHaveText(/Delta Roofing/);

  await page.keyboard.press('N');
  await expect(page.locator('#panel-biz-title')).toHaveText(/Echo Garage/);

  await page.locator('#panel-overlay').click({ position: { x: 10, y: 10 } });
  await expect(page.locator('#panel-overlay')).toHaveClass(/open/);

  const state = await page.evaluate(() => ({
    rows: allRows.map(r => ({ name: r.business_name, approved: r.approved, send_after: r.send_after })),
    sessionMeta: document.getElementById('panel-session-meta')?.textContent || '',
    searchAreaGridVisible: !!Array.from(document.querySelectorAll('button')).find(btn => /Search Area Grid/i.test(btn.textContent || '')),
  }));

  expect(state.rows[0].approved).toBe('true');
  expect(state.rows[1].send_after).toBe('');
  expect(state.rows[2].send_after).toBe('2026-03-18 08:00');
  expect(state.searchAreaGridVisible).toBeTruthy();
  expect(state.sessionMeta).toContain('5 in set');
  expect(errors).toEqual([]);
});
