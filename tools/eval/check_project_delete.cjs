// Real browser project management acceptance. Touches only its own smoke project.
const fs=require('fs'),path=require('path');
const {chromium}=require(path.join(process.env.APPDATA,'npm/node_modules/openclaw/node_modules/playwright-core'));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu','--disable-extensions','--renderer-process-limit=1']});
 const context=await browser.newContext({viewport:{width:1600,height:1050}});
 const name='smoke-delete-'+Date.now(),api='http://localhost:3100/api';let receipt;
 try{
  await context.request.get(api+'/auth/dev');
  const made=await context.request.post(api+'/projects',{data:{name}});if(!made.ok())throw Error(await made.text());
  const before=await (await context.request.get(`${api}/projects/${name}/file?name=${name}.kicad_sch`)).body();
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://localhost:3100',{waitUntil:'domcontentloaded',timeout:120000});
  const card=page.locator('.project-item-card').filter({hasText:name});
  await card.locator('.project-select').click({timeout:60000});
  await page.getByRole('button',{name:`Delete project ${name}`,exact:true}).click();
  await page.getByRole('dialog',{name:'Delete project?'}).waitFor();
  await page.getByRole('button',{name:'Keep project',exact:true}).click();
  if(!(await context.request.get(api+'/projects')).ok())throw Error('List failed');
  if(!(await (await context.request.get(api+'/projects')).json()).includes(name))throw Error('Cancel deleted project');
  await page.getByRole('button',{name:`Delete project ${name}`,exact:true}).click();
  const deletion=page.waitForResponse(r=>r.request().method()==='DELETE'&&r.url().endsWith('/projects/'+name));
  await page.getByRole('button',{name:'Move to trash',exact:true}).click();
  const removed=await deletion;if(!removed.ok())throw Error(await removed.text());receipt=(await removed.json()).receipt;
  await page.locator('.project-undo-toast').getByRole('button',{name:'Undo',exact:true}).waitFor();
  if((await (await context.request.get(api+'/projects')).json()).includes(name))throw Error('Deleted project still listed');
  await page.locator('.project-undo-toast').getByRole('button',{name:'Undo',exact:true}).click();
  await card.waitFor({timeout:30000});
  const after=await (await context.request.get(`${api}/projects/${name}/file?name=${name}.kicad_sch`)).body();
  if(!before.equals(after))throw Error('Restore changed schematic bytes');
  if((await context.request.post(`${api}/projects/${name}/restore`,{data:{receipt}})).status()!==409)throw Error('Restore overwrote live project');
  if((await context.request.post(`${api}/projects/${name}/restore`,{data:{receipt:'../other'}})).status()!==400)throw Error('Unsafe recovery receipt accepted');
  const dir=path.resolve('backend/.state/codex-20261018/project-ui');fs.mkdirSync(dir,{recursive:true});
  await page.screenshot({path:path.join(dir,'delete-undo.png'),fullPage:true});
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: visible Delete, cancel, recoverable deletion, Undo, exact file preservation, collision and path guards; no page errors.');
 }finally{await context.request.delete(api+'/projects/'+name);await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
