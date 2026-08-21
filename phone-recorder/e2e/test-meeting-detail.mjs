// End-to-end test: MeetingDetail cleans legacy raw-JSON key points and the
// audio download saves a real file with the correct extension.
//
// Drives the built frontend (../dist) in headless Chromium against a mocked
// backend. The meeting carries key_points exactly as stored by the old buggy
// parser ("```json", "[", quoted lines with trailing commas) and an .mp3
// audio file served through the audio endpoint.
//
// Usage:  npm run build && node e2e/test-meeting-detail.mjs
// Env:    CHROMIUM_PATH  path to a Chromium/Chrome binary — required unless a
//                        playwright-managed browser is already installed
//         E2E_PORT       port for the static server (default 9002)
import { chromium } from 'playwright-core';
import { readFileSync, existsSync } from 'fs';
import { createServer } from 'http';
import { join, extname, dirname } from 'path';
import { fileURLToPath } from 'url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DIST = join(HERE, '..', 'dist');
const PORT = Number(process.env.E2E_PORT || 9002);
if (!existsSync(join(DIST, 'index.html'))) {
  console.error('dist/ not found — run `npm run build` first');
  process.exit(1);
}

const step = (s) => console.log('STEP:', s);

const AUDIO_BYTES = Buffer.from('ID3fake-mp3-bytes-for-e2e-test-0123456789');
const DIRTY_KEY_POINTS = [
  '```json',
  '[',
  '"The meeting was disrupted by a technical issue, leading to repetition in the transcript.",',
  '"No substantial discussions or decisions were captured due to the transcript error.",',
  '"A follow-up meeting may be necessary to address the intended agenda items.",',
];
const EXPECTED_KEY_POINTS = [
  'The meeting was disrupted by a technical issue, leading to repetition in the transcript.',
  'No substantial discussions or decisions were captured due to the transcript error.',
  'A follow-up meeting may be necessary to address the intended agenda items.',
];
const MEETING = {
  id: 'm1',
  title: 'E2E Test Meeting',
  status: 'completed',
  created_at: '2026-08-21T06:00:00Z',
  duration: 65,
  platform: 'phone_recorder',
  audio_file: '20260821_rec.mp3',
  summary: 'A short test summary.',
  key_points: DIRTY_KEY_POINTS,
  action_items: [],
};

// --- static server for the built SPA ---
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json', '.webmanifest': 'application/manifest+json' };
const server = createServer((req, res) => {
  let p = join(DIST, req.url.split('?')[0]);
  if (!existsSync(p) || req.url === '/') p = join(DIST, 'index.html');
  try {
    const body = readFileSync(p);
    res.writeHead(200, { 'content-type': MIME[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(r => server.listen(PORT, r));
step(`static server on :${PORT}`);

let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    headless: true,
    args: ['--no-sandbox'],
  });
} catch (err) {
  server.close();
  console.error('Could not launch a browser:', err.message.split('\n')[0]);
  console.error('Set CHROMIUM_PATH to a Chromium/Chrome binary, e.g.:');
  console.error('  CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e');
  process.exit(1);
}
const context = await browser.newContext();
const page = await context.newPage();
page.on('pageerror', e => console.log('PAGE EXCEPTION:', String(e).slice(0, 200)));

// --- mock the backend API ---
let audioRequestHadAuth = false;
await page.route('**/api/**', async (route) => {
  const url = route.request().url();
  if (url.includes('/api/auth/verify')) return route.fulfill({ json: { success: true, valid: true, entity_id: 'e1', email: 't@t.io', name: 'Tester', user_id: 'u1' } });
  if (url.includes('/api/meetings/templates')) return route.fulfill({ json: { success: true, templates: [] } });
  if (url.includes('/api/meetings/list')) return route.fulfill({ json: { success: true, meetings: [MEETING], total_pages: 1 } });
  if (url.includes(`/api/meetings/audio/${MEETING.audio_file}`)) {
    audioRequestHadAuth = !!route.request().headers()['authorization'];
    return route.fulfill({ status: 200, contentType: 'audio/mpeg', body: AUDIO_BYTES });
  }
  return route.fulfill({ json: { success: true } });
});

await page.addInitScript(() => {
  localStorage.setItem('auth_token', 'e2e-token');
});

await page.goto(`http://localhost:${PORT}/`);
await page.click('text=My Meetings');
await page.waitForSelector('text=E2E Test Meeting', { timeout: 15000 });
step('meeting list loaded');

await page.click('text=View Details');
await page.waitForSelector('.key-points-list', { timeout: 15000 });
step('meeting detail opened');

// --- key points must be cleaned ---
const points = await page.$$eval('.key-points-list li', els => els.map(e => e.textContent.trim()));
console.log('KEY POINTS RENDERED:', JSON.stringify(points));
if (points.length !== EXPECTED_KEY_POINTS.length) {
  throw new Error(`expected ${EXPECTED_KEY_POINTS.length} key points, got ${points.length}`);
}
for (let i = 0; i < points.length; i++) {
  if (points[i] !== EXPECTED_KEY_POINTS[i]) throw new Error(`key point ${i} not cleaned: "${points[i]}"`);
}
for (const p of points) {
  if (/```|^\[$|^\]$|^"|",?$/.test(p)) throw new Error(`raw JSON artifact still visible: "${p}"`);
}
step('key points rendered clean (no fences/brackets/quotes)');

// --- audio download must save a real file with the right extension ---
const [download] = await Promise.all([
  page.waitForEvent('download', { timeout: 15000 }),
  page.click('.btn-download-audio'),
]);
const suggested = download.suggestedFilename();
const savedPath = join(HERE, 'downloaded-audio.tmp');
await download.saveAs(savedPath);
const saved = readFileSync(savedPath);
console.log('DOWNLOAD:', suggested, saved.length, 'bytes');
if (!suggested.endsWith('.mp3')) throw new Error(`expected .mp3 filename, got "${suggested}"`);
if (!saved.equals(AUDIO_BYTES)) throw new Error('downloaded bytes do not match served audio');
if (!audioRequestHadAuth) throw new Error('audio request was sent without Authorization header');
step('audio downloaded: correct bytes, .mp3 extension, authenticated request');

await browser.close();
server.close();
console.log('E2E-OK');
