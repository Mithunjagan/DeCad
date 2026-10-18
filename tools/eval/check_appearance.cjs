// Browser interaction checks; assistant response is held locally, no model/OCR job.
const assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
const {chromium}=require(path.join(process.env.APPDATA,'npm/node_modules/openclaw/node_modules/playwright-core'));
const output=path.resolve('backend/.state/codex-20261018/appearance');fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu','--disable-extensions','--renderer-process-limit=1']});
 const context=await browser.newContext({viewport:{width:1600,height:1000},colorScheme:'light',deviceScaleFactor:1.25});
 const api='http://localhost:3100/api',name='smoke-appearance-'+Date.now();let created=false,finish=()=>{},page;
 const errors=[];
 try{
  assert((await context.request.get(api+'/auth/dev')).ok());
  assert((await context.request.post(api+'/projects',{data:{name}})).ok());created=true;
  page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://localhost:3100',{waitUntil:'domcontentloaded',timeout:120000});
  const theme=page.getByLabel('Color theme');await theme.waitFor({timeout:90000});
  await page.locator('.project-item-card').filter({hasText:name}).locator('.project-select').click();
  await page.waitForFunction(()=>document.querySelector('.app')?.classList.contains('theme-daylight'));
  assert.equal(await theme.inputValue(),'system');
  await page.emulateMedia({colorScheme:'dark'});
  await page.waitForFunction(()=>document.querySelector('.app')?.classList.contains('theme-forge'));
  await theme.selectOption('theme-daylight');
  await page.emulateMedia({colorScheme:'light'});await page.emulateMedia({colorScheme:'dark'});
  assert(await page.locator('.app.theme-daylight').count());
  await page.reload({waitUntil:'domcontentloaded'});await theme.waitFor();
  assert.equal(await theme.inputValue(),'theme-daylight');
  await page.locator('.project-item-card').filter({hasText:name}).locator('.project-select').click();
  await theme.selectOption('system');
  await page.waitForFunction(()=>document.querySelector('.app')?.classList.contains('theme-forge'));
  // Keep the request pending while exercising the real loading state.
  const waiting=new Promise(resolve=>finish=resolve);
  await page.route('**/api/ai/chat',async route=>{await waiting;await route.fulfill({status:503,json:{detail:'Appearance check: intentional local response failure.'}});});
  await page.locator('.composer-textarea').fill('Appearance check only');
  await page.getByRole('button',{name:'Send command'}).click();
  await page.locator('.assistant-activity').waitFor();
  assert.equal(await page.locator('.assistant-activity').getAttribute('data-phase'),'design');
  assert.equal(await page.getByRole('button',{name:'Send command'}).isDisabled(),true);
  await page.waitForTimeout(1200);
  assert.match(await page.locator('.activity-footer').textContent(),/[1-9]\d*s/);
  const moving=await page.locator('.activity-flow').evaluate(el=>getComputedStyle(el).animationName);
  assert.equal(moving,'signal-travel');
  await page.screenshot({path:path.join(output,'dark-loading-125.png')});
  await page.emulateMedia({colorScheme:'light'});
  await page.waitForFunction(()=>document.querySelector('.app')?.classList.contains('theme-daylight'));
  await page.screenshot({path:path.join(output,'light-loading-125.png')});
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('.activity-flow').evaluate(el=>getComputedStyle(el).animationName),'none');
  assert.equal(await page.locator('.activity-flow').evaluate(el=>getComputedStyle(el).strokeDasharray),'none');
  finish();await page.locator('.assistant-activity').waitFor({state:'detached'});
  await page.getByRole('alert').filter({hasText:'Appearance check:'}).waitFor();
  assert.equal(await page.locator('.composer-textarea').inputValue(),'Appearance check only');
  for(const width of [1920,1440,1280,1024,900,390,360]){
   await page.setViewportSize({width,height:1000});
   if(width<=900)await page.getByRole('button',{name:'Assistant',exact:true}).click();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Page overflow: ${width}`);
   const bounds=await page.locator('.right-assistant-sidebar').boundingBox();
   assert(bounds&&bounds.x>=0&&bounds.x+bounds.width<=width+1,`Assistant clipped: ${width}`);
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'browser-check.json'),JSON.stringify({passed:true,scales:[1.25],widths:[1920,1440,1280,1024,900,390,360],errors},null,2));
  console.log('PASS: system light/dark updates, manual override/persistence, real pending/error UI, signal animation, reduced motion, 125% rendering and responsive widths.');
 }finally{
  finish();
  if(page&&!page.isClosed()){
   await page.waitForLoadState('networkidle',{timeout:10000}).catch(()=>{});
   await page.close();
  }
  try{
   if(created){
    let removed;
    for(let retry=0;retry<4;retry++){
     removed=await context.request.delete(api+'/projects/'+name);
     if(removed.ok()||removed.status()===404)break;
     await new Promise(resolve=>setTimeout(resolve,500));
    }
    assert(removed.ok()||removed.status()===404,`Test project cleanup failed: ${await removed.text()}`);
   }
  }finally{await browser.close();}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
