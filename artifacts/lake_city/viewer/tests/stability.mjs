import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
const tag=process.argv[2]||'baseline';
const root=path.resolve('../renders/stability/'+tag);await fs.mkdir(root,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'C:/Users/limou/AppData/Local/ms-playwright/chromium-1237/chrome-win64/chrome.exe',headless:true,args:['--enable-unsafe-webgpu','--use-angle=d3d11','--disable-background-timer-throttling','--disable-renderer-backgrounding']});
const page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1});const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
await page.goto('http://127.0.0.1:4173/?debug=1');await page.waitForFunction(()=>window.__cityTest?.ready,undefined,{timeout:120000});await page.addStyleTag({content:'#loading,#pause,#header,#intro,#location,#compass,#walk-hint,#reticle { display:none!important; }'});
await page.evaluate(()=>{window.__cityTest.life?.setPaused(true);window.__audit=window.__cityTest.auditBatches();});
const scenarios=[{id:'downtown',start:[427.5,.15,43.5],delta:[1.25,0,0],yaw:-.5,pitch:.06},{id:'lake',start:[-324.902,.15,217.816],delta:[.3,0,-1.25],yaw:-.3,pitch:0},{id:'park',start:[255,.15,24],delta:[0,0,-1.25],yaw:-.1,pitch:.02},{id:'residential',start:[-180,.15,-271.5],delta:[1.25,0,0],yaw:-Math.PI/2,pitch:0}];const result={tag,source:(await page.evaluate(()=>window.__cityTest.getState())).sourceHash,frames:[],errors};
for(const scenario of scenarios){for(let i=0;i<12;i++){
const position=scenario.start.map((v,n)=>v+scenario.delta[n]*i);await page.evaluate(({position,yaw,pitch})=>window.__cityTest.singleFrameAt(position,yaw,pitch),{position,yaw:scenario.yaw,pitch:scenario.pitch});
const name=`${scenario.id}-${String(i).padStart(2,'0')}`;await page.screenshot({path:path.join(root,name+'.png')});result.frames.push({name,state:await page.evaluate(()=>window.__cityTest.getState())});
await page.evaluate(({position,yaw,pitch})=>window.__cityTest.singleFrameAt(position,yaw,pitch),{position,yaw:scenario.yaw,pitch:scenario.pitch});await page.screenshot({path:path.join(root,name+'-repeat.png')});
if(i%3===0){await page.evaluate(()=>window.__cityTest.setBatchCulling(false));await page.evaluate(({position,yaw,pitch})=>window.__cityTest.singleFrameAt(position,yaw,pitch),{position,yaw:scenario.yaw,pitch:scenario.pitch});await page.screenshot({path:path.join(root,name+'-all-source.png')});await page.evaluate(()=>window.__cityTest.setBatchCulling(true));}
console.log(tag,name);
}}
result.audit=await page.evaluate(()=>window.__audit);await fs.writeFile(path.join(root,'capture.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result.audit));await browser.close();console.log('complete',tag);if(!tag.startsWith('baseline')&&(errors.length||result.audit.cameraMismatches.length||result.audit.textureMismatches.length))process.exitCode=1;



