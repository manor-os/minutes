import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { statSync } from 'node:fs';
const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(resolve(here, '../../../phone-recorder/package.json'));
const { chromium } = require('playwright-core');
if (!process.env.CHROMIUM_PATH) throw new Error('Set CHROMIUM_PATH to Chrome/Chromium.');
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 640 }, deviceScaleFactor: 1 });
  await page.route(/^https?:/, route => route.abort('blockedbyclient'));
  await page.goto(pathToFileURL(join(here, 'social-preview.html')).href);
  const path = resolve(here, '../assets/github-social-preview.png');
  await page.screenshot({ path });
  const bytes = statSync(path).size;
  if (bytes >= 1000000) throw new Error('Social preview exceeds 1 MB.');
  console.log(JSON.stringify({ width: 1280, height: 640, bytes }));
} finally { await browser.close(); }
