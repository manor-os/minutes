// Regression for the real meeting list/detail UI: compact key points, Actions,
// Manor tickets, Ask SSE/error handling, mobile tabs, and audio download.
//
// Usage:
//   VITE_EDITION=cloud VITE_API_URL=http://127.0.0.1:9002 npm run build
//   CHROMIUM_PATH=/path/to/chrome node e2e/test-meeting-detail.mjs
import { chromium } from 'playwright-core';
import { readFileSync, existsSync, unlinkSync } from 'fs';
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

const step = (message) => console.log('STEP:', message);
const waitUntil = async (predicate, label, timeout = 10000) => {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > timeout) throw new Error(`timed out waiting for ${label}`);
    await new Promise(resolve => setTimeout(resolve, 25));
  }
};

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
  created_at: '2026-09-17T19:00:00Z',
  duration: 65,
  platform: 'phone_recorder',
  audio_file: '20260917_rec.mp3',
  summary: 'The team agreed on the launch plan and follow-up work.',
  transcript: 'The team agreed to prepare the launch plan before Friday.',
  key_points: DIRTY_KEY_POINTS,
  action_items: [
    {
      task: 'Prepare launch plan',
      assignee: 'Calvin Lin',
      due_date: '2026-09-18T09:30',
      completed: false,
      source: 'meeting-ai',
    },
    {
      task: 'Book follow-up meeting',
      assignee: 'TBD',
      due_date: 'TBD',
      completed: false,
    },
  ],
};

const MIME = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json',
  '.webmanifest': 'application/manifest+json',
};
const server = createServer((req, res) => {
  let path = join(DIST, req.url.split('?')[0]);
  if (!existsSync(path) || req.url === '/') path = join(DIST, 'index.html');
  try {
    const body = readFileSync(path);
    res.writeHead(200, { 'content-type': MIME[extname(path)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end();
  }
});
await new Promise(resolve => server.listen(PORT, '127.0.0.1', resolve));
step(`static server on :${PORT}`);

let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    headless: true,
    args: ['--no-sandbox'],
  });
} catch (error) {
  server.close();
  console.error('Could not launch a browser:', error.message.split('\n')[0]);
  console.error('Set CHROMIUM_PATH to a Chromium/Chrome binary.');
  process.exit(1);
}

const context = await browser.newContext({ serviceWorkers: 'block' });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', error => pageErrors.push(String(error)));

let currentMeeting = JSON.parse(JSON.stringify(MEETING));
let assetsLoaded = false;
let audioRequestHadAuth = false;
let chatMode = 'success';
const patchRequests = [];
const ticketRequests = [];
const chatRequests = [];
const parseBody = request => request.postData() ? JSON.parse(request.postData()) : {};

await page.route('**/api/**', async (route) => {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  const auth = request.headers().authorization || '';

  if (path === '/api/auth/verify') {
    return route.fulfill({ json: { success: true, valid: true, entity_id: 'e1', email: 't@t.io', name: 'Tester', user_id: 'u1' } });
  }
  if (path === '/api/auth/me') {
    return route.fulfill({ json: { success: true, stt_managed_by: 'manor', llm_managed_by: 'manor', stt_configured: true, llm_configured: true } });
  }
  if (path === '/api/meetings/templates') {
    return route.fulfill({ json: { success: true, templates: [] } });
  }
  if (path === '/api/meetings/list') {
    return route.fulfill({ json: { success: true, meetings: [currentMeeting], total_pages: 1 } });
  }
  if (path === '/api/meetings/staff/list') {
    return route.fulfill({ json: { success: true, staff: [
      { id: 11, name: 'Calvin Lin', title: 'Founder' },
      { id: 12, name: 'Priya Sharma', title: 'Operations' },
    ] } });
  }
  if (path === '/api/meetings/assets') {
    assetsLoaded = true;
    return route.fulfill({ json: { success: true, assets: [
      { id: 41, name: 'Main Office', address: '1 Test Street' },
      { id: 42, name: 'Warehouse' },
    ] } });
  }
  if (path === `/api/meetings/audio/${MEETING.audio_file}`) {
    audioRequestHadAuth = auth === 'Bearer e2e-token';
    return route.fulfill({ status: 200, contentType: 'audio/mpeg', body: AUDIO_BYTES });
  }
  if (path === `/api/meetings/${MEETING.id}` && request.method() === 'PATCH') {
    const body = parseBody(request);
    patchRequests.push({ body, auth });
    currentMeeting = { ...currentMeeting, ...body };
    return route.fulfill({ json: { success: true, meeting: currentMeeting } });
  }
  const ticketMatch = path.match(/^\/api\/meetings\/m1\/action-items\/(\d+)\/create-ticket$/);
  if (ticketMatch && request.method() === 'POST') {
    const body = parseBody(request);
    ticketRequests.push({ index: Number(ticketMatch[1]), body, auth });
    return route.fulfill({ json: { success: true, task_id: `task-${ticketRequests.length}` } });
  }
  if (path === `/api/meetings/${MEETING.id}/chat` && request.method() === 'POST') {
    const body = parseBody(request);
    chatRequests.push({ body, auth });
    if (chatMode === 'http-error') {
      return route.fulfill({ status: 402, json: { detail: '额度不足，请充值后再试。' } });
    }
    return route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'data: {"token":"The team "}',
        '',
        'data: {"token":"agreed to prepare the launch plan."}',
        '',
        'data: {"done":true}',
        '',
      ].join('\n'),
    });
  }
  return route.fulfill({ json: { success: true } });
});

await page.addInitScript(() => {
  localStorage.setItem('auth_token', 'e2e-token');
  localStorage.setItem('auto_refresh_enabled', 'false');
  localStorage.setItem('notifications_enabled', 'false');
});

await page.goto(`http://127.0.0.1:${PORT}/`);
await page.getByRole('button', { name: 'My Meetings', exact: true }).click();
await page.locator('[data-meeting-id="m1"] .meeting-open').waitFor({ timeout: 15000 });
await page.locator('[data-meeting-id="m1"] .meeting-open').click();
const detail = page.getByRole('dialog', { name: 'E2E Test Meeting', exact: true });
await detail.waitFor({ timeout: 15000 });
step('opened the real meeting card and detail dialog');

await detail.locator('details.quiet-key-points > summary').click();
const points = await detail.locator('.key-points-list li').allTextContents();
if (JSON.stringify(points) !== JSON.stringify(EXPECTED_KEY_POINTS)) {
  throw new Error(`key points were not cleaned: ${JSON.stringify(points)}`);
}
step('cleaned legacy key points render inside the compact disclosure');

await detail.locator('#detail-tab-summary').focus();
await detail.locator('#detail-tab-summary').press('End');
if (await detail.locator('#detail-tab-ask').getAttribute('aria-selected') !== 'true') {
  throw new Error('End key did not select the last meeting tab');
}
await detail.locator('#detail-tab-ask').press('ArrowLeft');
if (await detail.locator('#detail-tab-actions').getAttribute('aria-selected') !== 'true') {
  throw new Error('ArrowLeft did not select Actions');
}
const actions = detail.locator('#detail-panel-actions');
if (await actions.locator('.action-item-card').count() !== 2) throw new Error('expected two action items');

const firstAction = actions.locator('.action-item-card').first();
await firstAction.getByRole('button', { name: 'Edit', exact: true }).click();
await firstAction.locator('.action-edit-task').fill('Prepare revised launch plan');
await firstAction.locator('.action-edit-assignee').selectOption('Priya Sharma');
await firstAction.locator('.action-edit-due').fill('2026-09-20T14:00');
await firstAction.getByRole('button', { name: 'Save', exact: true }).click();
await waitUntil(() => patchRequests.length === 1, 'action edit PATCH');
await actions.getByText('Prepare revised launch plan', { exact: true }).waitFor();

const edited = patchRequests[0].body.action_items[0];
if (edited.assignee !== 'Priya Sharma' || edited.due_date !== '2026-09-20T14:00') {
  throw new Error(`action edit fields were not sent: ${JSON.stringify(edited)}`);
}
if (edited.completed !== false || edited.source !== 'meeting-ai') {
  throw new Error(`action edit discarded existing fields: ${JSON.stringify(edited)}`);
}
if (patchRequests[0].auth !== 'Bearer e2e-token') throw new Error('action PATCH was not authenticated');
step('action edit saves and preserves fields outside the edit form');

await waitUntil(() => assetsLoaded, 'asset list');
const editedAction = actions.locator('.action-item-card').filter({ hasText: 'Prepare revised launch plan' });
await editedAction.getByRole('button', { name: 'Create Ticket', exact: true }).click();
let assetModal = detail.locator('.asset-selection-content').filter({ hasText: 'Select Asset (Optional)' });
await assetModal.locator('.asset-select').selectOption('41');
await assetModal.getByRole('button', { name: 'Create Ticket', exact: true }).click();
await waitUntil(() => ticketRequests.length === 1, 'single ticket request');
await assetModal.waitFor({ state: 'detached' });
if (JSON.stringify(ticketRequests[0]) !== JSON.stringify({ index: 0, body: { asset_id: 41 }, auth: 'Bearer e2e-token' })) {
  throw new Error(`unexpected single ticket request: ${JSON.stringify(ticketRequests[0])}`);
}
step('single Manor ticket creation includes the selected asset and auth');

await actions.locator('.btn-generate-tickets').click();
assetModal = detail.locator('.asset-selection-content').filter({ hasText: 'Select Asset for All Tickets (Optional)' });
await assetModal.locator('.asset-select').selectOption('42');
await assetModal.getByRole('button', { name: 'Generate All Tickets', exact: true }).click();
await waitUntil(() => ticketRequests.length === 3, 'bulk ticket requests');
await assetModal.waitFor({ state: 'detached' });
const bulk = ticketRequests.slice(1);
if (JSON.stringify(bulk.map(item => ({ index: item.index, body: item.body }))) !== JSON.stringify([
  { index: 0, body: { asset_id: 42 } },
  { index: 1, body: { asset_id: 42 } },
])) {
  throw new Error(`unexpected bulk ticket requests: ${JSON.stringify(bulk)}`);
}
step('bulk ticket creation covers every action and closes its asset picker');

const removable = actions.locator('.action-item-card').filter({ hasText: 'Book follow-up meeting' });
await removable.getByRole('button', { name: 'Delete', exact: true }).click();
await waitUntil(() => patchRequests.length === 2, 'action delete PATCH');
await removable.waitFor({ state: 'detached' });
if (patchRequests[1].body.action_items.length !== 1 || patchRequests[1].body.action_items[0].task !== 'Prepare revised launch plan') {
  throw new Error(`action delete sent the wrong list: ${JSON.stringify(patchRequests[1].body)}`);
}
step('action deletion persists the remaining complete action object');

await detail.getByRole('tab', { name: 'Ask', exact: true }).click();
const ask = detail.locator('#detail-panel-ask');
await ask.locator('.chat-input').fill('What was agreed?');
await ask.getByRole('button', { name: 'Ask', exact: true }).click();
await ask.locator('.chat-msg-assistant').filter({ hasText: 'The team agreed to prepare the launch plan.' }).waitFor();
if (JSON.stringify(chatRequests[0]) !== JSON.stringify({ body: { question: 'What was agreed?' }, auth: 'Bearer e2e-token' })) {
  throw new Error(`unexpected chat request: ${JSON.stringify(chatRequests[0])}`);
}
if (await ask.locator('.chat-input').isDisabled()) throw new Error('chat input stayed disabled after the stream');
step('Ask renders the authenticated SSE answer');

chatMode = 'http-error';
await ask.locator('.chat-input').fill('Can I ask another question?');
await ask.locator('.chat-input').press('Enter');
await ask.locator('.chat-msg-assistant').filter({ hasText: '额度不足，请充值后再试。' }).waitFor();
if (await ask.locator('.chat-input').isDisabled()) throw new Error('chat input stayed disabled after an HTTP error');
step('Ask shows backend HTTP errors instead of an empty answer');

await detail.locator('details.quiet-detail-more > summary').click();
const [download] = await Promise.all([
  page.waitForEvent('download', { timeout: 15000 }),
  detail.locator('.btn-download-audio').click(),
]);
const suggested = download.suggestedFilename();
const savedPath = join(HERE, 'downloaded-audio.tmp');
await download.saveAs(savedPath);
const saved = readFileSync(savedPath);
unlinkSync(savedPath);
if (!suggested.endsWith('.mp3')) throw new Error(`expected .mp3 filename, got "${suggested}"`);
if (!saved.equals(AUDIO_BYTES)) throw new Error('downloaded bytes do not match served audio');
if (!audioRequestHadAuth) throw new Error('audio request was sent without Authorization');
step('audio download remains available in More and is authenticated');

await page.setViewportSize({ width: 390, height: 844 });
await detail.getByRole('tab', { name: 'Actions', exact: true }).click();
await detail.getByText('Prepare revised launch plan', { exact: true }).waitFor();
await detail.getByRole('tab', { name: 'Ask', exact: true }).click();
await ask.getByText('The team agreed to prepare the launch plan.', { exact: true }).waitFor();
step('Actions and Ask remain reachable on a mobile viewport');

if (pageErrors.length) throw new Error(`page exceptions: ${pageErrors.join(' | ')}`);
await browser.close();
server.close();
console.log('E2E-OK');
