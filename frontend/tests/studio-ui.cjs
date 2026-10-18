const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const path=require('node:path');
const fs=require('node:fs');
const output=path.resolve(__dirname,'../../evidence/studio-ui');fs.mkdirSync(output,{recursive:true});
const base=process.env.UI_BASE_URL || 'http://localhost:3100';
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.UI_BROWSER_CHANNEL?{channel:process.env.UI_BROWSER_CHANNEL}:{})});
 const context=await browser.newContext({viewport:{width:1440,height:900}});const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const overflow=async()=>page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,body:document.body.scrollWidth}));
 await page.goto(base,{waitUntil:'networkidle'});
 await page.getByRole('heading',{name:/Great circuits/}).waitFor();
 for(const width of [1440,1024,768,390,360,320]){
   await page.setViewportSize({width,height:width<600?844:900});
   const size=await overflow();assert(size.scroll<=width,`Welcome overflow at ${width}: ${JSON.stringify(size)}`);
   await page.screenshot({path:path.join(output,`welcome-${width}.png`),fullPage:true});
 }
 await page.setViewportSize({width:1440,height:900});
 await page.getByRole('button',{name:'Open local workspace',exact:true}).click();
 await page.locator('.app').waitFor();await page.waitForFunction(()=>!document.querySelector('.project-loading'),{},{timeout:30000});await page.waitForTimeout(700);
 console.log('Live local session opened; projects:',await page.locator('.project-item-card').count());
 for(const width of [1920,1440,1280,1024,900,768,390,360,320]){
   await page.setViewportSize({width,height:width<600?844:900});
   const size=await overflow();assert(size.scroll<=width,`Workspace overflow at ${width}: ${JSON.stringify(size)}`);
   assert(await page.locator('.center-editor-container').isVisible(),`Workspace hidden at ${width}`);
   for(const button of await page.locator('.top-navbar button:visible').all()){const bounds=await button.boundingBox();assert(bounds.x>=0&&bounds.x+bounds.width<=width,`Header button clipped at ${width}`);}
   await page.screenshot({path:path.join(output,`workspace-${width}.png`),fullPage:true});
   if(width>900){const bounds=await page.locator('.assistant-settings').boundingBox();assert(bounds.x+bounds.width<=width,`Assistant settings clipped at ${width}`);}
   if(width<=900){
     await page.getByRole('button',{name:'Assistant',exact:true}).click();
     assert(await page.locator('.right-assistant-sidebar').isVisible());
     const bounds=await page.locator('.assistant-settings').boundingBox();assert(bounds.x>=0&&bounds.x+bounds.width<=width,`Assistant settings clipped at ${width}`);
     await page.locator('.assistant-settings summary').click();assert(await page.getByLabel('Output software').isVisible());await page.locator('.assistant-settings summary').click();
     assert(!await page.locator('.center-editor-container').isVisible());
     await page.screenshot({path:path.join(output,`assistant-${width}.png`),fullPage:true});
     await page.getByRole('button',{name:'Projects',exact:true}).click();
     assert(await page.locator('.left-nav-sidebar').isVisible());
     await page.getByRole('button',{name:'Workspace',exact:true}).click();
   }
 }
 await page.setViewportSize({width:1440,height:900});
 await page.keyboard.press('Control+k');await page.getByRole('combobox',{name:'Search commands and projects'}).fill('new project');await page.keyboard.press('Enter');
 await page.getByRole('dialog',{name:'New circuit project'}).waitFor();
 await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
 await page.getByRole('button',{name:'Focus',exact:true}).click();assert(!await page.locator('.left-nav-sidebar').isVisible());assert(!await page.locator('.right-assistant-sidebar').isVisible());
 await page.getByRole('button',{name:'Show panels',exact:true}).click();
 await page.locator('.starter-prompt').first().click();assert.equal(await page.getByRole('textbox',{name:'Circuit command'}).inputValue(),'create a voltage divider');
 await page.getByRole('textbox',{name:'Circuit command'}).fill('');
 await page.getByLabel('Color theme').selectOption('theme-daylight');await page.waitForTimeout(350);await page.screenshot({path:path.join(output,'workspace-light.png'),fullPage:true});
 await page.reload({waitUntil:'networkidle'});assert(await page.locator('.app.theme-daylight').count());await page.getByLabel('Color theme').selectOption('theme-forge');
 for(const tab of ['BOM','Nets','Checks','History','Source','Schematic']) {await page.locator('.tab-btn').filter({hasText:new RegExp(`^${tab}`)}).click();await page.waitForTimeout(250);}
 await page.keyboard.press('Control+k');await page.getByRole('combobox',{name:'Search commands and projects'}).fill('no command matches');assert(await page.getByText('No matching commands.').count());await page.keyboard.press('Escape');

 // UI-only recognition fixture: exercise review without writing to a real project.
 const sample={components:[{ref:'R1',value:'10k',library:'Device:R'},{ref:'V1',value:'5',library:'Simulation_SPICE:VDC'}],nets:[{name:'VIN',nodes:[{ref:'V1',pin:'1'},{ref:'R1',pin:'1'}]},{name:'GND',nodes:[{ref:'V1',pin:'2'},{ref:'R1',pin:'2'}]}]};
 await page.route('**/api/ai/chat',route=>route.fulfill({json:{reply:'UI test proposal: review before applying.',proposal:sample}}));
 await page.getByRole('textbox',{name:'Circuit command'}).fill('UI review fixture');await page.getByRole('button',{name:'Send command'}).click();
 await page.getByRole('dialog',{name:'Review circuit',exact:true}).waitFor();
 for(const width of [1440,768,390,320]){
   await page.setViewportSize({width,height:844});
   const box=await page.getByRole('dialog').boundingBox();assert(box.x>=0&&box.x+box.width<=width,`Review dialog overflow at ${width}`);
   await page.screenshot({path:path.join(output,`review-${width}.png`),fullPage:true});
 }
 assert(await page.getByRole('button',{name:'Import into KiCad project',exact:true}).isDisabled());
 await page.getByLabel('I checked the component values').check();assert(await page.getByRole('button',{name:'Import into KiCad project',exact:true}).isEnabled());
 await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
 await page.setViewportSize({width:1440,height:900});
 await page.locator('.tab-btn').filter({hasText:/^Nets/}).click();
 await page.getByTitle('Download in chosen format').click();
 await page.getByRole('button',{name:/PCB autorouter Specctra DSN/}).click();
 await page.getByRole('dialog',{name:'Export PCB and Specctra DSN',exact:true}).waitFor();
 for(const width of [1440,390]){await page.setViewportSize({width,height:844});await page.screenshot({path:path.join(output,`pcb-export-${width}.png`),fullPage:true});const box=await page.getByRole('dialog').boundingBox();assert(box.x>=0&&box.x+box.width<=width);}
 await page.keyboard.press('Escape');
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Account menu'}).click();await page.getByRole('button',{name:'Link GitHub account',exact:true}).click();await page.getByRole('dialog',{name:'Connect GitHub',exact:true}).waitFor();await page.screenshot({path:path.join(output,'github-dialog-390.png'),fullPage:true});await page.keyboard.press('Escape');
 // Empty workspace uses the same real UI with a read-only project-list fixture.
 const emptyPage=await context.newPage();await emptyPage.route('**/api/projects',route=>route.request().method()==='GET'?route.fulfill({json:[]}):route.continue());await emptyPage.goto(base,{waitUntil:'networkidle'});await emptyPage.getByRole('button',{name:'Create your first project',exact:true}).waitFor();await emptyPage.screenshot({path:path.join(output,'empty-workspace.png'),fullPage:true});await emptyPage.close();
 assert.deepEqual(errors,[],'Browser runtime errors');console.log('PASS: live session, 9 workspace widths, 6 welcome widths, mobile panels, command palette, project dialog, focus mode, prompt presets, persistent light theme, view tabs, reviewed-circuit gates (fixture), live PCB dialog, GitHub dialog, empty workspace (fixture); no browser errors.');
 await browser.close();
})().catch(error=>{console.error(error);process.exit(1);});
