// Render QA (layer A, browser part) for one self-contained report page.
//
// Usage:
//   node docs/research-reports/kit/render_qa.mjs <page-url> <out-dir>
//
// <page-url> is an http(s) URL served by a short-lived local static server, e.g.
//   python3 -m http.server 8765 --bind 127.0.0.1 --directory <research_dir>/page
//   -> http://127.0.0.1:8765/index.html   (stop the server afterwards)
// <out-dir> must be OUTSIDE Git (screenshots are evidence, not source).
//
// Requires an existing Playwright install; nothing is installed by this script.
//   PLAYWRIGHT_MODULE_DIR  directory that contains node_modules/playwright (optional; default: normal resolution)
//   CHROME_PATH            browser executable (optional; default: Playwright's bundled Chromium)
// If Playwright or a browser is unavailable, record qa.render.state = "not_run" in run.json.
//
// Checks at 390x844 and 1440x900, light and dark: HTTP 200, no horizontal overflow,
// no console errors, no external requests, every chart rendered as SVG, cite/toc anchors
// land on their targets, theme toggle works. Writes <out-dir>/render-qa.json and screenshots.
// Passing proves the page renders; it does not prove the content is correct.
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';

const [url, out] = process.argv.slice(2);
if (!url || !out) { console.error('usage: node render_qa.mjs <page-url> <out-dir>'); process.exit(2); }
const require = createRequire(process.env.PLAYWRIGHT_MODULE_DIR ? path.join(process.env.PLAYWRIGHT_MODULE_DIR, 'x.js') : import.meta.url);
const { chromium } = require('playwright');

fs.mkdirSync(path.join(out, 'screenshots'), { recursive: true });
const origin = new URL(url).origin;
const viewports = [{ name: 'm390', width: 390, height: 844 }, { name: 'd1440', width: 1440, height: 900 }];
const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
const results = [];
for (const vp of viewports) for (const scheme of ['light', 'dark']) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, colorScheme: scheme, deviceScaleFactor: vp.width < 500 ? 2 : 1 });
  const page = await ctx.newPage();
  const errors = [], external = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('request', r => { if (!r.url().startsWith(origin) && !r.url().startsWith('data:')) external.push(r.url()); });
  const resp = await page.goto(url, { waitUntil: 'load' });
  const tag = `${vp.name}-${scheme}`;
  await page.screenshot({ path: path.join(out, 'screenshots', `${tag}-first.png`) });
  await page.screenshot({ path: path.join(out, 'screenshots', `${tag}-full.png`), fullPage: true });
  const m = await page.evaluate(() => {
    const de = document.documentElement;
    const over = [];
    document.querySelectorAll('body *').forEach(el => { const r = el.getBoundingClientRect(); if (r.width > 0 && r.right > de.clientWidth + 1 && getComputedStyle(el).position !== 'fixed' && !el.closest('.scroll')) over.push(el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className : '')); });
    const charts = document.querySelectorAll('script[data-chart]').length;
    const chartSvgs = [...document.querySelectorAll('script[data-chart]')].filter(s => s.previousElementSibling && s.previousElementSibling.tagName.toLowerCase() === 'svg').length;
    const small = [];
    document.querySelectorAll('a.cite, nav.toc a, button, summary').forEach(a => { const r = a.getBoundingClientRect(); if (r.width > 0 && (r.height < 24 || r.width < 24)) small.push(a.textContent.trim().slice(0, 20)); });
    return { scrollW: de.scrollWidth, clientW: de.clientWidth, overflowEls: over.slice(0, 5), charts, chartSvgs, smallTargets: small.slice(0, 5) };
  });
  const rec = { viewport: vp.name, scheme, status: resp ? resp.status() : null, ...m, consoleErrors: errors, externalRequests: external };
  if (vp.name === 'm390' && scheme === 'light') {
    const clicks = [];
    const hrefs = [...new Set(await page.$$eval('nav.toc a, a.cite', as => as.map(a => a.getAttribute('href'))))];
    for (const h of hrefs) {
      await page.$eval(`a[href="${h}"]`, a => { const d = a.closest('details'); if (d) d.open = true; });
      await page.locator(`a[href="${h}"]`).filter({ visible: true }).first().click();
      let ok = false;
      for (let i = 0; i < 20 && !ok; i++) { await page.waitForTimeout(100); ok = await page.evaluate(h => { const el = document.querySelector(h); if (!el) return false; const r = el.getBoundingClientRect(); return location.hash === h && r.top < innerHeight && r.bottom > 0; }, h); }
      clicks.push({ href: h, ok });
    }
    await page.click('#theme');
    clicks.push({ href: '#theme-toggle', ok: (await page.evaluate(() => document.documentElement.dataset.theme)) === 'dark' });
    await page.screenshot({ path: path.join(out, 'screenshots', `${tag}-after-clicks.png`) });
    rec.clicks = clicks;
  }
  results.push(rec);
  await ctx.close();
}
await browser.close();
const fails = results.filter(r => r.status !== 200 || r.scrollW > r.clientW || r.consoleErrors.length || r.externalRequests.length || r.chartSvgs !== r.charts || (r.clicks || []).some(c => !c.ok));
const summary = { layer: 'A-render', url, state: fails.length ? 'failed' : 'passed', cases: results.length, failed_cases: fails.length,
  not_checked: ['semantic support (layer B)', 'owner intent (layer C)', 'external link liveness'], results };
fs.writeFileSync(path.join(out, 'render-qa.json'), JSON.stringify(summary, null, 1));
for (const r of results) console.log(r.viewport, r.scheme, 'status', r.status, 'scroll', r.scrollW + '/' + r.clientW, 'charts', r.chartSvgs + '/' + r.charts, 'errors', r.consoleErrors.length, 'external', r.externalRequests.length, 'clicks', r.clicks ? r.clicks.filter(c => c.ok).length + '/' + r.clicks.length : '-');
console.log(`render QA: ${summary.state} (${fails.length} failed of ${results.length} cases). Content correctness is NOT checked.`);
process.exit(fails.length ? 1 : 0);
