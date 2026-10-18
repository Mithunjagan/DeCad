// Real app path: upload sheet -> assistant -> CUDA worker -> review -> native DSN.
const assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),cp=require('child_process');
const {chromium}=require(path.join(process.env.APPDATA,'npm/node_modules/openclaw/node_modules/playwright-core'));
const out=path.resolve('backend/.state/codex-20261018/gpu-runtime');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu','--disable-extensions','--renderer-process-limit=1']});
 const context=await browser.newContext({viewport:{width:1600,height:1000}}),api='http://localhost:3100/api';
 const name='smoke-app-gpu-'+Date.now(),source='Sample 1.jpg.jpeg';let made=false,page;const samples=[],errors=[];
 try{
  await context.request.get(api+'/auth/dev');let response=await context.request.post(api+'/projects',{data:{name}});assert(response.ok(),await response.text());made=true;
  page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto('http://localhost:3100',{waitUntil:'domcontentloaded'});
  const loaded=page.waitForResponse(r=>r.url().endsWith(`/projects/${name}/details`));
  await page.locator('.project-item-card').filter({hasText:name}).locator('.project-select').click();await loaded;
  await page.locator('.composer-textarea').fill('Analyze the attached schematic');
  const resultPromise=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/ai/chat'),{timeout:900000});
  let finished=false;resultPromise.then(()=>{finished=true;},()=>{finished=true;});let observedCuda=false,shot=false;
  await page.locator('input[type=file]').first().setInputFiles(path.resolve('../../ORCAD JPG Source file-20261015T225949Z-1-001/ORCAD JPG Source file',source));
  await page.locator('.assistant-activity').waitFor();
  while(!finished){
   const runtime=await (await context.request.get(api+'/vision/status')).json();
   let telemetry='';try{telemetry=cp.execFileSync('nvidia-smi',['--query-gpu=utilization.gpu,memory.used','--format=csv,noheader,nounits'],{encoding:'utf8',windowsHide:true}).trim();}catch{}
   samples.push({time:Date.now(),runtime,telemetry});
   if(runtime.runtime?.gpu_verified&&runtime.runtime.state==='running'){
    observedCuda=true;
    if(!shot){await page.locator('.activity-runtime').filter({hasText:'CUDA'}).waitFor({timeout:12000});await page.screenshot({path:path.join(out,'app-gpu-running.png')});shot=true;}
   }
   await new Promise(r=>setTimeout(r,2500));
  }
  const result=await resultPromise;assert(result.ok(),await result.text());const body=await result.json();
  assert(body.proposal?.components?.length,'No actual recognition proposal');assert(observedCuda,'App never reported live CUDA');
  fs.writeFileSync(path.join(out,'S1-app-proposal.json'),JSON.stringify(body.proposal,null,2));
  await page.getByRole('dialog',{name:'Review circuit',exact:true}).waitFor();await page.screenshot({path:path.join(out,'app-gpu-review.png')});
  // Export only this disposable fixture; no user project or recognition source is edited.
  const exported=await context.request.post(`${api}/projects/${name}/export/orcad-dsn`,{data:{circuit:body.proposal,source},timeout:180000});assert(exported.ok(),await exported.text());
  const runtime=await (await context.request.get(api+'/vision/status')).json();assert(runtime.runtime.gpu_verified);assert.equal(runtime.runtime.device,'cuda');assert.equal(runtime.runtime.workspace_libraries,true);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'app-result.json'),JSON.stringify({passed:true,project:name,runtime,telemetry:samples,errors,exportVerification:exported.headers()['x-verification']},null,2));
  console.log(JSON.stringify({passed:true,project:name,parts:body.proposal.components.length,nets:body.proposal.nets.length,runtime:runtime.runtime,exportVerification:exported.headers()['x-verification'],maxGpuPercent:Math.max(...samples.map(s=>parseInt(s.telemetry)||0))},null,2));
  // Keep a complete evidence copy before putting our generated project in trash.
  fs.cpSync(path.resolve('backend/workspaces/local',name,'orcad'),path.join(out,'S1-orcad'),{recursive:true});
 }catch(error){
  fs.writeFileSync(path.join(out,'app-failure.json'),JSON.stringify({error:String(error),samples,errors},null,2));
  if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'app-failure.png')});throw error;
 }finally{
  if(page&&!page.isClosed())await page.close();
  if(made){const r=await context.request.delete(`${api}/projects/${name}?force=true`);assert(r.ok()||r.status()===404,await r.text());}
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exit(1)});
