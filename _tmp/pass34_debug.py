from playwright.sync_api import sync_playwright
import json
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://127.0.0.1:5000', wait_until='domcontentloaded')
    page.wait_for_selector('#panel-overlay')
    page.evaluate("""
    () => {
      const mk = (name, extra = {}) => ({ business_name: name, city:'Austin', state:'TX', industry:'hvac', website:'https://example.com', phone:'555', score:'88', subject:'s', body:'b', to_email:'a@example.com', approved:'false', send_after:'', sent_at:'', do_not_contact:'false', ...extra });
      toast = (msg, type) => { window.__toasts = window.__toasts || []; window.__toasts.push({ msg, type }); };
      loadStats = async () => {};
      switchPage = () => {};
      api = async (path, body = {}) => ({ ok: true, send_after: '2026-03-18 08:00' });
      const rows = [mk('Alpha'), mk('Bravo')];
      allRows = rows;
      filteredRows = rows.slice();
      currentFilter = 'all';
      renderTable();
      _mrpOpenRowsInOutreach(rows);
    }
    """)
    page.wait_for_timeout(400)
    state = page.evaluate("""() => ({
      overlay: document.getElementById('panel-overlay')?.className,
      title: document.getElementById('panel-session-title')?.textContent,
      pos: document.getElementById('panel-pos')?.textContent,
      biz: document.getElementById('panel-biz-title')?.textContent,
      toasts: window.__toasts || [],
      panelIdx,
      panelRowsKeys,
      currentRows: _panelCurrentRows().map(r => r.business_name),
      filteredRows: filteredRows.map(r => r.business_name),
      allRows: allRows.map(r => r.business_name),
    })""")
    print(json.dumps(state, indent=2))
    browser.close()
