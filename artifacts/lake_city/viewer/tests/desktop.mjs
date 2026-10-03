import {chromium} from 'playwright';
import {readFile,writeFile,mkdir,access,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import os from 'node:os';
const base=process.env.CITY_URL||'http://127.0.0.1:4173';
const evidence=path.resolve('../renders/runtime');await mkdir(evidence,{recursive:true});
let executable=process.env.CHROMIUM_PATH||chromium.executablePath();
try{await access(executable);}catch{
  const cache=process.env.PLAYWRIGHT_BROWSERS_PATH||(process.platform==='win32'?path.join(process.env.LOCALAPPDATA||path.join(os.homedir(),'AppData','Local'),'ms-playwright'):path.join(os.homedir(),'.cache','ms-playwright'));
  const versions=(await readdir(cache)).filter(n=>/^chromium-\d+$/.test(n)).sort((a,b)=>Number(b.split('-')[1])-Number(a.split('-')[1]));
  for(const version of versions){const candidate=path.join(cache,version,process.platform==='win32'?'chrome-win64/chrome.exe':'chrome-linux/chrome');try{await access(candidate);executable=candidate;break;}catch{}}
}
const browser=await chromium.launch({executablePath:executable,headless:true,args:['--enable-unsafe-webgpu','--use-angle=d3d11','--disable-background-timer-throttling','--disable-renderer-backgrounding']});
const context=await browser.newContext({viewport:{width:1600,height:1000},deviceScaleFactor:1});
const page=await context.newPage();
const consoleMessages=[],network=[];
page.on('console',m=>{if(m.type()==='info')console.log(m.text());if(m.type()==='error'||m.type()==='warning'){consoleMessages.push({type:m.type(),text:m.text()});console.log(m.type(),m.text());}});page.on('pageerror',e=>consoleMessages.push({type:'pageerror',text:e.message}));
page.on('response',async r=>{if(/assets\/(city.json|geometry.bin|traffic_network.json|characters\/pedestrian\.(glb|json))/.test(r.url()))network.push({url:r.url(),status:r.status(),headers:await r.allHeaders()});});
const report={timestamp:new Date().toISOString(),scope:'Isolated headless desktop Chromium; no user browser controlled',browser:browser.version(),viewport:[1600,1000],dpr:1,quality:'Final render_profile.json; native resolution, full source geometry and full-resolution planar reflections',sampling:{warmupFrames:4,measuredFramesPerView:90,sourceStatic:false,cityLife:"562 vehicles and80 pedestrians active during performance samples",otherGPUWork:'Parent confirmed Blender GPU rendering complete before this run',cache:'Cold isolated context startup, then same-context warm reload; static scene shadows cached per region, moving actor depth union updated each simulation revision',gpuTiming:'Unavailable; CPU callback and animation-frame interval measured separately'},evidenceDirectory:evidence,checks:{},consoleMessages,network};
const check=(name,status,details)=>report.checks[name]={status,...details};
const stat=(array)=>{const s=[...array].sort((a,b)=>a-b);return {p50:s[Math.floor(s.length*.5)]??null,p95:s[Math.floor(s.length*.95)]??null,mean:s.reduce((a,b)=>a+b,0)/Math.max(s.length,1)};};
const entry=await readFile('dist/index.html','utf8'),script=entry.match(/src="([^"]+\.js)"/)[1];
report.build={entrySHA256:createHash('sha256').update(entry).digest('hex'),javascriptSHA256:createHash('sha256').update(await readFile(path.join('dist',script))).digest('hex'),renderProfileSHA256:createHash('sha256').update(await readFile('render_profile.json')).digest('hex')};
try{
  await page.goto(base+'?debug=1',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__cityTest?.ready||!document.getElementById('error').hidden,undefined,{timeout:240000});
  const ready=await page.evaluate(()=>Boolean(window.__cityTest?.ready));
  if(!ready)throw new Error(await page.locator('#error-message').textContent());
  await page.waitForTimeout(800);
  console.log('First city frame ready');const state=await page.evaluate(()=>window.__cityTest.getState());report.initialState=state;report.backend=state.backend;
  check('cityLifeResources',state.life.vehicles===562&&state.life.promotedSourceVehicles===478&&state.life.additionalVehicles===84&&state.life.pedestrians.count===80&&state.life.pedestrians.bonesPerActor===49?'passed':'failed',{life:state.life});
  check('startup','passed',{timings:state.timings});check('backend',state.backend.verifiedBackend?'passed':'failed',{actual:state.backend});
  check('nativeResolution',state.dpr===1&&state.framebuffer[0]===1600&&state.framebuffer[1]===1000?'passed':'failed',{framebuffer:state.framebuffer});
  await page.screenshot({path:path.join(evidence,'01-aerial.png')});
  const lifeReport=JSON.parse(await readFile('life_validation.json','utf8'));
  check('cityLifeValidation',lifeReport.sourceHash===state.sourceHash&&!lifeReport.failure&&!lifeReport.errors.length&&Object.values(lifeReport.checks).every(c=>!c.status||c.status==='passed')?'passed':'failed',{report:'life_validation.json',shadowUnion:lifeReport.shadowReference});
  const manifest=await readFile('dist/assets/city.json'),geometry=await readFile('dist/assets/geometry.bin');
  report.source={sourceHash:state.sourceHash,manifestSHA256:createHash('sha256').update(manifest).digest('hex'),geometrySHA256:createHash('sha256').update(geometry).digest('hex'),manifestBytes:manifest.length,geometryBytes:geometry.length};
  const data=JSON.parse(manifest);let triangles=0;for(const i of data.instances)for(const m of data.prototypes[i.prototype].meshes)triangles+=m.indexCount/3;
  check('exactTransfer',state.transferAudit.passed&&state.inventory.instancedTriangles===triangles&&state.inventory.instances===data.instances.length?'passed':'failed',{sourceTriangles:triangles,runtimeInventory:state.inventory,transferAudit:state.transferAudit});
  const waterPlanes=new Set();for(const i of data.instances)for(const m of data.prototypes[i.prototype].meshes)if(/water/.test(m.material))waterPlanes.add(i.position[1]+geometry.readFloatLE(m.positionOffset+4)*i.scale[1]);
  check('exactReflectionPlanes',[...waterPlanes].every(h=>state.reflectorPlanes.includes(h))?'passed':'failed',{source:[...waterPlanes],runtime:state.reflectorPlanes});
  check('uncompressedTransport',network.every(r=>!r.headers['content-encoding'])?'passed':'failed',{responses:network});
  await page.evaluate(()=>window.__cityTest.view('plan'));await page.waitForTimeout(1000);await page.screenshot({path:path.join(evidence,'02-plan.png')});
  const planFrames=await page.evaluate(()=>window.__cityTest.sampleFrames(90));
  report.performance={plan:{camera:'North-up orthographic plan, current manifest bounds plus7% margin',samples:planFrames.length,durationMs:planFrames.reduce((s,f)=>s+f.interval,0),frameIntervalMs:stat(planFrames.map(f=>f.interval)),cpuCallbackMs:stat(planFrames.map(f=>f.cpu)),drawCalls:planFrames.at(-1)?.calls,scenePasses:planFrames.at(-1)?.scenePasses,trianglesAcrossPasses:planFrames.at(-1)?.triangles,gpuMilliseconds:null,cpuPhases:Object.fromEntries(["simulationMs","shadowMs","reflectionMs","beautyMs"].map(k=>[k,stat(planFrames.map(f=>f[k]))]))}};
  for(const [i,landmark] of data.landmarks.entries()){
    await page.evaluate(id=>window.__cityTest.view(id),landmark.id);await page.waitForTimeout(700);
    await page.screenshot({path:path.join(evidence,`${String(i+3).padStart(2,'0')}-${landmark.id.replace(/[^a-z0-9_-]/gi,'_')}.png`)});
  }
  for(const id of ['lake_approach','residential','park_lawn','downtown_street']){await page.evaluate(id=>window.__cityTest.captureCamera(id),id);await page.waitForTimeout(600);await page.screenshot({path:path.join(evidence,`source-${id}.png`)});}
  await page.evaluate(()=>window.__cityTest.view('aerial'));await page.waitForTimeout(400);await page.click('#nav-walk');await page.waitForTimeout(600);
  const before=await page.evaluate(()=>window.__cityTest.getState());
  await page.keyboard.down('w');await page.waitForTimeout(1000);await page.keyboard.up('w');
  const after=await page.evaluate(()=>window.__cityTest.getState());
  check('actualKeyboardMovement',Math.hypot(after.position[0]-before.position[0],after.position[2]-before.position[2])>.3?'passed':'failed',{before:before.position,after:after.position,pointerLock:after.pointerLocked});
  await page.screenshot({path:path.join(evidence,'walking-promenade.png')});await page.mouse.move(850,50);await page.waitForTimeout(150);
  const looked=await page.evaluate(()=>window.__cityTest.getState());check('actualMouseLook',looked.rotation.some((r,i)=>Math.abs(r-after.rotation[i])>.0001)?'passed':'failed',{before:after.rotation,after:looked.rotation});
  const walkingFrames=await page.evaluate(()=>window.__cityTest.sampleFrames(90));report.performance.walking={position:looked.position,rotation:looked.rotation,samples:walkingFrames.length,durationMs:walkingFrames.reduce((s,f)=>s+f.interval,0),frameIntervalMs:stat(walkingFrames.map(f=>f.interval)),cpuCallbackMs:stat(walkingFrames.map(f=>f.cpu)),drawCalls:walkingFrames.at(-1)?.calls,scenePasses:walkingFrames.at(-1)?.scenePasses,trianglesAcrossPasses:walkingFrames.at(-1)?.triangles,gpuMilliseconds:null,cpuPhases:Object.fromEntries(["simulationMs","shadowMs","reflectionMs","beautyMs"].map(k=>[k,stat(walkingFrames.map(f=>f[k]))]))};
  await page.keyboard.press('Escape');await page.waitForTimeout(250);const pause=await page.evaluate(()=>window.__cityTest.getState());check('pause',pause.paused&&!pause.pointerLocked?'passed':'failed',{state:pause});
  await page.click('#fullscreen');await page.waitForTimeout(300);const full=await page.evaluate(()=>!!document.fullscreenElement);await page.click('#resume');await page.keyboard.press('Escape');await page.waitForTimeout(200);
  const fullscreenPause=await page.evaluate(()=>window.__cityTest.getState());
  check('fullscreenAPIs',full&&fullscreenPause.paused?'passed':'failed',{entered:full,retainedOnEscape:fullscreenPause.fullscreen,nativeEscapeInterception:'Not established by headless testing; Keyboard Lock depends on user browser support'});
  if(await page.evaluate(()=>!!document.fullscreenElement))await page.click('#fullscreen');
  await page.click('#resume');await page.evaluate(()=>window.dispatchEvent(new Event('blur')));await page.waitForTimeout(100);const blur=await page.evaluate(()=>window.__cityTest.getState());check('focusLoss',blur.paused&&blur.keys.length===0?'passed':'failed',{scope:'Synthetic application event'});
  const routeResults=[];
  for(const route of data.paths.filter(p=>p.closed||/park|promenade|lake|boulevard/i.test(p.id))){
    const result=await page.evaluate(route=>{const failures=[];let count=0;for(let i=1;i<route.points.length+(route.closed?1:0);i++){const a=route.points[i-1],b=route.points[i%route.points.length],n=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/3));for(let j=0;j<=n;j++){const x=a[0]+(b[0]-a[0])*j/n,z=a[1]+(b[1]-a[1])*j/n,q=window.__cityTest.collision(x,z);count++;if(q.blocked&&failures.length<30)failures.push({x,z,blocked:q.blocked});}}return {id:route.id,samples:count,failures};},route);
    routeResults.push(result);
  }
  check('routeClearance',routeResults.every(r=>!r.failures.length)?'passed':'failed',{routes:routeResults});
  const loop=data.paths.find(p=>p.id==='PATH_LAKE_COMPLETE_LOOP');
  if(loop){
    const traversal=await page.evaluate(route=>{
      window.__cityTest.walk([route.points[0][0],.15,route.points[0][1]]);
      let maxDeviation=0,distance=0;
      for(let i=1;i<=route.points.length;i++){
        const state=window.__cityTest.getState(),point=route.points[i%route.points.length];
        const dx=point[0]-state.position[0],dz=point[1]-state.position[2];distance+=Math.hypot(dx,dz);
        const actual=window.__cityTest.moveBy(dx,dz);maxDeviation=Math.max(maxDeviation,Math.hypot(point[0]-actual[0],point[1]-actual[2]));
      }
      return {segments:route.points.length,distanceMetres:distance,maxDeviationMetres:maxDeviation,finalState:window.__cityTest.getState()};
    },loop);
    check('completeLakeLoopTraversal',traversal.maxDeviationMetres<.2?'passed':'failed',traversal);
  }
  const supportChecks=[];for(const surface of data.walkSurfaces??[]){const [x,z,X,Z]=surface.bounds;const q=await page.evaluate(p=>window.__cityTest.collision(p[0],p[1]),[(x+X)/2,(z+Z)/2]);supportChecks.push({surface,result:q});}
  check('bridgeAndDockSupport',supportChecks.every(s=>s.result.support!==null)?'passed':'failed',{surfaces:supportChecks});
  const water=data.waterPolygons[0];if(water?.length){const point=[water.reduce((s,p)=>s+p[0],0)/water.length,water.reduce((s,p)=>s+p[1],0)/water.length];const q=await page.evaluate(p=>window.__cityTest.collision(...p),point);check('waterBarrier',q.water&&q.blocked==='water'?'passed':'failed',{point,result:q});}
  const building=data.instances.find(i=>data.prototypes[i.prototype].collision?.[0]>5);if(building){const q=await page.evaluate(p=>window.__cityTest.collision(p[0],p[2]),building.position);check('solidBuildingBarrier',!!q.blocked?'passed':'failed',{instance:building.id,result:q});}
  const spawnResults=[];for(const l of data.landmarks){await page.evaluate(p=>window.__cityTest.walk(p),l.walkPosition??[l.lookAt[0],.15,l.lookAt[2]]);const s=await page.evaluate(()=>window.__cityTest.getState());spawnResults.push({landmark:l.id,position:s.position,eyeHeight:s.eyeHeight,valid:Math.abs(s.eyeHeight-1.72)<1e-6});}
  check('landmarkSpawns',spawnResults.every(s=>s.valid)?'passed':'failed',{spawns:spawnResults});
  await page.evaluate(()=>window.__cityTest.view('aerial'));await page.waitForTimeout(600);const finalState=await page.evaluate(()=>window.__cityTest.getState());
  check('shaderAndRuntimeErrors',finalState.errors.length||consoleMessages.some(m=>m.type==='pageerror'||m.type==='error')?'failed':'passed',{errors:consoleMessages});
  await page.evaluate(()=>window.__cityTest.dispose());const dead=await page.evaluate(()=>window.__cityTest.getState().disposed);check('dispose',dead?'passed':'failed',{scope:'Explicit listener, animation mixer, actor skeleton/material, renderer, geometry, reflector and device cleanup'});
  await page.reload({waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.__cityTest?.ready,undefined,{timeout:240000});const reload=await page.evaluate(()=>window.__cityTest.getState());check('reload','passed',{timings:reload.timings});
  check('nativeDesktopEscape','blocked',{reason:'No authorization to control the user desktop; physical long-hold Escape and embedded browser behavior are untested.'});
  check('gpuTimestamps','not_applicable',{reason:'GPU timestamp instrumentation was not enabled. CPU callback and full rendered frame interval are measured separately.'});
  const noGpu=await context.newPage();await noGpu.addInitScript(()=>Object.defineProperty(navigator,'gpu',{value:undefined,configurable:true}));await noGpu.goto(base,{waitUntil:'domcontentloaded'});await noGpu.waitForSelector('#error:not([hidden])');check('missingWebGPUFailure','passed',{scope:'Mocked navigator.gpu absence',message:await noGpu.locator('#error-message').textContent()});await noGpu.close();
  const missingAsset=await context.newPage();await missingAsset.route('**/assets/geometry.bin',r=>r.fulfill({status:404,body:'Not found'}));await missingAsset.goto(base,{waitUntil:'domcontentloaded'});await missingAsset.waitForSelector('#error:not([hidden])');check('missingAssetFailure','passed',{scope:'Mocked missing geometry response',message:await missingAsset.locator('#error-message').textContent()});await missingAsset.close();
}catch(error){report.failure=String(error);check('completion','failed',{reason:String(error)});await page.screenshot({path:path.join(evidence,'failure.png')}).catch(()=>{});}
finally{await writeFile('runtime_validation.json',JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify({checks:Object.fromEntries(Object.entries(report.checks).map(([k,v])=>[k,v.status])),failure:report.failure,performance:report.performance},null,2));if(Object.values(report.checks).some(c=>c.status==='failed'))process.exitCode=1;}
