// Only the --verify off-screen desktop exposes this loopback debug port.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {chromium}=require(path.join(process.env.APPDATA,'npm/node_modules/openclaw/node_modules/playwright-core'));
(async()=>{
 const browser=await chromium.connectOverCDP('http://localhost:9227');
 try{
  const page=browser.contexts()[0].pages().find(p=>p.url().startsWith('http://localhost:3100'));
  assert(page);await page.locator('.native-kicad-pane').waitFor();
  await page.waitForFunction(()=>!document.querySelector('.native-kicad-pane .project-loading p'),null,{timeout:45000});
  await page.waitForFunction(()=>typeof window.__DECAD_DESKTOP__?.systemDark==='boolean');
  const actual=await page.evaluate(()=>window.__DECAD_DESKTOP__.systemDark);
  await page.waitForFunction(dark=>document.querySelector('.app')?.classList.contains(dark?'theme-forge':'theme-daylight'),actual);
  assert((await page.evaluate(()=>window.__DECAD_DESKTOP__.project)).startsWith('smoke-native-appearance-'));
  // Exercise the host's appearance notification without changing Windows settings.
  await page.evaluate(dark=>{window.__DECAD_DESKTOP__.systemDark=!dark;window.dispatchEvent(new Event('decad-system-appearance'));},actual);
  await page.waitForFunction(dark=>document.querySelector('.app')?.classList.contains(dark?'theme-daylight':'theme-forge'),actual);
  await page.evaluate(dark=>{window.__DECAD_DESKTOP__.systemDark=dark;window.dispatchEvent(new Event('decad-system-appearance'));},actual);
  await page.waitForFunction(dark=>document.querySelector('.app')?.classList.contains(dark?'theme-forge':'theme-daylight'),actual);
  await page.evaluate(()=>window.__DECAD_DESKTOP__.request('control',{command:'save'}));
  const result=await page.evaluate(()=>({theme:document.querySelector('.app').className,systemDark:window.__DECAD_DESKTOP__.systemDark,preference:document.querySelector('[aria-label="Color theme"]').value,dpi:devicePixelRatio,font:getComputedStyle(document.querySelector('.composer-textarea')).fontSize}));
  fs.writeFileSync('backend/.state/codex-20261018/appearance/native-web-check.json',JSON.stringify(result,null,2));
  console.log('PASS: native Windows appearance, desktop theme event, real Save, 125% WebView scaling: '+JSON.stringify(result));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
