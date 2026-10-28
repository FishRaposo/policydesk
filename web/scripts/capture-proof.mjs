// Capture actual UI states; no fabricated images or model measurements.
import { chromium } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '../..');
const output = path.join(root, 'docs/media');
await mkdir(output, {recursive:true});
const browser = await chromium.launch({channel: process.env.CI ? undefined : 'msedge'});
const context = await browser.newContext();
const page = await context.newPage();
const base = process.env.POLICYDESK_PREVIEW_URL || 'http://127.0.0.1:4177/policydesk/';
const files = [];
try {
  for (const width of [390,768,1440]) {
    await page.setViewportSize({width,height:900});
    await page.goto(base);
    await page.getByLabel('Ticket language',{exact:true}).selectOption('en');
    for (const [name,selector] of [['approval','01 Damaged item'],['refusal','04 Another customer’s order']]) {
      await page.getByRole('button',{name:selector,exact:true}).click();
      const filename = `${name}-${width}.png`;
      await page.screenshot({path:path.join(output,filename),fullPage:true}); files.push(filename);
    }
  }
  await page.setViewportSize({width:1280,height:900});
  await page.goto(base);
  await page.getByLabel('Ticket language',{exact:true}).selectOption('en');
  await page.screenshot({path:path.join(output,'proof-frame-01.png')});
  await page.getByRole('button',{name:'Simulate approval',exact:true}).click();
  await page.screenshot({path:path.join(output,'proof-frame-02.png')});
  await page.getByRole('button',{name:'04 Another customer’s order',exact:true}).click();
  await page.screenshot({path:path.join(output,'proof-frame-03.png')});
  files.push('proof-frame-01.png','proof-frame-02.png','proof-frame-03.png');
  const inputHashes = {};
  for (const folder of ['web/src','src/policydesk']) {
    for (const name of (await readdir(path.join(root,folder),{recursive:true})).sort()) {
      if (!/\.(?:ts|css|json|jsonl|yaml|py|sha256)$/.test(name) || name.includes('__pycache__')) continue;
      const relative = `${folder}/${name.replaceAll('\\','/')}`;
      inputHashes[relative] = createHash('sha256').update(await readFile(path.join(root,relative))).digest('hex');
    }
  }
  await writeFile(path.join(output,'capture-manifest.json'),JSON.stringify({
    provenance:'actual_browser_render_of_synthetic_data',browser:browser.version(),
    viewports:[390,768,1440],gifViewport:{width:1280,height:900},files,inputHashes,
    command:'npm run proof (with local production preview running)',
  },null,2)+'\n');
  console.log(`Captured ${files.length} actual UI screenshots; no model calls.`);
} finally { await context.close(); await browser.close(); }
