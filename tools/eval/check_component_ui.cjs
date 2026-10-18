// Read-only UI check through installed headless Edge. No image recognition.
const fs=require('fs'),path=require('path');
const {chromium}=require(path.join(process.env.APPDATA,'npm/node_modules/openclaw/node_modules/playwright-core'));
(async()=>{
 const output=path.resolve('backend/.state/codex-20261018/component-api');
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu','--disable-extensions','--renderer-process-limit=1']});
 let context,pid;
 try{
  context=await browser.newContext({viewport:{width:1600,height:1100}});
  const login=await context.request.get('http://localhost:3100/api/auth/dev');
  if(!login.ok())throw new Error('Local login failed: '+login.status());
  if(process.argv.includes('--place')){
   pid='smoke-library-ui-'+Date.now();
   const create=await context.request.post('http://localhost:3100/api/projects',{data:{name:pid}});
   if(!create.ok())throw new Error('Temporary project creation failed');
  }
  const page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://localhost:3100',{waitUntil:'domcontentloaded',timeout:120000});
  if(pid)await page.locator('.project-item-card').filter({hasText:pid}).click({timeout:30000});
  await page.getByRole('button',{name:'Libraries & footprints',exact:true}).click({timeout:120000});
  await page.getByRole('heading',{name:'Unified KiCad & OrCAD component database'}).waitFor();
  await page.getByText('Library locations, asset import and source permissions',{exact:true}).click();
  await page.getByRole('button',{name:'KiCad:',exact:false}).first().waitFor({timeout:30000});
  await page.getByText('Format and version support',{exact:true}).click();
  await page.getByRole('cell',{name:'.brd',exact:true}).waitFor();
  if(pid){
   await page.getByRole('searchbox',{name:'Search components',exact:true}).fill('Timer:NE555P');
   await page.getByLabel('Query authorized external providers if absent locally',{exact:true}).uncheck();
   await page.getByRole('button',{name:'Find component and add to project',exact:true}).click();
   await page.getByRole('status').filter({hasText:'U1 added with a verified pin/pad mapping'}).first().waitFor({timeout:60000});
   const details=await (await context.request.get(`http://localhost:3100/api/projects/${pid}/details`)).json();
   if(details.components.length!==1||details.components[0].ref!=='U1')throw new Error('Placed component was not saved');
   if(await page.getByRole('textbox',{name:'Acquired component reference',exact:true}).inputValue()!=='U2')throw new Error('Reference did not advance');
   const response=page.waitForResponse(r=>r.url().endsWith(`/projects/${pid}/components/acquire`)&&r.request().method()==='POST');
   await page.getByRole('button',{name:'Find component and add to project',exact:true}).click();
   const second=await (await response).json();
   if(second.status!=='ready'||second.placement.position.x===50.8&&second.placement.position.y===50.8)throw new Error('Second component did not get a separate position');
   const updated=await (await context.request.get(`http://localhost:3100/api/projects/${pid}/details`)).json();
   if(updated.components.length!==2||!updated.components.some(c=>c.ref==='U2'))throw new Error('Second placement was not saved');
  }
  await page.screenshot({path:path.join(output,pid?'library-find-add.png':'library-browser.png'),fullPage:true});
  if(errors.length)throw new Error(errors.join('\n'));
  console.log('UI passed: unified browser, local discovery, format matrix, '+(pid?'real find-and-add placement, ':'')+'no page errors');
 }finally{
  if(context&&pid){
   const cleanup=await context.request.delete(`http://localhost:3100/api/projects/${pid}`);
   if(!cleanup.ok())throw new Error('Temporary project cleanup failed');
   fs.writeFileSync(path.join(output,'ui-cleanup.json'),JSON.stringify(await cleanup.json()));
  }
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
