import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {chromium} from 'playwright';

const base=process.env.CITY_URL||'http://127.0.0.1:4173/';
const evidence=path.resolve('../renders/flight');await mkdir(evidence,{recursive:true});
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const protectedFiles=['public/assets/city.json','public/assets/geometry.bin','public/assets/traffic_network.json','public/assets/characters/pedestrian.glb'];
const originalFiles=Object.fromEntries(await Promise.all(protectedFiles.map(async file=>[file,digest(await readFile(file))])));
const cityData=JSON.parse(await readFile('public/assets/city.json','utf8'));
const tower=cityData.instances.find(i=>i.prototype.startsWith('tower_')),sourceGeometry=await readFile('public/assets/geometry.bin');
let towerMin=Infinity,towerMax=-Infinity;
for(const mesh of cityData.prototypes[tower.prototype].meshes)for(let i=1;i<mesh.positionCount;i+=3){const y=sourceGeometry.readFloatLE(mesh.positionOffset+i*4);towerMin=Math.min(towerMin,y);towerMax=Math.max(towerMax,y);}
const towerPosition=[tower.position[0],tower.position[1]+(towerMin+towerMax)*tower.scale[1]*.5,tower.position[2]];
const entry=await readFile('dist/index.html','utf8'),script=entry.match(/src="([^"]+\.js)"/)[1];
const report={timestamp:new Date().toISOString(),scope:'Isolated desktop hardware WebGPU flight integration smoke test; actual browser keyboard and buttons, no user browser or desktop controlled',viewport:[1600,1000],dpr:1,url:base,build:{entrySHA256:digest(entry),javascriptSHA256:digest(await readFile(path.join('dist',script)))},protectedFiles:originalFiles,checks:{},errors:[],responses:[],screenshots:[],limitations:['Headless keyboard events verify application handling; physical Escape or OS-level keyboard interception is not established.','This smoke test does not assert aerodynamic realism or cover every collision trajectory.']};
let browser,page;
const check=(name,condition,details={})=>{report.checks[name]={status:condition?'passed':'failed',...details};assert.ok(condition,name);};
const snapshot=()=>page.evaluate(()=>window.__cityTest.flight.snapshot());
const state=()=>page.evaluate(()=>window.__cityTest.getState());
const waitFlight=status=>page.waitForFunction(status=>window.__cityTest?.flight?.snapshot()?.status===status,status,{timeout:45000});
const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
const screenshot=async name=>{const file=path.join(evidence,name+'.png');await page.screenshot({path:file});report.screenshots.push(file);};
const protectedScreenshot=async name=>{await page.locator('#intro').evaluate(e=>e.style.setProperty('visibility','hidden','important'));try{await page.locator('#scene').screenshot({path:path.join(evidence,name+'.png')});}finally{await page.locator('#intro').evaluate(e=>e.style.removeProperty('visibility'));}};
const hold=async(key,ms)=>{await page.keyboard.down(key);try{await page.waitForTimeout(ms);}finally{await page.keyboard.up(key);}};

try{
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'C:/Users/limou/AppData/Local/ms-playwright/chromium-1237/chrome-win64/chrome.exe',headless:true,args:['--enable-unsafe-webgpu','--use-angle=d3d11','--disable-background-timer-throttling','--disable-renderer-backgrounding']});
  report.browser=browser.version();page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1});
  page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());if(m.type()==='info')console.log(m.text());});
  page.on('response',r=>report.responses.push({path:new URL(r.url()).pathname,status:r.status()}));
  const response=await page.goto(base+'?debug=1',{waitUntil:'domcontentloaded'});check('localHTTP',response.status()===200,{statusCode:response.status()});
  await page.waitForFunction(()=>window.__cityTest?.ready||!document.getElementById('error').hidden,undefined,{timeout:180000});
  assert.ok(await page.evaluate(()=>!!window.__cityTest?.ready),await page.locator('#error-message').textContent());
  report.initial=await state();report.sourceHash=report.initial.sourceHash;
  check('hardwareWebGPU',report.initial.backend.verifiedBackend&&!report.initial.backend.isFallbackAdapter,{backend:report.initial.backend});
  check('nativeFramebuffer',report.initial.dpr===1&&report.initial.framebuffer[0]===1600&&report.initial.framebuffer[1]===1000,{framebuffer:report.initial.framebuffer});
  check('protectedCityInitially',report.initial.transferAudit.passed&&report.initial.life.vehicles===562&&report.initial.life.pedestrians.count===80&&report.initial.inventory.instances===12488,{inventory:report.initial.inventory,life:report.initial.life});
  await page.evaluate(()=>{window.__cityTest.life.setPaused(true);window.__cityTest.view('aerial');});await page.waitForTimeout(650);
  await protectedScreenshot('protected-aerial-before');
  await page.locator('#nav-fly').click();await waitFlight('flying');await page.waitForTimeout(300);
  const start=await snapshot();check('enterFlightUI',start.active&&!start.paused&&start.position[1]>200&&start.speed>30&&await page.locator('#flight-hud').isVisible(),{snapshot:start});
  const provenance=JSON.parse(await readFile('../aircraft/aircraft_provenance.json','utf8'));
  check('exactSourceAircraft',start.aircraft.meshes===39&&start.aircraft.geometries===39&&start.aircraft.triangles===37119&&provenance.authoredGeometryUnchanged&&provenance.geometryEqualWithinZeroRoundoff,{diagnostics:start.aircraft,provenance:'../aircraft/aircraft_provenance.json',geometrySHA256:provenance.runtimeGeometry.normalizedSha256});
  const north=await page.locator('#compass div').evaluate(e=>e.style.transform);check('eastHeadingCompass',Math.abs(start.yaw-Math.PI/2)<.01&&Math.abs(Number(north.match(/rotate\(([-\d.]+)deg\)/)?.[1])+90)<1,{yaw:start.yaw,transform:north,meaning:'North points left while flying east'});
  await screenshot('01-flight-entry');
  const shadowBefore=(await state()).shadowStats;const throttleBefore=await snapshot();await hold('w',850);const throttleAfter=await snapshot();
  check('actualThrottleKey',throttleAfter.throttle>throttleBefore.throttle+.02,{before:throttleBefore,after:throttleAfter});
  const pitchBefore=await snapshot();await hold('ArrowUp',700);const pitchAfter=await snapshot();
  check('actualPitchKey',Math.abs(pitchAfter.pitch-pitchBefore.pitch)>.01,{before:pitchBefore.pitch,after:pitchAfter.pitch});
  const bankBefore=await snapshot();await hold('ArrowRight',850);const bankAfter=await snapshot();
  check('actualBankKey',Math.abs(bankAfter.bank-bankBefore.bank)>.03,{before:bankBefore.bank,after:bankAfter.bank});
  check('flightMoves',distance(start.position,bankAfter.position)>10,{distanceMetres:distance(start.position,bankAfter.position),before:start.position,after:bankAfter.position});
  const shadowAfter=(await state()).shadowStats;check('movingAircraftShadowUpdates',shadowAfter.dynamicPasses>shadowBefore.dynamicPasses,{before:shadowBefore,after:shadowAfter,cityLifePaused:true});
  await screenshot('02-controlled-flight');
  await page.keyboard.press('Escape');await waitFlight('paused');await page.waitForTimeout(150);const pausedA=await snapshot();await page.waitForTimeout(500);const pausedB=await snapshot();
  check('escapePause',pausedB.paused&&distance(pausedA.position,pausedB.position)<1e-9&&await page.locator('#flight-pause').isVisible(),{before:pausedA,after:pausedB});
  await screenshot('03-flight-paused');
  await page.keyboard.press('Enter');await waitFlight('flying');await page.waitForTimeout(400);const resumed=await snapshot();
  check('enterResume',!resumed.paused&&distance(pausedB.position,resumed.position)>1&&distance(pausedB.position,resumed.position)<40,{snapshot:resumed});
  await page.keyboard.press('r');await page.waitForTimeout(200);const reset=await snapshot();
  check('resetKey',!reset.crashed&&reset.active&&distance(reset.position,[-560,240,250])<30&&Math.abs(reset.bank)<.02&&Math.abs(reset.throttle-.72)<.03,{snapshot:reset});
  await page.keyboard.press('Escape');await waitFlight('paused');await page.locator('#flight-resume').click();await waitFlight('flying');
  check('resumeButton',!(await snapshot()).paused);
  const edgeCases=[
    {side:'east',position:[cityData.bounds.max[0]-1,300,0],yaw:Math.PI/2,axis:0,sign:1,bound:cityData.bounds.max[0]},
    {side:'west',position:[cityData.bounds.min[0]+1,300,0],yaw:-Math.PI/2,axis:0,sign:-1,bound:cityData.bounds.min[0]},
    {side:'south',position:[0,300,cityData.bounds.max[1]-1],yaw:0,axis:2,sign:1,bound:cityData.bounds.max[1]},
    {side:'north',position:[0,300,cityData.bounds.min[1]+1],yaw:Math.PI,axis:2,sign:-1,bound:cityData.bounds.min[1]},
  ];
  const crossings=await page.evaluate(cases=>{const f=window.__cityTest.flight;return cases.map(c=>{f.setPose(c.position,c.yaw,0,0,45);for(let i=0;i<10;i++)f.step(.1);return{...c,snapshot:f.snapshot()};});},edgeCases);
  for(const c of crossings){const s=c.snapshot;check('unrestrictedCityEdge_'+c.side,s.active&&!s.paused&&s.status==='flying'&&(s.position[c.axis]-c.bound)*c.sign>30&&Math.abs(s.yaw-c.yaw)<1e-9&&!/edge|limit|ceiling/i.test(s.warning??''),{snapshot:s,outwardDistance:(s.position[c.axis]-c.bound)*c.sign});}
  const heights=await page.evaluate(()=>{const f=window.__cityTest.flight;return[721,2001].map(height=>{f.setPose([-560,height,250],Math.PI/2,0,0,45);f.step(.1);return{height,snapshot:f.snapshot()};});});
  check('unrestrictedAltitude',heights.every(({height,snapshot:s})=>s.active&&!s.paused&&!s.crashed&&s.status==='flying'&&s.position[1]>height-1&&Math.abs(s.yaw-Math.PI/2)<1e-9&&!/edge|limit|ceiling/i.test(s.warning??'')),{cases:heights});
  const distant=await page.evaluate(()=>{const f=window.__cityTest.flight;f.setPose([10000,2001,10000],Math.PI/2,0,0,45);return f.step(.1);});
  check('distantFlightNoTeleport',distant.active&&!distant.paused&&distant.status==='flying'&&distant.position[0]>10004&&distant.position[2]===10000,{snapshot:distant});
  const lowOutside=await page.evaluate(()=>{const f=window.__cityTest.flight;f.setPose([2000,2,0],Math.PI/2,0,0,45);return f.step(.1);});
  check('lowFlightOutsideCity',lowOutside.active&&!lowOutside.paused&&!lowOutside.crashed&&lowOutside.position[0]>2004,{snapshot:lowOutside});
  const crashed=await page.evaluate(()=>{const f=window.__cityTest.flight;f.setPose([-560,0,250],Math.PI/2,0,0,45);return f.step(.1);});
  check('waterCollisionStopsFlight',crashed.crashed&&crashed.paused&&crashed.status==='crashed'&&crashed.speed===0&&crashed.crashReason==='Water contact',{snapshot:crashed});
  await screenshot('04-water-contact');await page.locator('#flight-reset').click();await waitFlight('flying');const recovered=await snapshot();
  check('crashResetButton',!recovered.crashed&&recovered.active&&recovered.position[1]>200&&distance(recovered.position,[-560,240,250])<30,{snapshot:recovered});
  const towerHit=await page.evaluate(position=>{const f=window.__cityTest.flight;f.setPose(position,Math.PI/2,0,0,45);return f.step(.05);},towerPosition);
  check('cityTowerCollisionPreserved',towerHit.crashed&&towerHit.paused&&towerHit.speed===0&&towerHit.crashReason==='Collision with the city',{tower:tower.id,snapshot:towerHit});
  await page.locator('#flight-reset').click();await waitFlight('flying');
  await page.keyboard.press('Escape');await waitFlight('paused');await page.locator('#flight-exit').click();await page.waitForFunction(()=>window.__cityTest.getState().mode==='aerial');
  const afterExit=await state();check('exitFlightToAerial',!(await snapshot()).active&&afterExit.mode==='aerial'&&await page.locator('#flight-hud').isHidden(),{mode:afterExit.mode,flight:await snapshot()});
  await page.evaluate(()=>window.__cityTest.view('aerial'));await page.waitForTimeout(650);await protectedScreenshot('protected-aerial-after');await screenshot('04-aerial-restored');
  const beforeImage=await readFile(path.join(evidence,'protected-aerial-before.png')),afterImage=await readFile(path.join(evidence,'protected-aerial-after.png'));
  report.protectedAerial={before:'../renders/flight/protected-aerial-before.png',after:'../renders/flight/protected-aerial-after.png',pngByteIdentity:beforeImage.equals(afterImage),note:'The city simulation is paused for this matched camera evidence. Pixel comparison is evaluated separately if PNG encoding differs.'};
  check('protectedAerialPixelIdentity',beforeImage.equals(afterImage),{beforeSHA256:digest(beforeImage),afterSHA256:digest(afterImage),note:'Same camera and paused city, with changing welcome overlay hidden; entire PNGs byte-identical'});
  await page.locator('#nav-fly').click();await waitFlight('flying');await page.locator('#nav-walk').click();await page.waitForFunction(()=>window.__cityTest.getState().mode==='walk');await page.waitForTimeout(250);
  const walkingBefore=await state();check('flightToWalking',!(await snapshot()).active&&walkingBefore.mode==='walk'&&walkingBefore.position[1]<10,{state:walkingBefore});
  if(walkingBefore.paused)await page.locator('#resume').click();await hold('w',650);const walkingAfter=await state();check('walkingControlsRemainFunctional',distance(walkingBefore.position,walkingAfter.position)>.3,{before:walkingBefore.position,after:walkingAfter.position});
  await page.keyboard.press('Escape');await page.locator('#overview').click();await page.waitForFunction(()=>window.__cityTest.getState().mode==='aerial');
  report.final=await state();
  check('protectedCityAfterFlight',report.final.sourceHash===report.initial.sourceHash&&JSON.stringify(report.final.inventory)===JSON.stringify(report.initial.inventory)&&report.final.transferAudit.passed&&report.final.life.vehicles===562&&report.final.life.pedestrians.count===80,{sourceHash:report.final.sourceHash,inventory:report.final.inventory});
  const fileAfter=Object.fromEntries(await Promise.all(protectedFiles.map(async file=>[file,digest(await readFile(file))])));check('protectedFilesUnchanged',JSON.stringify(fileAfter)===JSON.stringify(originalFiles),{hashes:fileAfter});
  check('resourcesLoaded',!report.responses.some(r=>r.status>=400),{responses:report.responses});
  check('noSceneErrors',report.errors.length===0&&report.final.errors.length===0,{errors:report.errors,runtimeErrors:report.final.errors});
  console.log(JSON.stringify({checks:Object.fromEntries(Object.entries(report.checks).map(([k,v])=>[k,v.status])),protectedAerial:report.protectedAerial},null,2));
}catch(error){report.failure=String(error);console.error(error);if(page)await screenshot('failure').catch(()=>{});process.exitCode=1;}
finally{await writeFile('flight_validation.json',JSON.stringify(report,null,2));if(browser)await browser.close();if(report.errors.length||report.failure||Object.values(report.checks).some(c=>c.status==='failed'))process.exitCode=1;}
