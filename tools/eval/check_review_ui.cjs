// UI-only 24-part/235-net fixture. No OCR, model, EDA import or real project edits.
const assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
const {chromium}=require(path.join(process.env.APPDATA,'npm/node_modules/openclaw/node_modules/playwright-core'));
const out=path.resolve('backend/.state/codex-20261018/review-ui');fs.mkdirSync(out,{recursive:true});
const fixture={sheet_aspect:1.4,components:Array.from({length:24},(_,i)=>({ref:'U'+(i+1),value:'74F244',library:'74xx:74LS244',x:.1+i*.02,y:.2})),nets:Array.from({length:235},(_,i)=>({name:'DATA_'+String(i).padStart(3,'0'),nodes:[0,1].map(j=>{const p=i*2+j;return {ref:'U'+(Math.floor(p/20)+1),pin:String(p%20+1)};})})),warnings:['UI fixture: confirm pin assignments against the source.']};
const source='<svg xmlns="http://www.w3.org/2000/svg" width="600" height="350"><rect width="600" height="350" fill="#fff"/><g stroke="#263d30" fill="none" stroke-width="3"><path d="M60 175h150m180 0h150"/><rect x="210" y="90" width="180" height="170"/></g><g font-size="24" font-family="sans-serif" fill="#263d30"><text x="260" y="65">U1</text><text x="245" y="180">74F244</text></g></svg>';
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-gpu','--disable-extensions','--renderer-process-limit=1']});
 const context=await browser.newContext({viewport:{width:1600,height:1000},deviceScaleFactor:1.25,colorScheme:'dark'});
 const api='http://localhost:3100/api',name='smoke-review-'+Date.now();let made=false,page,received,imported,fail=false;
 const errors=[];
 try{
  assert((await context.request.get(api+'/auth/dev')).ok());assert((await context.request.post(api+'/projects',{data:{name}})).ok());made=true;
  assert((await context.request.post(`${api}/projects/${name}/attachments?name=source.svg`,{data:source,headers:{'Content-Type':'image/svg+xml'}})).ok());
  page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.route(`**/api/projects/${name}/details`,route=>route.fulfill({json:{components:fixture.components,nets:fixture.nets.map((n,i)=>({...n,class:'Default',nodes:i===234?[n.nodes[0]]:n.nodes})),checks:[{severity:'warning',description:'UI fixture'}],validation:{status:'completed',passed:false},revisions:[],files:[]}}));
  await page.route('**/api/ai/chat',async route=>{received=route.request().postDataJSON();await route.fulfill(fail?{status:422,json:{detail:'Unsupported command. '+('Supported command details. '.repeat(20))}}:{json:{reply:'Review the UI fixture before applying.',proposal:fixture}});});
  await page.route(`**/api/projects/${name}/import`,async route=>{imported=route.request().postDataJSON();await route.fulfill({json:{edits:[],output:{ready:false}}});});
  await page.goto('http://localhost:3100',{waitUntil:'domcontentloaded',timeout:120000});
  await page.locator('.project-item-card').filter({hasText:name}).locator('.project-select').click({timeout:90000});
  await page.waitForFunction(()=>document.querySelector('.workspace-heading p')?.textContent.includes('24 components'));
  await page.locator('.tab-btn').filter({hasText:/^Nets/}).click();
  await page.getByLabel('Search electrical nets').waitFor();assert.equal(await page.locator('.schematic-secondary-toolbar').isVisible(),false);
  await page.getByLabel('Filter net connections').selectOption('single');assert.equal(await page.locator('.nets-table tbody tr').count(),1);
  await page.getByLabel('Filter net connections').selectOption('all');
  await page.getByLabel('Search electrical nets').fill('U1:1');assert((await page.locator('.nets-table tbody tr').count())>0);
  await page.getByLabel('Search electrical nets').fill('');
  await page.locator('.nets-table-scroll').evaluate(el=>el.scrollTop=700);
  const header=await page.locator('.nets-table th').first().boundingBox(),scroll=await page.locator('.nets-table-scroll').boundingBox();assert(Math.abs(header.y-scroll.y)<2,'Net header is not fixed to its scroll region');
  await page.screenshot({path:path.join(out,'netlist-125.png')});
  // A copied display label must resolve to real attachment metadata.
  await page.locator('.composer-textarea').fill('create a design [Attached: source.svg]');await page.getByRole('button',{name:'Send command'}).click();
  const dialog=page.getByRole('dialog',{name:'Review circuit',exact:true});await dialog.waitFor();
  assert.deepEqual(received.attachments,['references/source.svg']);assert.equal(received.message,'create a design');
  const apply=()=>dialog.getByRole('button',{name:'Import into KiCad project',exact:true});
  assert(await apply().isDisabled());
  await dialog.getByLabel('Filter components').fill('U1');assert((await dialog.getByLabel(/Component \d+ reference/).count())<24);
  await dialog.getByLabel('Filter components').fill('');
  await dialog.getByLabel('Component 1 reference',{exact:true}).fill('U101');
  await dialog.getByRole('tab',{name:/Connections/}).click();
  await dialog.getByLabel('Filter nets').fill('DATA_000');
  assert.equal(await dialog.getByLabel('Connection 1 component').inputValue(),'U101');
  await dialog.getByLabel('Connection 1 physical pin').fill('2');
  assert(await dialog.getByRole('checkbox').isDisabled());
  await dialog.getByRole('tab',{name:/Review notes/}).click();await dialog.getByText(/assigned more than once/).first().waitFor();
  await dialog.getByRole('button',{name:'Undo edit',exact:true}).click();
  assert(await dialog.getByRole('checkbox').isEnabled());
  await dialog.getByRole('tab',{name:'JSON',exact:true}).click();
  const raw=JSON.parse(await dialog.getByLabel('Circuit JSON').inputValue());assert.equal(raw.components[0].x,.1);assert.equal(raw.nets[0].nodes[0].ref,'U101');
  await dialog.getByLabel('Circuit JSON').fill('{bad');assert(await apply().isDisabled());
  await dialog.getByRole('button',{name:'Use JSON changes'}).click();await dialog.getByRole('alert').waitFor();
  await dialog.getByRole('button',{name:'Discard JSON changes'}).click();
  await dialog.getByRole('tab',{name:/Components/}).click();
  await dialog.getByRole('button',{name:'Compare source'}).click();
  await dialog.getByAltText('Original schematic for comparison').waitFor();
  await dialog.getByRole('button',{name:'Zoom source in'}).click();
  await page.screenshot({path:path.join(out,'review-source-125.png')});
  await dialog.getByRole('button',{name:'Hide source'}).click();
  for(const width of [1920,1440,1024,768,390,320]){
   await page.setViewportSize({width,height:844});
   const box=await dialog.boundingBox();assert(box.x>=0&&box.x+box.width<=width+1,`Dialog outside ${width}`);
   assert(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),`Dialog horizontal overflow ${width}`);
   const check=await dialog.getByRole('checkbox').boundingBox(),label=await dialog.getByRole('checkbox').locator('..').boundingBox();assert(check.width<25&&label.width>check.width*3,`Checkbox layout regressed ${width}`);
   const footer=await dialog.locator('footer').boundingBox();assert(footer.y+footer.height<=844+1,`Footer clipped ${width}`);
   assert(await apply().isVisible());
   const target=await dialog.getByLabel('Review export target').boundingBox();assert(target.width>100,`Export target squeezed ${width}`);
   if([1440,390,320].includes(width))await page.screenshot({path:path.join(out,`review-${width}.png`)});
  }
  await page.setViewportSize({width:1600,height:1000});await page.getByLabel('Color theme').selectOption('theme-daylight');
  await page.waitForFunction(()=>document.querySelector('.app')?.classList.contains('theme-daylight'));
  await page.screenshot({path:path.join(out,'review-light.png')});
  await dialog.getByRole('checkbox').check();
  await dialog.getByLabel('Review export target').selectOption('orcad');assert(await dialog.getByRole('button',{name:'Generate & verify OrCAD .DSN'}).isEnabled());
  await dialog.getByLabel('Review export target').selectOption('kicad');
  await apply().click();await dialog.waitFor({state:'detached'});assert.equal(imported.circuit.components[0].ref,'U101');assert.equal(imported.circuit.components[0].x,.1);assert.equal(imported.circuit.nets[0].nodes[0].ref,'U101');
  // Error details stay collapsed and Retry preserves the source.
  fail=true;await page.locator('.composer-textarea').fill('create a design [Attached: source.svg]');await page.getByRole('button',{name:'Send command'}).click();
  const alert=page.getByRole('alert').filter({hasText:'Request not applied'});await alert.waitFor();assert.equal(await alert.locator('details').getAttribute('open'),null);
  fail=false;await alert.getByRole('button',{name:'Retry request'}).click();await dialog.waitFor();assert.deepEqual(received.attachments,['references/source.svg']);
  await page.screenshot({path:path.join(out,'review-final.png')});
  await dialog.getByRole('button',{name:'Close dialog'}).click();
  assert.deepEqual(errors,[]);console.log('PASS: 24 parts/235 nets, source/zoom, search, reference-to-pin preservation, duplicate-pin gate, JSON guard, checkbox/footer at six widths, target choice, import payload, copied attachment and retry, sticky net header; no browser errors.');
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:true,fixture:true,ocrRun:false,parts:24,nets:235,widths:[1920,1440,1024,768,390,320],scale:1.25,errors},null,2));
 }catch(error){
  if(page&&!page.isClosed()){await page.screenshot({path:path.join(out,'failure.png')});console.error('UI diagnostics',JSON.stringify({errors,received,text:await page.locator('.right-assistant-sidebar').innerText().catch(()=>'' )}));}
  throw error;
 }finally{
  if(page&&!page.isClosed()){await page.waitForLoadState('networkidle',{timeout:8000}).catch(()=>{});await page.close();}
  if(made){let r;for(let i=0;i<4;i++){r=await context.request.delete(`${api}/projects/${name}`);if(r.ok()||r.status()===404)break;await new Promise(resolve=>setTimeout(resolve,500));}assert(r.ok()||r.status()===404,await r.text());}
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exit(1)});
