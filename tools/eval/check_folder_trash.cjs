// The Python controller holds an actual Windows subdirectory handle throughout.
const assert=require('node:assert/strict'),path=require('path'),fs=require('fs');
const {chromium}=require(path.join(process.env.APPDATA,'npm/node_modules/openclaw/node_modules/playwright-core'));
(async()=>{
 const name=process.env.DECAD_TRASH_TEST_PROJECT;assert(name?.startsWith('smoke-folder-trash-'));
 let desktop;
 for(let i=0;i<50;i++){try{desktop=await chromium.connectOverCDP('http://localhost:9227');break;}catch{await new Promise(r=>setTimeout(r,400));}}
 assert(desktop,'Native verification desktop did not start');
 const native=desktop.contexts()[0].pages().find(p=>p.url().startsWith('http://localhost:3100'));
 await native.locator('.native-kicad-pane').waitFor();
 await native.waitForFunction(()=>!document.querySelector('.native-kicad-pane .project-loading p'),null,{timeout:45000});
 assert.equal(await native.evaluate(()=>window.__DECAD_DESKTOP__.project),name);
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu','--disable-extensions','--renderer-process-limit=1']});
 const context=await browser.newContext({viewport:{width:1440,height:900}}),api='http://localhost:3100/api';
 const errors=[];native.on('pageerror',e=>errors.push(e.message));
 try{
  await context.request.get(api+'/auth/dev');const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://localhost:3100',{waitUntil:'domcontentloaded',timeout:90000});
  const card=page.locator('.project-item-card').filter({hasText:name});await card.locator('.project-select').click();
  let before;
  async function remove(){
   await page.getByRole('button',{name:`Delete project ${name}`,exact:true}).click();
   await page.getByRole('dialog',{name:'Delete project?'}).getByRole('button',{name:'Move to trash',exact:true}).click();
   await page.getByRole('button',{name:'Force move to trash',exact:true}).waitFor({timeout:35000});
   // The native editor may upgrade the empty legacy fixture during its real Save.
   if(!before)before=await (await context.request.get(`${api}/projects/${name}/file?name=${name}.kicad_sch`)).body();
   const response=page.waitForResponse(r=>r.request().method()==='DELETE'&&r.url().includes(name+'?force=true'));
   await page.getByRole('button',{name:'Force move to trash',exact:true}).click();
   const result=await response;assert(result.ok(),await result.text());const data=await result.json();assert.equal(data.retained_original,true);
   await page.locator('.project-undo-toast').waitFor();assert(!((await (await context.request.get(api+'/projects')).json()).includes(name)));
   assert.equal((await context.request.get(`${api}/projects/${name}/files`)).status(),404);
   return data;
  }
  const first=await remove();
  await native.locator('.native-kicad-pane').waitFor({state:'detached',timeout:10000});
  await page.locator('.project-undo-toast').getByRole('button',{name:'Undo',exact:true}).click();await card.waitFor();
  const after=await (await context.request.get(`${api}/projects/${name}/file?name=${name}.kicad_sch`)).body();assert(before.equals(after),'Undo changed the schematic');
  const second=await remove();
  const out=path.resolve('backend/.state/codex-20261018/folder-trash');fs.mkdirSync(out,{recursive:true});
  await page.screenshot({path:path.join(out,'browser-force-delete.png')});
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:true,realWindowsFolderLock:true,nativeSavedAndClosed:true,secondWindowObservedDeletion:true,undoPreservedSchematic:true,first,second,errors},null,2));
  console.log('PASS: browser saves/closes the matching real KiCad editor, locked-folder force removal, verified recovery, cross-window deletion, Undo and repeated force removal; no browser errors.');
  await page.close();
 }finally{await browser.close();await desktop.close();}
})().catch(e=>{console.error(e);process.exit(1)});
