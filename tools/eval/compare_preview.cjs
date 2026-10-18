// Render the saved Capture preview beside a source thumbnail. Uses the installed Edge browser.
const fs = require('fs');
const path = require('path');
const { chromium } = require(path.join(process.env.APPDATA, 'npm/node_modules/openclaw/node_modules/playwright-core'));

(async () => {
  const [source, preview, output] = process.argv.slice(2);
  if (!output) throw new Error('usage: node compare_preview.cjs source.png preview.svg comparison.png');
  const data = (file, type) => `data:${type};base64,${fs.readFileSync(file).toString('base64')}`;
  const browser = await chromium.launch({channel: 'msedge', headless: true,
    args: ['--disable-gpu', '--disable-extensions', '--renderer-process-limit=1']});
  try {
    const page = await browser.newPage({viewport: {width: 2400, height: 1100}, deviceScaleFactor: 1});
    await page.setContent(`<style>body{margin:0;background:#e9e9e9;font:20px Arial}main{display:flex;gap:12px}section{width:1194px}h3{margin:12px}img{width:1194px;height:1030px;object-fit:contain;background:white}</style>
      <main><section><h3>Source scan</h3><img src="${data(source, 'image/png')}"></section>
      <section><h3>Saved DSN preview</h3><img src="${data(preview, 'image/svg+xml')}"></section></main>`);
    await page.locator('img').evaluateAll(images => Promise.all(images.map(img => img.decode())));
    await page.screenshot({path: output});
    console.log(output);
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
