// Real React lifecycle; HTTP, microphone, recorder, and WebSocket are synthetic.
// This verifies account configuration behavior, not login or paid model execution.
import assert from 'node:assert/strict';
import { build } from 'vite';
import react from '@vitejs/plugin-react';
import { chromium } from 'playwright-core';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const output = process.env.MINUTES_RECORDER_TEST_OUTPUT;
if (output) mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || process.env.CHROMIUM_PATH ||
    (existsSync('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome') ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : undefined) });
const results = [];
const bundles = new Map();
const account = (policy, stt, llm = true) => ({ success: true, stt_managed_by: policy,
  llm_managed_by: policy, stt_configured: stt, llm_configured: llm });

async function fixture(scenario) {
  const modes = { VITE_EDITION: scenario.edition, VITE_STT_MODE: scenario.sttMode || 'cloud',
    VITE_LLM_MODE: scenario.llmMode || 'cloud', VITE_API_URL: 'https://minutes.example.test' };
  const key = JSON.stringify(modes);
  if (!bundles.has(key)) {
    const entry = '\0minutes-recorder-test.jsx';
    const compiled = await build({ root, configFile: false, envDir: false, logLevel: 'error',
      plugins: [react(), { name: 'isolated-recorder-fixture',
        resolveId(id) { if (id === 'minutes-recorder-test') return entry; },
        load(id) { if (id === entry) return `import React, {useState} from 'react'; import {createRoot} from 'react-dom/client'; import ${JSON.stringify(join(root, 'src/index.css'))}; import ${JSON.stringify(join(root, 'src/App.css'))}; import Recorder from ${JSON.stringify(join(root, 'src/components/Recorder.jsx'))}; import ${JSON.stringify(join(root, 'src/Monochrome.css'))}; function Fixture(){const [recording,setRecording]=useState(false); return React.createElement(Recorder,{isRecording:recording,setIsRecording:setRecording,onRecordingComplete:()=>{},onOpenSettings:()=>{},onNotification:n=>window.testNotifications.push(n)});} createRoot(document.getElementById('root')).render(React.createElement(Fixture));`; },
      }],
      build: { write: false, minify: false, rollupOptions: { input: 'minutes-recorder-test', output: { format: 'iife', inlineDynamicImports: true } } },
      define: Object.fromEntries(Object.entries(modes).map(([key, value]) => [`import.meta.env.${key}`, JSON.stringify(value)])) });
    const js = compiled.output.find(f => f.type === 'chunk').code;
    const css = compiled.output.find(f => f.type === 'asset' && f.fileName.endsWith('.css'))?.source || '';
    bundles.set(key, `<meta charset="utf-8"><div id="root"></div><style>${css}</style><script>${js.replaceAll('</script', '<\\/script')}</script>`);
  }
  return bundles.get(key);
}

try {
  for (const scenario of [
    { name: 'hosted starts with no browser key flags', edition: 'cloud', profile: account('manor', true) },
    { name: 'hosted local accounts retain missing-key warning', edition: 'cloud', profile: account('local', false, false), warning: 'both' },
    { name: 'hosted starts when account profile is unavailable', edition: 'cloud', profile: null },
    { name: 'retained community Manor identity avoids separate key warning', edition: 'community', profile: account('manor', false, false) },
    { name: 'legacy Manor policy avoids separate key warning', edition: 'community', profile: { success: true, llm_managed_by: 'manor', stt_configured: false } },
    { name: 'community uses server keys with no browser flags', edition: 'community', profile: account('local', true) },
    { name: 'community missing STT warns and refresh recovers', edition: 'community', profile: account('local', false), warning: 'stt' },
    { name: 'stale configured flags cannot hide missing server keys', edition: 'community', profile: account('local', false, false), flags: true, warning: 'both' },
    { name: 'local STT with remote LLM does not require STT key', edition: 'community', profile: account('local', false, false), sttMode: 'local' },
    { name: 'remote STT with local LLM only warns about STT', edition: 'community', profile: account('local', false, false), llmMode: 'local', warning: 'stt' },
    { name: 'unknown profile avoids false key diagnosis', edition: 'community', profile: null },
    { name: 'legacy profile without readiness avoids false key diagnosis', edition: 'community', profile: { success: true, llm_managed_by: 'local', has_stt_key: false, has_llm_key: false } },
  ]) {
    const html = await fixture(scenario);
    const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    page.setDefaultTimeout(8000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let profile = scenario.profile;
    let profileRequests = 0;
    const profileHeaders = [];
    try {
      await page.addInitScript(({ flags }) => {
        localStorage.setItem('auth_token', 'dummy-login-token+/=');
        localStorage.setItem('capture_system_audio', 'false');
        localStorage.setItem('transcript_language', 'en');
        localStorage.setItem('stt_api_key', 'dummy-obsolete-browser-key');
        localStorage.setItem('stt_base_url', 'https://obsolete-audio.example.test');
        if (flags) {
          localStorage.setItem('has_stt_key', 'true');
          localStorage.setItem('has_llm_key', 'true');
        }
        window.testNotifications = [];
        window.testSockets = [];
        window.testMicCalls = 0;
        Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
          getUserMedia: async () => {
            window.testMicCalls += 1;
            const stream = { active: true };
            const track = { stop: () => { stream.active = false; } };
            stream.getTracks = () => [track];
            stream.getAudioTracks = () => [track];
            return stream;
          },
        } });
        window.MediaRecorder = class {
          constructor(stream) { this.stream = stream; this.state = 'inactive'; }
          start() { this.state = 'recording'; }
          stop() { this.state = 'inactive'; this.onstop?.(); }
        };
        window.WebSocket = class {
          static OPEN = 1;
          constructor(url) {
            this.url = url;
            this.readyState = 0;
            this.messages = [];
            window.testSockets.push(this);
            setTimeout(() => { this.readyState = 1; this.onopen?.(); }, 0);
          }
          send(message) { if (typeof message === 'string') this.messages.push(JSON.parse(message)); }
          close() { this.readyState = 3; this.onclose?.(); }
        };
      }, { flags: scenario.flags || false });
      await page.route('**/*', async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/recorder-test') return route.fulfill({ contentType: 'text/html', body: html });
        if (path === '/api/meetings/templates') return route.fulfill({ json: { success: true, templates: [{ id: 'general', name: 'General Meeting' }] } });
        if (path === '/api/auth/me') {
          profileRequests += 1;
          profileHeaders.push(route.request().headers().authorization);
          return route.fulfill({ status: profile ? 200 : 503, json: profile || { detail: 'Unavailable' } });
        }
        return route.abort('blockedbyclient');
      });
      const profileResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/auth/me');
      await page.goto('https://minutes.example.test/recorder-test');
      await profileResponse;
      await page.getByRole('button', { name: 'Start Recording', exact: true }).waitFor();
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await page.getByRole('button', { name: 'Start Recording', exact: true }).click();
      if (scenario.warning) {
        const expected = scenario.warning === 'both'
          ? 'STT and LLM API keys are not configured. Recording requires at least an STT key for transcription.'
          : 'STT API key is not configured. Live transcription will not work without it.';
        await page.getByText(expected, { exact: true }).waitFor();
        assert.equal(await page.evaluate(() => window.testMicCalls), 0);
        assert.equal(await page.evaluate(() => window.testSockets.length), 0);
        profile = account('local', true);
        const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/auth/me');
        await page.evaluate(() => window.dispatchEvent(new Event('minutes-ai-config-updated')));
        await refreshed;
        await page.locator('.api-key-warning').waitFor({ state: 'detached' });
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        await page.getByRole('button', { name: 'Start Recording', exact: true }).click();
      }
      await page.getByRole('button', { name: 'Stop recording', exact: true }).waitFor();
      await page.waitForFunction(() => window.testSockets[0]?.messages.some(message => message.type === 'config'));
      assert.equal(await page.locator('.api-key-warning').count(), 0);
      assert.equal(await page.evaluate(() => window.testMicCalls), 1);
      const sockets = await page.evaluate(() => window.testSockets.map(socket => ({ url: socket.url, messages: socket.messages })));
      assert.equal(sockets.length, 1);
      const socketUrl = new URL(sockets[0].url);
      assert.equal(socketUrl.protocol, 'wss:');
      assert.equal(socketUrl.pathname, '/ws/transcribe');
      assert.equal(socketUrl.searchParams.get('token'), 'dummy-login-token+/=');
      assert.deepEqual(sockets[0].messages, [{ type: 'config', language: 'en' }],
        'only language preferences are sent; cached credentials and endpoints never override account configuration');
      assert.deepEqual(profileHeaders, Array(scenario.warning ? 2 : 1).fill('Bearer dummy-login-token+/='));
      assert.equal(profileRequests, scenario.warning ? 2 : 1);
      assert.deepEqual(await page.evaluate(() => window.testNotifications), []);
      assert.deepEqual(errors, []);
      if (output && scenario.name === 'hosted starts with no browser key flags') {
        await page.screenshot({ path: join(output, 'hosted-recorder.png'), fullPage: true });
      }
      results.push({ name: scenario.name, passed: true, kind: 'React browser with mocked HTTP and media' });
    } catch (error) {
      if (output) {
        await page.screenshot({ path: join(output, 'failure.png'), fullPage: true });
        writeFileSync(join(output, 'failure-dom.txt'), await page.locator('body').innerText());
      }
      error.message = `${scenario.name}: ${error.message}`;
      throw error;
    } finally { await context.close(); }
  }
} finally {
  await browser.close();
  if (output) writeFileSync(join(output, 'results.json'), JSON.stringify({ results, realModelCalls: 0, realLogin: false }, null, 2));
}
console.log(JSON.stringify({ passed: results.length, failed: 0, realModelCalls: 0 }));
