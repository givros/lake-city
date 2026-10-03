import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const browser=await chromium.launch({executablePath:'C:/Users/limou/AppData/Local/ms-playwright/chromium-1237/chrome-win64/chrome.exe',headless:true,args:['--enable-unsafe-webgpu','--use-angle=d3d11','--disable-background-timer-throttling','--disable-renderer-backgrounding']});
try{
  const page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1});
  await page.goto('http://127.0.0.1:4173/?debug=1');await page.waitForFunction(()=>window.__cityTest?.ready,undefined,{timeout:150000});
  await page.evaluate(()=>window.__cityTest.life.setPaused(true));await page.addStyleTag({content:'#loading,#pause,#header,#intro,#location,#compass,#walk-hint,#reticle {display:none!important}'});
  const pose=await page.evaluate(()=>{const api=window.__cityTest,s=api.lifeSnapshot();const a=s.actors.filter(a=>a.sourceInstanceId&&a.position[0]>400&&a.position[0]<415&&Math.abs(Math.sin(a.rotation))<.01&&a.speed>2&&Math.abs(a.position[2])<500).sort((a,b)=>Math.abs(a.position[2])-Math.abs(b.position[2]))[0];if(!a)throw Error('No moving source car on target boulevard');const position=[395,.15,a.position[2]+Math.cos(a.rotation)*a.speed*.5],target=[a.position[0],a.position[1]+.7,a.position[2]+Math.cos(a.rotation)*a.speed*.5];return{actor:a,position,yaw:Math.atan2(position[0]-target[0],position[2]-target[2]),pitch:Math.atan2(target[1]-(position[1]+1.72),Math.hypot(position[0]-target[0],position[2]-target[2]))};});
  await page.evaluate(p=>window.__cityTest.singleFrameAt(p.position,p.yaw,p.pitch),pose);await page.screenshot({path:'../renders/vehicle-promotion/promoted-car-a.png'});
  const before=await page.evaluate(()=>window.__cityTest.getState());await page.evaluate(()=>window.__cityTest.life.step(1));
  await page.evaluate(p=>window.__cityTest.singleFrameAt(p.position,p.yaw,p.pitch),pose);await page.screenshot({path:'../renders/vehicle-promotion/promoted-car-b.png'});
  const after=await page.evaluate(id=>window.__cityTest.lifeSnapshot().actors.find(a=>a.id===id),pose.actor.id);
  const result={sourceInstanceId:pose.actor.sourceInstanceId,prototype:pose.actor.prototype,camera:before.camera,rotation:before.rotation,elapsedSeconds:1,before:pose.actor,after,distance:after.distanceTravelled-pose.actor.distanceTravelled,images:['../renders/vehicle-promotion/promoted-car-a.png','../renders/vehicle-promotion/promoted-car-b.png']};
  const report=JSON.parse(await fs.readFile('vehicle_promotion_validation.json','utf8'));report.targetedTrafficCapture=result;await fs.writeFile('vehicle_promotion_validation.json',JSON.stringify(report,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
