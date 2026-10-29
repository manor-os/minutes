import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFileSync, existsSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, extname, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '../../..');
const OUT = resolve(HERE, '../assets');
const require = createRequire(join(ROOT, 'phone-recorder/package.json'));
const { chromium } = require('playwright-core');
const meeting = JSON.parse(readFileSync(join(HERE, 'meeting-fixture.json'), 'utf8'));
const dist = join(ROOT, 'phone-recorder/dist');
const mime = { '.js': 'text/javascript', '.html': 'text/html', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json' };
if (!existsSync(join(dist, 'index.html'))) throw new Error('Build the Community frontend first.');
if (!process.env.CHROMIUM_PATH) throw new Error('Set CHROMIUM_PATH to your Chrome/Chromium executable.');
mkdirSync(OUT, { recursive: true });
const server = createServer((req, res) => {
  let path = resolve(dist, '.' + new URL(req.url, 'http://localhost').pathname);
  if (!path.startsWith(dist + '/') || !existsSync(path)) path = join(dist, 'index.html');
  res.writeHead(200, { 'Content-Type': mime[extname(path)] || 'application/octet-stream' });
  res.end(readFileSync(path));
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH });
  const context = await browser.newContext({ viewport: { width: 1120, height: 830 }, deviceScaleFactor: 1.5, serviceWorkers: 'block', locale: 'en-US', timezoneId: 'UTC' });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.startsWith('/api/')) {
      if (path === '/api/auth/verify') return route.fulfill({ json: { success: true, valid: true, user_id: 'sample-user', entity_id: 'sample-entity', name: 'Alex', email: 'alex@example.test' } });
      if (path === '/api/auth/me') return route.fulfill({ json: { success: true, stt_configured: true, llm_configured: true, has_stt_key: true, has_llm_key: true } });
      if (path === '/api/meetings/list') return route.fulfill({ json: { success: true, meetings: [meeting], total_pages: 1 } });
      if (path === '/api/meetings/templates') return route.fulfill({ json: { success: true, templates: [{ id: 'general', name: 'General Meeting' }] } });
      if (path.endsWith('/chat')) {
        const answer = 'The team decided to **launch on Friday**, after the mobile review is complete.\n\nBefore launch:\n- **Jamie** will finish the pricing review.\n- **Morgan** will check the mobile experience.\n- **Alex** will prepare the customer announcement.\n\nThe team will review early feedback on **Monday**.';
        return route.fulfill({ contentType: 'text/event-stream', body: `data: ${JSON.stringify({ token: answer })}\n\ndata: {"done":true}\n\n` });
      }
      return route.fulfill({ json: { success: true, staff: [] } });
    }
    if (url.origin === origin) return route.continue();
    return route.abort('blockedbyclient');
  });
  await page.addInitScript(() => {
    localStorage.setItem('auth_token', 'synthetic-demo-session');
    localStorage.setItem('theme', 'light');
    localStorage.setItem('capture_system_audio', 'false');
    localStorage.setItem('auto_refresh_enabled', 'false');
    localStorage.setItem('notifications_enabled', 'false');
    localStorage.setItem('has_stt_key', 'true');
    localStorage.setItem('has_llm_key', 'true');
  });
  await page.goto(origin);
  await page.getByRole('button', { name: 'My Meetings', exact: true }).click();
  await page.locator('[data-meeting-id="launch-demo"] .meeting-open').click();
  const detail = page.getByRole('dialog', { name: meeting.title, exact: true });
  await detail.waitFor();
  await detail.screenshot({ path: join(OUT, 'community-summary.png') });
  await detail.getByRole('tab', { name: 'Actions', exact: true }).click();
  await detail.getByText('Finish the pricing review before launch.', { exact: true }).waitFor();
  await detail.screenshot({ path: join(OUT, 'community-actions.png') });
  await detail.getByRole('tab', { name: 'Ask', exact: true }).click();
  const question = detail.getByPlaceholder('Ask a question about this meeting...');
  await question.fill('What needs to happen before we launch?');
  await question.press('Enter');
  await detail.getByText('The team decided to', { exact: false }).waitFor();
  await detail.screenshot({ path: join(OUT, 'community-ask.png') });
  if (errors.length) throw new Error(errors.join('\n'));
  writeFileSync(join(HERE, 'screenshot-provenance.json'), JSON.stringify({
    sourceRevision: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: ROOT, encoding: 'utf8' }).trim(),
    edition: 'community', method: 'Unmodified Community UI; synthetic API fixtures',
    privateData: false, realModelOutputs: false, fixture: 'meeting-fixture.json',
    network: 'All nonlocal, nonfixture requests blocked',
    images: ['community-summary.png', 'community-actions.png', 'community-ask.png'],
  }, null, 2) + '\n');
  console.log('Captured Community summary, actions, and Ask; no page errors.');
} finally {
  await browser?.close();
  await new Promise(r => server.close(r));
}
