// Real React lifecycle, entirely intercepted HTTP; not login/model/business E2E.
import assert from 'node:assert/strict';
import { build } from 'vite';
import react from '@vitejs/plugin-react';
import { chromium } from 'playwright-core';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const output = process.env.MINUTES_LLM_TEST_OUTPUT;
if (output) mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || process.env.CHROMIUM_PATH ||
    (existsSync('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome') ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : undefined) });
const results = [];
try {
  for (const scenario of [
    { name: 'hosted uses managed transcription and text AI', edition: 'cloud', policy: 'manor', managed: true },
    { name: 'hosted local accounts retain their existing provider policy', edition: 'cloud', policy: 'local', managed: false },
    { name: 'hosted remains managed when profile fails', edition: 'cloud', policy: null, managed: true },
    { name: 'Manor identity uses managed credentials in community', edition: 'community', policy: 'manor', managed: true },
    { name: 'explicit independent community retains its model settings', edition: 'community', policy: 'local', managed: false },
    { name: 'local STT with remote LLM saves only text settings', edition: 'community', policy: 'local', managed: false, sttMode: 'local' },
    { name: 'remote STT with local LLM saves only audio settings', edition: 'community', policy: 'local', managed: false, llmMode: 'local' },
    { name: 'fully local community saves no provider settings', edition: 'community', policy: 'local', managed: false, sttMode: 'local', llmMode: 'local' },
    { name: 'unknown policy cannot reveal or submit stale provider settings', edition: 'community', policy: null, managed: null },
  ]) {
    const editsStt = scenario.managed === false && scenario.sttMode !== 'local';
    const editsLlm = scenario.managed === false && scenario.llmMode !== 'local';
    const entry = '\0minutes-settings-test.jsx';
    const compiled = await build({ root, configFile: false, envDir: false, logLevel: 'error',
      plugins: [react(), { name: 'isolated-settings-fixture',
        resolveId(id) { if (id === 'minutes-settings-test') return entry; },
        load(id) { if (id === entry) return `import React from 'react'; import {createRoot} from 'react-dom/client'; import ${JSON.stringify(join(root, 'src/index.css'))}; import ${JSON.stringify(join(root, 'src/App.css'))}; import Settings from ${JSON.stringify(join(root, 'src/components/Settings.jsx'))}; import ${JSON.stringify(join(root, 'src/Monochrome.css'))}; createRoot(document.getElementById('root')).render(React.createElement(Settings,{user:{name:'Synthetic',email:'synthetic@example.test'},onClose:()=>{}}));`; },
      }],
      build: { write: false, minify: false, rollupOptions: { input: 'minutes-settings-test', output: { format: 'iife', inlineDynamicImports: true } } },
      define: Object.fromEntries(Object.entries({ VITE_EDITION: scenario.edition, VITE_STT_MODE: scenario.sttMode || 'cloud', VITE_LLM_MODE: scenario.llmMode || 'cloud', VITE_API_URL: 'https://minutes.example.test' }).map(([key, value]) => [`import.meta.env.${key}`, JSON.stringify(value)])) });
    const js = compiled.output.find(f => f.type === 'chunk').code;
    const css = compiled.output.find(f => f.type === 'asset' && f.fileName.endsWith('.css'))?.source || '';
    const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    page.setDefaultTimeout(8000);
    const saves = [];
    let releaseProfile;
    const profileGate = new Promise(resolve => { releaseProfile = resolve; });
    try {
      await page.addInitScript(() => {
        localStorage.setItem('auth_token', 'dummy-component-token');
        localStorage.setItem('llm_model', 'stale-independent-model');
        localStorage.setItem('llm_base_url', 'https://old-provider.example.test');
        localStorage.setItem('stt_api_key', 'dummy-stale-browser-key');
        localStorage.setItem('stt_base_url', 'https://old-audio.example.test');
        localStorage.setItem('has_stt_key', 'true');
        localStorage.setItem('has_llm_key', 'true');
        window.aiConfigRefreshes = 0;
        window.addEventListener('minutes-ai-config-updated', () => { window.aiConfigRefreshes += 1; });
      });
      await page.route('**/*', async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/settings-test') return route.fulfill({ contentType: 'text/html', body: `<meta charset="utf-8"><div id="root"></div><style>${css}</style><script>${js.replaceAll('</script', '<\\/script')}</script>` });
        if (path === '/api/auth/me') {
          assert.equal(route.request().headers().authorization, 'Bearer dummy-component-token');
          await profileGate;
          return route.fulfill({ status: scenario.policy ? 200 : 503, json: scenario.policy ?
            { success: true, stt_managed_by: scenario.policy, llm_managed_by: scenario.policy, has_stt_key: true, has_llm_key: true, stt_base_url: 'https://saved-audio.example.test', llm_model: 'gpt4o-mini', llm_base_url: 'https://saved-provider.example.test' } : { detail: 'Unavailable' } });
        }
        if (path === '/api/auth/llm-config') {
          assert.equal(route.request().headers().authorization, 'Bearer dummy-component-token');
          saves.push(route.request().postDataJSON());
          return route.fulfill({ json: { success: true } });
        }
        if (path === '/api/auth/webhook') return route.fulfill({ json: { success: true } });
        return route.abort('blockedbyclient');
      });
      await page.goto('https://minutes.example.test/settings-test');
      await page.getByRole('heading', { name: 'Settings', exact: true }).waitFor();
      assert.equal(await page.locator('#sttApiKey, #sttBaseUrl, #llmApiKey, #llmBaseUrl, #llmModel').count(), 0, 'no stale provider UI before server policy');
      assert.equal(await page.locator('.quiet-managed-note').count(), 0, 'management notice waits for verified server policy');
      const profileResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/auth/me');
      releaseProfile();
      await profileResponse;
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      if (scenario.managed === true) {
        assert.equal(await page.locator('#llmApiKey, #llmBaseUrl, #llmModel').count(), 0);
        if (scenario.policy === 'manor') {
          await page.getByText('Manor manages transcription and summaries.', { exact: true }).waitFor();
        } else {
          assert.equal(await page.locator('.quiet-managed-note').count(), 0, 'an unavailable profile does not claim verified management');
        }
      } else if (scenario.managed === false) {
        await page.locator('summary').filter({ hasText: /^Transcription provider$/ }).click();
        await page.locator('summary').filter({ hasText: /^Summary provider$/ }).click();
        assert.equal(await page.getByText('Local Mode Active', { exact: true }).count(),
          Number(scenario.sttMode === 'local') + Number(scenario.llmMode === 'local'));
      } else {
        await page.locator('summary').filter({ hasText: /^Transcription provider$/ }).click();
        await page.locator('summary').filter({ hasText: /^Summary provider$/ }).click();
        await page.getByText('Independent model settings are unavailable until your account policy is verified.').waitFor();
        assert.equal(await page.locator('#llmApiKey').count(), 0);
        await page.getByText('Transcription settings are unavailable until your account policy is verified.').waitFor();
      }
      assert.equal(await page.locator('#sttApiKey').count(), Number(editsStt));
      assert.equal(await page.locator('#sttBaseUrl').count(), Number(editsStt));
      assert.equal(await page.locator('#llmApiKey').count(), Number(editsLlm));
      assert.equal(await page.locator('#llmBaseUrl, #llmModel').count(), editsLlm ? 2 : 0);
      if (editsStt) {
        await page.locator('#sttApiKey').fill('dummy-audio-key');
        await page.locator('#sttBaseUrl').fill('https://new-audio.example.test');
      }
      if (editsLlm) {
        await page.locator('#llmApiKey').fill('dummy-community-key');
        await page.locator('#llmBaseUrl').fill('https://new-provider.example.test');
        await page.locator('#llmModel').selectOption('gpt4o-mini');
      }
      await page.getByRole('button', { name: 'Save Changes', exact: true }).click();
      await page.getByText('Settings saved successfully!', { exact: true }).waitFor();
      const expected = {
        ...(editsStt && { stt_api_key: 'dummy-audio-key', stt_base_url: 'https://new-audio.example.test' }),
        ...(editsLlm && { llm_api_key: 'dummy-community-key', llm_base_url: 'https://new-provider.example.test', llm_model: 'gpt4o-mini' }),
      };
      assert.deepEqual(saves, editsStt || editsLlm ? [expected] : []);
      assert.equal(await page.evaluate(() => window.aiConfigRefreshes), editsStt || editsLlm ? 1 : 0);
      if (editsStt || editsLlm) assert.equal(await page.evaluate(() => localStorage.getItem('stt_api_key')), null);
      if (output && scenario.edition === 'cloud' && scenario.managed === true) {
        await page.getByRole('heading', { name: 'Settings', exact: true }).scrollIntoViewIfNeeded();
        await page.screenshot({ path: join(output, 'hosted-settings.png'), fullPage: true });
      }
      results.push({ name: scenario.name, passed: true, kind: 'React browser with mocked HTTP' });
    } catch (error) {
      if (output) {
        await page.screenshot({ path: join(output, 'failure.png'), fullPage: true });
        writeFileSync(join(output, 'failure-dom.txt'), await page.locator('body').innerText());
      }
      error.message = `${scenario.name}: ${error.message}`;
      throw error;
    } finally { releaseProfile(); await context.close(); }
  }
} finally {
  await browser.close();
  if (output) writeFileSync(join(output, 'results.json'), JSON.stringify({ results, realModelCalls: 0, realLogin: false }, null, 2));
}
console.log(JSON.stringify({ passed: results.length, failed: 0, realModelCalls: 0 }));
