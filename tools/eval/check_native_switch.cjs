// All edits/deletes are restricted to our own two temporary projects.
const fs=require('fs'),path=require('path');
const {chromium}=require(path.join(process.env.APPDATA,'npm/node_modules/openclaw/node_modules/playwright-core'));
const root=path.resolve('backend/.state/native-desktop');
function ready(name){return fs.readdirSync(root).some(dir=>{
 try{const s=JSON.parse(fs.readFileSync(path.join(root,dir,'status.json')));return !s.closed&&s.hwnd&&!s.suspended&&s.project?.endsWith('\\'+name)&&Date.now()/1000-s.updated<5;}catch{return false;}
});}
async function waitReady(name){const until=Date.now()+40000;while(Date.now()<until){if(ready(name))return;await new Promise(r=>setTimeout(r,150));}throw Error('Native editor not ready for '+name);}
(async()=>{
 const browser=await chromium.connectOverCDP('http://localhost:9227');
 const context=browser.contexts()[0],page=context.pages().find(p=>p.url().startsWith('http://localhost:3100'));
 const first=JSON.parse(fs.readFileSync('backend/.state/codex-20261018/native-smoke.json')).project;
 const second='smoke-native-switch-'+Date.now(),api='http://localhost:3100/api';
 try{
  const made=await context.request.post(api+'/projects',{data:{name:second}});if(!made.ok())throw Error(await made.text());
  await page.reload({waitUntil:'domcontentloaded'});await waitReady(first);
  await page.locator('.project-item-card').filter({hasText:second}).locator('.project-select').click();await waitReady(second);
  await page.evaluate(()=>window.__DECAD_DESKTOP__.request('control',{command:'save'}));
  await page.locator('.project-item-card').filter({hasText:first}).locator('.project-select').click();await waitReady(first);
  const before=await (await context.request.get(`${api}/projects/${second}/file?name=${second}.kicad_sch`)).body();
  await page.getByRole('button',{name:`Delete project ${second}`,exact:true}).click();
  await page.getByRole('button',{name:'Move to trash',exact:true}).click();
  await page.locator('.project-undo-toast').getByRole('button',{name:'Undo',exact:true}).click();await waitReady(second);
  const after=await (await context.request.get(`${api}/projects/${second}/file?name=${second}.kicad_sch`)).body();
  if(!before.equals(after))throw Error('Native project restore changed file bytes');
  await page.locator('.project-item-card').filter({hasText:first}).locator('.project-select').click();await waitReady(first);
  await page.getByRole('button',{name:'Source',exact:true}).click();
  await page.getByRole('textbox',{name:'KiCad source',exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('textarea[aria-label="KiCad source"]')?.value.includes('52.07'));
  if(!(await page.getByRole('textbox',{name:'KiCad source',exact:true}).inputValue()).includes('52.07'))throw Error('Source view missed native mouse edit');
  await page.getByRole('button',{name:'Schematic',exact:true}).click();await waitReady(first);
  await page.getByRole('button',{name:'KiCad view',exact:true}).click();
  await page.locator('kicanvas-embed[controls="basic"]').waitFor({timeout:30000});
  if(await page.locator('kc-ui-activity-side-bar').count())throw Error('Redundant activity rail still present');
  await page.getByRole('button',{name:'KiCad editor',exact:true}).click();await waitReady(first);
  console.log('PASS: native project switching, Delete/Undo, exact restored bytes, native edit in Source, preview/native switching and redundant rail removed.');
 }finally{
  await context.request.delete(api+'/projects/'+second);await browser.close();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
