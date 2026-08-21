// End-to-end test: the web recorder captures mic + tab (meeting) audio.
//
// Drives the built frontend (../dist) in headless Chromium. The OS device
// layer is stubbed: getUserMedia returns a 440 Hz tone ("my voice") and
// getDisplayMedia returns an 880 Hz tone ("remote participants"). Everything
// downstream is real: the recorder's AudioContext mixing graph, MediaRecorder,
// and the upload request. The uploaded webm is decoded back in the browser and
// checked for BOTH tones with Goertzel filters — proving that local and remote
// audio both end up in the recording.
//
// Usage:  npm run build && node e2e/test-recording.mjs
// Env:    CHROMIUM_PATH  optional path to a Chromium binary
//         E2E_PORT       port for the static server (default 9002)
import { chromium } from 'playwright-core';
import { writeFileSync, readFileSync, existsSync } from 'fs';
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

const results = { steps: [], label: null, webmBytes: 0, tones: {} };
const step = (s) => { console.log('STEP:', s); results.steps.push(s); };

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

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
  headless: true,
  args: ['--autoplay-policy=no-user-gesture-required', '--no-sandbox'],
});
const page = await (await browser.newContext()).newPage();
page.on('pageerror', e => console.log('PAGE EXCEPTION:', String(e).slice(0, 200)));

// --- mock the backend API ---
let uploadBuffer = null;
await page.route('**/api/**', async (route) => {
  const url = route.request().url();
  if (url.includes('/api/auth/verify')) return route.fulfill({ json: { success: true, valid: true, entity_id: 'e1', email: 't@t.io', name: 'Tester', user_id: 'u1' } });
  if (url.includes('/api/meetings/templates')) return route.fulfill({ json: { success: true, templates: [] } });
  if (url.includes('/api/meetings/upload')) {
    uploadBuffer = route.request().postDataBuffer();
    step(`upload intercepted: ${uploadBuffer ? uploadBuffer.length : 0} bytes (multipart)`);
    return route.fulfill({ json: { success: true, meeting: { id: 'm1', status: 'processing' } } });
  }
  if (url.includes('/api/meetings/list')) return route.fulfill({ json: { success: true, meetings: [], total_pages: 1 } });
  return route.fulfill({ json: { success: true } });
});

// --- stub only the device layer; everything downstream is real ---
await page.addInitScript(() => {
  localStorage.setItem('auth_token', 'e2e-token');
  localStorage.setItem('has_stt_key', 'true');
  localStorage.setItem('has_llm_key', 'true');
  localStorage.setItem('capture_system_audio', 'true');

  window.__e2e = { gumCalls: 0, gdmCalls: 0 };
  const makeTone = async (freq) => {
    const ctx = new AudioContext();
    try { await ctx.resume(); } catch (_) {}
    const osc = ctx.createOscillator();
    osc.frequency.value = freq;
    const gain = ctx.createGain();
    gain.gain.value = 0.5;
    const dest = ctx.createMediaStreamDestination();
    osc.connect(gain).connect(dest);
    osc.start();
    window.__e2e['ctx' + freq] = ctx; // keep alive
    return dest.stream;
  };
  navigator.mediaDevices.getUserMedia = async () => { window.__e2e.gumCalls++; return makeTone(440); };
  navigator.mediaDevices.getDisplayMedia = async () => { window.__e2e.gdmCalls++; return makeTone(880); };
});

await page.goto(`http://localhost:${PORT}/`);
await page.waitForSelector('text=Start Recording', { timeout: 15000 });
step('app loaded and authenticated (Recorder visible)');

const toggle = page.locator('.recorder-toggle input[type=checkbox]');
if (!(await toggle.isChecked())) throw new Error('capture-system-audio toggle should default to checked');
step('meeting-audio toggle present and enabled by default');

await page.click('text=Start Recording');
await page.waitForSelector('.recording-label', { timeout: 20000 });
await page.waitForTimeout(1000);
results.label = (await page.textContent('.recording-label')).trim();
step(`recording started, label: "${results.label}"`);
if (!/mic \+ meeting audio/i.test(results.label)) throw new Error(`expected mixed-source label, got "${results.label}"`);

const calls = await page.evaluate(() => window.__e2e);
step(`device calls: getUserMedia=${calls.gumCalls}, getDisplayMedia=${calls.gdmCalls}`);
if (calls.gdmCalls < 1) throw new Error('getDisplayMedia was never called');

await page.waitForTimeout(6000);
step(`timer: ${(await page.textContent('.recording-time')).trim()}`);

await page.click('text=Stop & Generate Summary');
await page.waitForSelector('text=Start Recording', { timeout: 15000 });
step('recording stopped, UI returned to idle');

for (let i = 0; i < 20 && !uploadBuffer; i++) await page.waitForTimeout(500);
if (!uploadBuffer) throw new Error('recording blob was never uploaded');

// --- extract the webm audio part from the multipart body ---
const raw = uploadBuffer;
const nameIdx = raw.indexOf(Buffer.from('name="audio"'));
if (nameIdx < 0) throw new Error('no "audio" part in upload');
const headerEnd = raw.indexOf(Buffer.from('\r\n\r\n'), nameIdx) + 4;
const boundary = raw.slice(0, raw.indexOf(Buffer.from('\r\n')));
let end = raw.indexOf(boundary, headerEnd);
end = end > headerEnd ? end - 2 : raw.length;
const webm = raw.slice(headerEnd, end);
results.webmBytes = webm.length;
writeFileSync(join(HERE, 'recorded.webm'), webm);
step(`extracted webm: ${webm.length} bytes`);
if (webm.length < 5000) throw new Error(`webm too small (${webm.length} bytes)`);

// --- decode the uploaded bytes in the browser and verify both tones ---
results.tones = await page.evaluate(async (b64) => {
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  const ctx = new AudioContext();
  const audio = await ctx.decodeAudioData(buf.buffer);
  const samples = audio.getChannelData(0);
  const n = samples.length;
  const SR = audio.sampleRate;
  const goertzel = (freq) => {
    const k = Math.round((n * freq) / SR);
    const w = (2 * Math.PI * k) / n;
    const c = 2 * Math.cos(w);
    let s0 = 0, s1 = 0, s2 = 0;
    for (let i = 0; i < n; i++) { s0 = samples[i] + c * s1 - s2; s2 = s1; s1 = s0; }
    return Math.sqrt(s1 * s1 + s2 * s2 - c * s1 * s2) / n;
  };
  return {
    duration_s: +(n / SR).toFixed(2),
    mic_440Hz: goertzel(440),
    meeting_880Hz: goertzel(880),
    control_1567Hz: goertzel(1567),
  };
}, webm.toString('base64'));
step(`decoded ${results.tones.duration_s}s of audio in-browser`);
await browser.close();
server.close();

console.log('TONES:', JSON.stringify(results.tones));
const { mic_440Hz: a, meeting_880Hz: b, control_1567Hz: c } = results.tones;
if (a < c * 20) throw new Error('440 Hz (mic) tone NOT found in recording');
if (b < c * 20) throw new Error('880 Hz (meeting/tab) tone NOT found in recording');
step('both mic (440 Hz) and meeting (880 Hz) tones present in the uploaded recording');

writeFileSync(join(HERE, 'result.json'), JSON.stringify(results, null, 2));
console.log('E2E-OK');
