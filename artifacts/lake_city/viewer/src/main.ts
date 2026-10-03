import './style.css';

import * as THREE from 'three/webgpu';

import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

import {createRenderer,type RendererBundle} from './renderer';

import {loadCity,type LoadedCity} from './scene';

import {CityCollision,BODY} from './collision';

import {CityLife} from './life';

import {CityFlight} from './flight/CityFlight';

import type {Vec3,Landmark} from './types';



const $=<T extends HTMLElement>(id:string)=>document.getElementById(id) as T;

const canvas=$<HTMLCanvasElement>('scene');

const startup=performance.now();

const timings:Record<string,number>={};

const errors:string[]=[];

let failed=false,disposed=false,bundle:RendererBundle|undefined,city:LoadedCity|undefined;

let life:CityLife|undefined;

let flight:CityFlight|undefined;
let lastFlightStatus='';

let fullscreenSession=0;

let dirty=true,forceFrames=0,mode:'aerial'|'plan'|'walk'|'flight'='aerial',paused=true;

let activeCamera:THREE.PerspectiveCamera|THREE.OrthographicCamera;

let passTimes={shadowMs:0,reflectionMs:0,beautyMs:0};
let frames:{interval:number;cpu:number;calls:number;scenePasses:number;triangles:number;simulationMs:number;shadowMs:number;reflectionMs:number;beautyMs:number}[]=[];

let controls:OrbitControls,collision:CityCollision;

const perspective=new THREE.PerspectiveCamera(48,innerWidth/innerHeight,.1,12000);

const planCamera=new THREE.OrthographicCamera(-1300,1300,900,-900,.1,6000);

const keys=new Set<string>();

const forward=new THREE.Vector3(),right=new THREE.Vector3(),up=new THREE.Vector3(0,1,0);

const euler=new THREE.Euler(0,0,0,'YXZ');

let footHeight=BODY.ground,velocityY=0;

let currentLandmark:Landmark|undefined;

let walkingPosition:Vec3|undefined;

let lastTime=performance.now(),lastRender=performance.now(),lastLocation=0;

let tween:{start:number;from:THREE.Vector3;to:THREE.Vector3;fromTarget:THREE.Vector3;toTarget:THREE.Vector3}|null=null;

const listeners:{target:EventTarget;type:string;handler:EventListener}[]=[];

function on(target:EventTarget,type:string,handler:(e:any)=>void){target.addEventListener(type,handler);listeners.push({target,type,handler});}

function fatal(message:string){if(failed||disposed)return;failed=true;errors.push(message);$('loading').hidden=true;$('error').hidden=false;$('error-message').textContent=message;bundle?.renderer.setAnimationLoop(null);console.error(message);}

function progress(message:string){$('loading-message').textContent=message;if(new URLSearchParams(location.search).has('debug'))console.info('City loading:',message,Math.round(performance.now()-startup));}

on($('reload'),'click',()=>location.reload());

function setActiveUi(){

  document.body.classList.toggle('walking',mode==='walk');document.body.classList.toggle('plan',mode==='plan');

  document.body.classList.toggle('flying',mode==='flight');

  $('aerial').classList.toggle('active',mode==='aerial');$('plan').classList.toggle('active',mode==='plan');

  $('nav-fly').classList.toggle('active',mode==='flight');
  $('flight-hud').hidden=mode!=='flight';$('flight-hint').hidden=mode!=='flight';
  if(mode!=='flight')$('flight-pause').hidden=true;else updateFlightUi();

  $('pause').hidden=mode!=='walk'||!paused;$('reticle').hidden=mode!=='walk'||paused;$('walk-hint').hidden=mode!=='walk'||paused;

  $('destinations').hidden=true;$('destinations-button').setAttribute('aria-expanded','false');

}

function overview(plan=false,instant=false){

  flight?.exit();

  perspective.fov=48;perspective.updateProjectionMatrix();

  if(document.pointerLockElement)document.exitPointerLock();keys.clear();paused=true;mode=plan?'plan':'aerial';controls.enabled=true;controls.enableRotate=!plan;

  currentLandmark=undefined;

  controls.screenSpacePanning=plan;

  controls.minDistance=40;controls.maxDistance=4700;controls.maxPolarAngle=Math.PI*.495;

  activeCamera=plan?planCamera:perspective;controls.object=activeCamera;

  const cameraList=city?(Array.isArray(city.data.cameras)?city.data.cameras:Object.values(city.data.cameras)):[];

  const camera=cameraList.find(c=>/aerial|overview/i.test(c.id));

  const position=plan?new THREE.Vector3(0,3000,.001):new THREE.Vector3(...(camera?.position??[-330,1850,2100]));

  const target=new THREE.Vector3(...(camera?.target??camera?.lookAt??[0,0,0]));

  if(plan){target.set(0,0,0);planCamera.up.set(0,0,-1);planCamera.zoom=1;resize();}

  if(instant||plan){activeCamera.position.copy(position);controls.target.copy(target);activeCamera.lookAt(target);tween=null;}

  else tween={start:performance.now(),from:perspective.position.clone(),to:position,fromTarget:controls.target.clone(),toTarget:target};

  controls.update();setActiveUi();dirty=true;$('location-name').textContent='Lake City';

}

function visit(landmark:Landmark,instant=false){

  if(mode==='walk'||mode==='flight')overview(false,true);

  mode='aerial';activeCamera=perspective;controls.object=perspective;controls.enabled=true;controls.enableRotate=true;

  controls.screenSpacePanning=false;controls.minDistance=40;controls.maxDistance=4700;controls.maxPolarAngle=Math.PI*.495;

  currentLandmark=landmark;

  const to=new THREE.Vector3(...landmark.position),target=new THREE.Vector3(...landmark.lookAt);

  const regionalPoints=landmark.id==='lake'?city!.data.waterPolygons[0]:landmark.id==='park'?city!.data.paths.filter(p=>/^PATH_PARK_/.test(p.id)).flatMap(p=>p.points):null;

  if(regionalPoints?.length){

    const minX=Math.min(...regionalPoints.map(p=>p[0])),maxX=Math.max(...regionalPoints.map(p=>p[0])),minZ=Math.min(...regionalPoints.map(p=>p[1])),maxZ=Math.max(...regionalPoints.map(p=>p[1]));

    const extent=Math.max(maxX-minX,maxZ-minZ);

    target.set((minX+maxX)/2,0,(minZ+maxZ)/2);

    to.set(target.x+extent*(landmark.id==='lake'?-.14:.15),extent*(landmark.id==='lake'?.84:.9),target.z+extent*(landmark.id==='lake'?.58:.9));

  }

  if(instant){perspective.position.copy(to);controls.target.copy(target);perspective.lookAt(target);tween=null;}

  else tween={start:performance.now(),from:perspective.position.clone(),to,fromTarget:controls.target.clone(),toTarget:target};

  $('location-name').textContent=landmark.name;document.body.classList.add('compact');setActiveUi();dirty=true;

}

function defaultSpawn():Vec3 {

  const shore=city!.data.landmarks.find(l=>/lake|promenade|waterfront/i.test(l.id+' '+l.name));

  if(shore?.walkPosition)return shore.walkPosition;

  if(shore)return [shore.lookAt[0],BODY.ground,shore.lookAt[2]];

  return [-325,BODY.ground,210];

}

function setWalkPose(spawn?:Vec3){

  perspective.fov=48;perspective.updateProjectionMatrix();

  const point=spawn??currentLandmark?.walkPosition??walkingPosition??defaultSpawn();

  const safe=collision.safePoint(point[0],point[2]);footHeight=safe[1];velocityY=0;

  perspective.position.set(safe[0],footHeight+BODY.eye,safe[2]);

  const destination=currentLandmark??city!.data.landmarks.find(l=>/lake|promenade|waterfront/i.test(l.id+' '+l.name));

  if(destination?.id==='lake'){

    const route=city!.data.paths.find(p=>p.id==='PATH_LAKE_COMPLETE_LOOP');

    if(route?.points.length){

      let nearest=0;

      for(let i=1;i<route.points.length;i++)if(Math.hypot(route.points[i][0]-safe[0],route.points[i][1]-safe[2])<Math.hypot(route.points[nearest][0]-safe[0],route.points[nearest][1]-safe[2]))nearest=i;

      const behind=route.points[(nearest+route.points.length-2)%route.points.length],ahead=route.points[(nearest+2)%route.points.length];

      const direction=new THREE.Vector3(ahead[0]-behind[0],0,ahead[1]-behind[1]).normalize();

      direction.add(new THREE.Vector3(destination.lookAt[0]-safe[0],0,destination.lookAt[2]-safe[2]).normalize().multiplyScalar(.12)).normalize();

      perspective.lookAt(safe[0]+direction.x*60,footHeight+BODY.eye-2,safe[2]+direction.z*60);

    }else perspective.lookAt(destination.lookAt[0],footHeight+BODY.eye,destination.lookAt[2]);

  }

  else if(destination)perspective.lookAt(destination.lookAt[0],footHeight+BODY.eye,destination.lookAt[2]);

  else perspective.rotation.set(0,-Math.PI*.7,0,'YXZ');

  perspective.updateMatrixWorld();walkingPosition=[safe[0],safe[1],safe[2]];

}

function enterWalk(requestLock=true,spawn?:Vec3){

  flight?.exit();

  tween=null;if(mode!=='walk'||spawn)setWalkPose(spawn);

  mode='walk';activeCamera=perspective;controls.enabled=false;paused=true;setActiveUi();dirty=true;

  if(requestLock)canvas.requestPointerLock().catch(()=>{$('pause').hidden=false;});

}

function pauseWalking(){if(mode!=='walk')return;keys.clear();paused=true;if(document.pointerLockElement)document.exitPointerLock();setActiveUi();dirty=true;}

function enterFlight(){
  if(!flight)return;
  if(document.pointerLockElement)document.exitPointerLock();
  keys.clear();tween=null;currentLandmark=undefined;mode='flight';activeCamera=perspective;
  controls.enabled=false;paused=false;lastFlightStatus='';
  flight.start();document.body.classList.add('compact');setActiveUi();dirty=true;
}

function pauseFlight(){
  if(mode!=='flight'||!flight)return;
  flight.setPaused(true);paused=true;updateFlightUi();dirty=true;
}

function resumeFlight(){
  if(mode!=='flight'||!flight)return;
  flight.setPaused(false);paused=flight.paused;lastTime=performance.now();updateFlightUi();dirty=true;
}

function resetFlight(){
  if(mode!=='flight'||!flight)return;
  flight.reset();paused=flight.paused;lastTime=performance.now();updateFlightUi();dirty=true;
}

function pauseExploration(){pauseWalking();pauseFlight();}

function updateFlightUi(){
  if(mode!=='flight'||!flight)return;
  const state=flight.snapshot();paused=flight.paused;
  $('flight-speed').textContent=String(Math.round(state.speedKmh));
  $('flight-altitude').textContent=String(Math.round(state.altitude));
  $('flight-throttle').textContent=String(Math.round(state.throttle*100));
  $('flight-status').textContent=state.grounded?'On the ground':'CROPPER SEVEN';
  $('flight-warning').textContent=state.warning??'';
  $('flight-warning').hidden=!state.warning;
  const stopped=state.status==='paused'||state.status==='crashed';
  $('flight-pause').hidden=!stopped;
  $('flight-resume').hidden=state.status!=='paused';
  $('flight-pause-title').textContent=state.crashed?'Flight interrupted':'Flight paused';
  $('flight-pause-message').textContent=state.crashed?(state.crashReason??'The aircraft has made contact. Start a new flight above the lake.'):'Your aircraft is holding its position. Continue whenever you are ready.';
  if(state.status!==lastFlightStatus){lastFlightStatus=state.status;dirty=true;}
  $('location-name').textContent='Lake City · Flight';
}

function resize(){

  if(!bundle)return;bundle.renderer.setPixelRatio(window.devicePixelRatio);bundle.renderer.setSize(innerWidth,innerHeight);

  perspective.aspect=innerWidth/innerHeight;perspective.updateProjectionMatrix();

  const bounds=city?.data.bounds??{min:[-1087.5,-816],max:[1087.5,816]},worldWidth=bounds.max[0]-bounds.min[0],worldHeight=bounds.max[1]-bounds.min[1];

  const halfHeight=Math.max(worldHeight*.535,worldWidth*.535/(innerWidth/innerHeight));

  planCamera.left=-halfHeight*innerWidth/innerHeight;planCamera.right=-planCamera.left;planCamera.top=halfHeight;planCamera.bottom=-halfHeight;planCamera.updateProjectionMatrix();

  dirty=true;

}

function updateWalking(dt:number){

  if(paused)return;

  let f=Number(keys.has('w')||keys.has('z')||keys.has('arrowup'))-Number(keys.has('s')||keys.has('arrowdown'));

  let r=Number(keys.has('d')||keys.has('arrowright'))-Number(keys.has('a')||keys.has('q')||keys.has('arrowleft'));

  if(f||r){

    const length=Math.hypot(f,r);f/=length;r/=length;

    perspective.getWorldDirection(forward);forward.y=0;forward.normalize();right.crossVectors(forward,up).normalize();

    const speed=keys.has('shift')?BODY.fastSpeed:BODY.speed;

    const [x,support,z]=collision.move(perspective.position.x,perspective.position.z,(forward.x*f+right.x*r)*speed*dt,(forward.z*f+right.z*r)*speed*dt,footHeight);

    perspective.position.x=x;perspective.position.z=z;

    if(support>=footHeight) {footHeight=support;velocityY=0;}else {velocityY-=9.81*dt;footHeight=Math.max(support,footHeight+velocityY*dt);}

    perspective.position.y=footHeight+BODY.eye;walkingPosition=[x,footHeight,z];dirty=true;

  }

}

function tick(now:number){

  if(failed||disposed||!bundle)return;

  const start=performance.now(),elapsed=Math.max(0,(now-lastTime)/1000),dt=Math.min(elapsed,.05);lastTime=now;

  const lifeStart=performance.now();if(life?.update(elapsed))dirty=true;const simulationMs=performance.now()-lifeStart;

  if(tween){const u=Math.min((now-tween.start)/1200,1),s=u*u*(3-2*u);perspective.position.lerpVectors(tween.from,tween.to,s);controls.target.lerpVectors(tween.fromTarget,tween.toTarget,s);dirty=true;if(u>=1)tween=null;}

  if(mode==='walk')updateWalking(dt);
  else if(mode==='flight'){if(flight?.update(Math.min(elapsed,.12)))dirty=true;updateFlightUi();}
  else if(controls.update())dirty=true;

  if(window.devicePixelRatio!==bundle.renderer.getPixelRatio())resize();

  if(mode==='walk'&&now-lastLocation>1000){lastLocation=now;const nearest=[...city!.data.landmarks].sort((a,b)=>Math.hypot(a.lookAt[0]-perspective.position.x,a.lookAt[2]-perspective.position.z)-Math.hypot(b.lookAt[0]-perspective.position.x,b.lookAt[2]-perspective.position.z))[0];if(nearest)$('location-name').textContent=nearest.name;}

  if(!dirty&&forceFrames<=0)return;

  try{

    bundle.fitSun(activeCamera.position,mode==='walk');

    bundle.renderer.info.reset();renderCityFrame();

    const info=bundle.renderer.info.render;

    frames.push({simulationMs,...passTimes,interval:now-lastRender,cpu:performance.now()-start,calls:info.drawCalls,scenePasses:info.frameCalls,triangles:info.triangles});if(frames.length>1600)frames.shift();

    lastRender=now;forceFrames=Math.max(forceFrames-1,0);dirty=false;

    const north=$('compass').querySelector('div')!;north.style.transform=`rotate(${mode==='plan'?0:mode==='flight'?flight!.snapshot().yaw*180/Math.PI-180:-controls.getAzimuthalAngle()*180/Math.PI}deg)`;

  }catch(error){fatal(error instanceof Error?error.message:String(error));}

}

function renderCityFrame(){

  activeCamera.coordinateSystem=bundle!.renderer.coordinateSystem;

  activeCamera.updateProjectionMatrix();activeCamera.updateMatrixWorld();bundle!.scene.updateMatrixWorld();

  const shadowStart=performance.now();bundle!.renderSun(activeCamera,(life?.revision??0)+(flight?.revision??0));const reflectionStart=performance.now();

  city!.renderReflections(bundle!.renderer,activeCamera);

  const beautyStart=performance.now();bundle!.renderer.render(bundle!.scene,activeCamera);passTimes={shadowMs:reflectionStart-shadowStart,reflectionMs:beautyStart-reflectionStart,beautyMs:performance.now()-beautyStart};

}

async function fullscreen(){

  const session=++fullscreenSession;

  try{

    if(document.fullscreenElement){await document.exitFullscreen();return;}

    await document.documentElement.requestFullscreen();

    const keyboard=(navigator as unknown as {keyboard?:{lock:(keys:string[])=>Promise<void>;unlock:()=>void}}).keyboard;

    if(document.fullscreenElement&&!disposed&&keyboard){

      await keyboard.lock(['Escape']).catch(()=>{});

      if(disposed||session!==fullscreenSession||!document.fullscreenElement)keyboard.unlock();

    }

  }catch{$('fullscreen').title='Fullscreen is unavailable in this browser window';}

}

async function boot(){

  bundle=await createRenderer(canvas,fatal);timings.rendererReady=performance.now()-startup;

  if(disposed){bundle.dispose();return;}

  city=await loadCity(bundle.scene,progress);timings.assetsReady=performance.now()-startup;

  if(disposed){releaseCity();bundle.dispose();return;}

  collision=new CityCollision(city.data);timings.collisionReady=performance.now()-startup;

  progress("Bringing the streets to life…");life=await CityLife.create(city,collision,bundle.scene);timings.lifeReady=performance.now()-startup;

  if(disposed){life.dispose();releaseCity();bundle.dispose();return;}

  progress('Preparing the aircraft…');flight=new CityFlight(city,bundle.scene,perspective,canvas);timings.flightReady=performance.now()-startup;

  activeCamera=perspective;controls=new OrbitControls(perspective,canvas);controls.enableDamping=true;controls.dampingFactor=.1;controls.screenSpacePanning=false;controls.minPolarAngle=.005;

  controls.addEventListener('change',()=>{dirty=true;});controls.addEventListener('start',()=>{tween=null;document.body.classList.add('compact');});

  overview(false,true);resize();

  const list=$('place-list');

  for(const landmark of city.data.landmarks){const button=document.createElement('button');button.textContent=landmark.name;const arrow=document.createElement('small');arrow.textContent='↗';button.append(arrow);on(button,'click',()=>visit(landmark));list.append(button);}

  on($('aerial'),'click',()=>overview());on($('plan'),'click',()=>overview(true));on(document.querySelector('.brand')!,'click',(e:Event)=>{e.preventDefault();document.body.classList.remove('compact');overview();});

  on($('destinations-button'),'click',()=>{const opened=$('destinations').hidden;$('destinations').hidden=!opened;$('destinations-button').setAttribute('aria-expanded',String(opened));});

  on($('walk'),'click',()=>enterWalk());on($('nav-walk'),'click',()=>enterWalk());on($('resume'),'click',()=>canvas.requestPointerLock().catch(()=>{}));on($('reset'),'click',()=>enterWalk(true,defaultSpawn()));on($('overview'),'click',()=>overview());on($('fullscreen'),'click',fullscreen);

  on($('nav-fly'),'click',enterFlight);on($('flight-resume'),'click',resumeFlight);on($('flight-reset'),'click',resetFlight);
  on($('flight-exit'),'click',()=>overview());on($('flight-pause-button'),'click',pauseFlight);

  on(document,'pointerlockchange',()=>{if(mode==='walk'){paused=document.pointerLockElement!==canvas;keys.clear();setActiveUi();dirty=true;}});

  on(document,'mousemove',(event:MouseEvent)=>{if(mode!=='walk'||paused)return;euler.setFromQuaternion(perspective.quaternion);euler.y-=event.movementX*.0018;euler.x=Math.max(-1.48,Math.min(1.48,euler.x-event.movementY*.0018));perspective.quaternion.setFromEuler(euler);dirty=true;});

  on(document,'keydown',(event:KeyboardEvent)=>{
    if(event.ctrlKey||event.metaKey||event.altKey||(event.target instanceof HTMLElement&&event.target.matches('input,textarea,[contenteditable="true"]')))return;
    const key=event.key.toLowerCase();
    if(key==='escape'){pauseExploration();event.preventDefault();return;}
    if(mode==='flight'){
      if(event.code==='KeyR'&&!event.repeat){resetFlight();event.preventDefault();}
      else if(event.code==='Enter'&&paused&&!event.repeat){resumeFlight();event.preventDefault();}
      return;
    }
    if(mode==='walk'&&!paused&&['w','a','s','d','z','q','shift','arrowup','arrowdown','arrowleft','arrowright'].includes(key)){keys.add(key);event.preventDefault();}
  });

  on(document,'keyup',(event:KeyboardEvent)=>keys.delete(event.key.toLowerCase()));

  on(window,'blur',pauseExploration);on(document,'visibilitychange',()=>{lastTime=performance.now();if(document.hidden)pauseExploration();});on(window,'resize',resize);

  on(document,'fullscreenchange',()=>{const full=Boolean(document.fullscreenElement);$('fullscreen').setAttribute('aria-label',full?'Exit fullscreen':'Enter fullscreen');$('fullscreen').title=full?'Exit fullscreen':'Fullscreen';if(!full){fullscreenSession++;(navigator as any).keyboard?.unlock();}resize();});

  progress('Opening the streets…');

  await bundle.renderer.compileAsync(bundle.scene,activeCamera,undefined,(event:ProgressEvent)=>{if(event.loaded%100===0)progress(`Preparing city materials · ${Math.round(event.loaded/event.total*100)}%`);});

  if(disposed||failed)return;

  if(bundle.sun.shadow.map)bundle.renderer.initRenderTarget(bundle.sun.shadow.map);

  bundle.sun.shadow.needsUpdate=true;

  renderCityFrame();

  if(new URLSearchParams(location.search).has('debug'))console.info('City first submission',JSON.stringify({time:performance.now()-startup,inventory:city.inventory,programs:{vertex:(bundle.renderer as any)._pipelines.programs.vertex.size,fragment:(bundle.renderer as any)._pipelines.programs.fragment.size,pipelines:(bundle.renderer as any)._pipelines.caches.size}}));

  await bundle.device.queue.onSubmittedWorkDone();timings.compiled=performance.now()-startup;timings.firstCompleteFrame=performance.now()-startup;

  if(disposed||failed)return;

  $('loading').style.opacity='0';setTimeout(()=>$('loading').hidden=true,650);bundle.renderer.setAnimationLoop(tick);lastTime=performance.now();

  (window as any).__cityTest={

    ready:true,

    flight:{snapshot:()=>flight!.snapshot(),start:enterFlight,pause:(value:boolean)=>value?pauseFlight():resumeFlight(),reset:resetFlight,setPose:(position:Vec3,yaw=Math.PI/2,pitch=0,bank=0,speed=45)=>{flight!.setPose(position,yaw,pitch,bank,speed);updateFlightUi();dirty=true;return flight!.snapshot();},step:(dt:number)=>{flight!.update(dt);updateFlightUi();dirty=true;return flight!.snapshot();}},

    lifeSnapshot:()=>life!.snapshot(),
    auditVehicleTransforms:()=>life!.auditVehicleTransforms(),
    auditPromotedVehicleDraws:()=>{
      const backend=bundle!.renderer.backend as any,draw=backend.draw.bind(backend),promoted=new Set(city!.promotedVehicles.map(i=>i.id)),audit={staticBatchDraws:0,fixedVehicleDraws:[] as string[],movingMeshDraws:0};
      backend.draw=(object:any,info:any)=>{const mesh=object.object;if(mesh.isBatchedMesh){audit.staticBatchDraws++;const ids=mesh._indirectTexture.image.data;for(let i=0;i<mesh._multiDrawCount;i++){const id=mesh.userData.sourceInstances?.[ids[i]];if(promoted.has(id)&&audit.fixedVehicleDraws.length<100)audit.fixedVehicleDraws.push(id);}}else if(mesh.name?.startsWith('moving_'))audit.movingMeshDraws++;return draw(object,info);};return audit;
    },
    inspectPedestrian:(id:string)=>life!.pedestrians.inspect(id),
    auditLifeDraws:()=>{
      const backend=bundle!.renderer.backend as any,draw=backend.draw.bind(backend),counts:Record<string,number>={};
      backend.draw=(object:any,info:any)=>{const mesh=object.object;if(mesh.isSkinnedMesh||mesh.name?.startsWith('moving_')){const role=object.camera.layers.mask===2?'dynamic-shadow':object.camera.position.y<0?'reflection':'beauty',key=role+':'+(mesh.isSkinnedMesh?'pedestrian':'vehicle');counts[key]=(counts[key]??0)+1;}return draw(object,info);};return counts;
    },
    auditLifeShadows:async()=>{bundle!.renderer.setAnimationLoop(null);life!.setPaused(true);renderCityFrame();await bundle!.device.queue.onSubmittedWorkDone();return bundle!.auditShadow(activeCamera);},
    resumeFrames:()=>{lastTime=performance.now();bundle!.renderer.setAnimationLoop(tick);dirty=true;},

    life:{setPaused:(paused:boolean)=>{life!.setPaused(paused);lastTime=performance.now();},step:(dt:number)=>{life!.step(dt);dirty=true;return life!.snapshot();},stats:()=>life!.stats()},

    getState:()=>({mode,paused,position:perspective.position.toArray(),rotation:[perspective.rotation.x,perspective.rotation.y,perspective.rotation.z],footHeight,eyeHeight:perspective.position.y-footHeight,keys:[...keys],pointerLocked:document.pointerLockElement===canvas,fullscreen:!!document.fullscreenElement,sourceHash:city!.data.sourceHash,inventory:city!.inventory,vehiclePromotion:{...city!.auditPromotions(),retiredStaticColliders:city!.promotedVehicles.filter(i=>collision.staticColliderIds.has(i.id)).map(i=>i.id)},transferAudit:city!.transferAudit,reflectorPlanes:city!.reflectors.map(r=>r.target.position.y),backend:bundle!.backendInfo,timings,errors:[...errors],dpr:bundle!.renderer.getPixelRatio(),viewport:[innerWidth,innerHeight],framebuffer:[canvas.width,canvas.height],camera:activeCamera.position.toArray(),landmarks:city!.data.landmarks,renderInfo:bundle!.renderer.info.render,rendererTrackedMemory:bundle!.renderer.info.memory,shadowNeedsUpdate:bundle!.sun.shadow.needsUpdate,shadowStats:bundle!.shadowStats(),life:life!.stats(),disposed}),

    view:(id:string)=>{if(id==='plan')overview(true,true);else if(id==='aerial')overview(false,true);else{const landmark=city!.data.landmarks.find(l=>l.id===id);if(landmark)visit(landmark,true);}},

    captureCamera:(id:string)=>{

      const cameras=Array.isArray(city!.data.cameras)?city!.data.cameras:Object.values(city!.data.cameras);

      const camera=cameras.find(c=>c.id===id);if(!camera)return false;

      overview(false,true);perspective.fov=THREE.MathUtils.radToDeg(2*Math.atan(36/(2*(id==='overview'?36:26)*perspective.aspect)));perspective.updateProjectionMatrix();controls.minDistance=.05;controls.maxPolarAngle=Math.PI;controls.target.fromArray(camera.target??camera.lookAt??[0,0,0]);perspective.position.fromArray(camera.position);perspective.lookAt(controls.target);controls.update();document.body.classList.add('compact');dirty=true;return true;

    },

    walk:(position?:Vec3)=>enterWalk(false,position),

    setPose:(position:Vec3,yaw=0,pitch=0)=>{enterWalk(false,position);perspective.rotation.set(pitch,yaw,0,'YXZ');dirty=true;},

    collision:(x:number,z:number)=>({blocked:collision.blocked(x,z),support:collision.support(x,z),water:collision.isWater(x,z)}),

    moveBy:(x:number,z:number)=>{const p=collision.move(perspective.position.x,perspective.position.z,x,z,footHeight);perspective.position.set(p[0],p[1]+BODY.eye,p[2]);footHeight=p[1];dirty=true;return p;},

    sampleFrames:async(count=120)=>{frames=[];forceFrames=count+4;await new Promise<void>(resolve=>{const wait=()=>forceFrames>0&&!failed?setTimeout(wait,80):resolve();wait();});return frames.slice(4);},

    requestFrames:(count=2)=>{forceFrames=count;dirty=true;},

    setBatchCulling:(enabled:boolean)=>{for(const mesh of city!.root.children)if(mesh instanceof THREE.BatchedMesh){mesh.perObjectFrustumCulled=enabled;(mesh as any)._visibilityChanged=true;}dirty=true;},

    singleFrameAt:async(position:Vec3,yaw=0,pitch=0)=>{bundle!.renderer.setAnimationLoop(null);enterWalk(false,position);perspective.rotation.set(pitch,yaw,0,'YXZ');dirty=true;tick(performance.now());await bundle!.device.queue.onSubmittedWorkDone();return frames.at(-1);},

    auditBatches:()=>{

      const backend=bundle!.renderer.backend as any,pending=new Map<any,any[]>(),audit={draws:0,cameraMismatches:[] as any[],textureMismatches:[] as any[]};

      for(const mesh of city!.root.children as any[]){if(!mesh.isBatchedMesh)continue;const before=mesh.onBeforeRender.bind(mesh);mesh.onBeforeRender=(...args:any[])=>{before(...args);mesh.userData.preparedCamera=args[2].id;};}

      const draw=backend.draw.bind(backend);backend.draw=(object:any,info:any)=>{

        const mesh=object.object;if(mesh.isBatchedMesh){audit.draws++;if(mesh.userData.preparedCamera!==object.camera.id&&audit.cameraMismatches.length<100)audit.cameraMismatches.push({mesh:mesh.name,prepared:mesh.userData.preparedCamera,camera:object.camera.id});

          if(!pending.has(object.context))pending.set(object.context,[]);pending.get(object.context)!.push({mesh,ids:mesh._indirectTexture.image.data.slice(0,mesh._multiDrawCount),camera:object.camera.id});}

        return draw(object,info);

      };

      const finish=backend.finishRender.bind(backend);backend.finishRender=(context:any)=>{for(const record of pending.get(context)??[]){const current=record.mesh._indirectTexture.image.data;let mismatch=0;for(let i=0;i<record.ids.length;i++)if(record.ids[i]!==current[i])mismatch++;if(mismatch&&audit.textureMismatches.length<100)audit.textureMismatches.push({mesh:record.mesh.name,camera:record.camera,drawCount:record.ids.length,mismatch});}pending.delete(context);return finish(context);};

      return audit;

    },

    getFrames:()=>frames,

    dispose:()=>dispose(),

  };

}

function releaseCity(){for(const mesh of city?.root.children??[])if(mesh instanceof THREE.BatchedMesh)mesh.dispose();for(const g of city?.geometries??[])g.dispose();for(const m of city?.materials??[])m.dispose();for(const r of city?.reflectors??[])r.dispose();}

function dispose(){if(disposed)return;disposed=true;fullscreenSession++;(navigator as any).keyboard?.unlock();if(document.pointerLockElement===canvas)document.exitPointerLock();bundle?.renderer.setAnimationLoop(null);for(const l of listeners)l.target.removeEventListener(l.type,l.handler);controls?.dispose();flight?.dispose();life?.dispose();releaseCity();bundle?.dispose();}

on(window,'pagehide',dispose);

boot().catch(error=>fatal(error instanceof Error?error.message:String(error)));

