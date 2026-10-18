// Connects only to the explicitly enabled off-screen verification shell.
const path=require('path'),fs=require('fs');
const {chromium}=require(path.join(process.env.APPDATA,'npm/node_modules/openclaw/node_modules/playwright-core'));
(async()=>{
 const browser=await chromium.connectOverCDP('http://localhost:9227');
 const page=browser.contexts()[0].pages().find(p=>p.url().startsWith('http://localhost:3100'));
 if(!page)throw Error('Verification shell page missing');
 const name=JSON.parse(fs.readFileSync('backend/.state/codex-20261018/native-smoke.json')).project;
 await page.locator('.native-kicad-pane').waitFor();
 const saved=await page.evaluate(()=>window.__DECAD_DESKTOP__.request('control',{command:'save'}));
 if(!saved.ok)throw Error('Native save failed');
 const status=await page.evaluate(()=>({native:!!window.__DECAD_DESKTOP__,visible:!!document.querySelector('.native-kicad-pane'),title:document.querySelector('.project-breadcrumbs')?.textContent}));
 if(!status.title.includes(name))throw Error('Wrong project opened');
 // HTML dialogs must conceal the native child rather than be covered by it.
 await page.getByRole('button',{name:`Delete project ${name}`,exact:true}).click();
 await page.getByRole('dialog',{name:'Delete project?'}).waitFor();
 await page.getByRole('button',{name:'Keep project',exact:true}).click();
 await page.evaluate(()=>window.__DECAD_DESKTOP__.request('control',{command:'zoom_in'}));
 await page.evaluate(()=>window.__DECAD_DESKTOP__.request('control',{command:'zoom_out'}));
 console.log('PASS: real desktop WebView bridge, native Save, native zoom commands, project identity and accessible delete dialog.');
 await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1;});
