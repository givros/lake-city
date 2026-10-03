import strictAssert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {stripTypeScriptTypes} from 'node:module';
import {fileURLToPath} from 'node:url';
import * as THREE from 'three/webgpu';
let checks=0;
const assert=Object.assign((...args)=>{checks++;strictAssert(...args);},{equal:(...args)=>{checks++;strictAssert.equal(...args);}});

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const modules=new Map();
function moduleUrl(file){
  file=path.resolve(file);if(modules.has(file))return modules.get(file);
  let source=stripTypeScriptTypes(fs.readFileSync(file,'utf8'),{mode:'transform'});
  source=source.replace(/from\s*(['"])([^'"]+)\1/g,(_all,_quote,name)=>{
    const url=name.startsWith('.')?moduleUrl(path.resolve(path.dirname(file),`${name}.ts`)):import.meta.resolve(name);
    return `from ${JSON.stringify(url)}`;
  });
  const url=`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;modules.set(file,url);return url;
}
const {ManualFlightController,wheelSupportHeight}=await import(moduleUrl(path.join(root,'src/flight/controller.ts')));
const {FlightCollision}=await import(moduleUrl(path.join(root,'src/flight/collision.ts')));
const {CityFlight}=await import(moduleUrl(path.join(root,'src/flight/CityFlight.ts')));
const neutral={throttle:0,pitch:0,roll:0,rudder:0,brake:false};
const airborne=()=>{
  const controller=new ManualFlightController(()=>0);controller.start();
  Object.assign(controller.state,{speed:45,throttle:.72,rpm:2001.6,grounded:false,phase:'flight',pitch:2.4*Math.PI/180});
  controller.state.position.set(-560,240,250);return controller;
};
const a=airborne(),b=airborne();
for(let i=0;i<600;i++)a.update(1/30,{...neutral,roll:i<120?.3:0});
for(let i=0;i<1200;i++)b.update(1/60,{...neutral,roll:i<240?.3:0});
const frameRateDrift=a.state.position.distanceTo(b.state.position);
assert(frameRateDrift<1e-8,'Fixed-step dynamics must not depend on render FPS');
assert(Math.abs(a.state.yaw)>.2,'Bank input must produce a real coordinated turn');
assert(a.state.position.y>50&&!a.state.crashed,'Starting flight must remain stable with normal throttle');
const throttle=airborne();for(let i=0;i<120;i++)throttle.update(1/60,{...neutral,throttle:1});
assert(throttle.state.throttle>.99&&throttle.state.speed>45,'Adding power must accelerate the airplane');
const pitch=airborne();for(let i=0;i<60;i++)pitch.update(1/60,{...neutral,pitch:-1});
assert(pitch.state.pitch<-.1,'Up arrow input must lower the nose');
const ground=new ManualFlightController(()=>0);ground.start();
for(let i=0;i<1200&&!ground.state.crashed&&!ground.state.takeoffs;i++)ground.update(1/120,{...neutral,throttle:1,pitch:1});
assert(ground.state.takeoffs===1&&!ground.state.grounded,'Original authored ground roll must still take off');
assert(Math.abs(wheelSupportHeight(()=>3,0,0,0,0,0)-3)<1e-12,'Wheel support must align with a raised ground surface');
const brake=new ManualFlightController(()=>0);brake.start();brake.state.speed=20;
for(let i=0;i<120;i++)brake.update(1/60,{...neutral,brake:true});
assert.equal(brake.state.speed,0,'Wheel brakes must stop a grounded airplane');

const data=JSON.parse(fs.readFileSync(path.join(root,'public/assets/city.json'),'utf8'));
const buffer=fs.readFileSync(path.join(root,'public/assets/geometry.bin'));
const binary=buffer.buffer.slice(buffer.byteOffset,buffer.byteOffset+buffer.byteLength),geometryMap=new Map();
for(const [name,prototype] of Object.entries(data.prototypes))geometryMap.set(name,prototype.meshes.map(mesh=>{
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(binary,mesh.positionOffset,mesh.positionCount),3));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(binary,mesh.indexOffset,mesh.indexCount),1));return geometry;
}));
const world=new FlightCollision({data,geometryMap});
const pose=(x,y,z,yaw=0,bank=0)=>({position:new THREE.Vector3(x,y,z),yaw,pitch:0,bank,grounded:false});
const outsideCityGround=world.ground.heightAt(2000,0);
assert(outsideCityGround!==null&&Math.abs(outsideCityGround+.12)<1e-5,'The existing ground outside city bounds must retain its actual height');
assert.equal(world.check(pose(2000,2,0),pose(2004,2,0)),null,'Low flight over real ground outside the city must not be misclassified as water');
const spawn=pose(-560,240,250,Math.PI/2);
assert.equal(world.check(spawn,spawn),null,'Initial lake flight must be clear of all city geometry');
const water=pose(-560,0,250);assert.equal(world.check(water,water)?.reason,'water','The lake must not become a landing surface');
const tower=data.instances.find(i=>i.prototype.startsWith('tower_'));
const towerBox=new THREE.Box3();for(const geometry of geometryMap.get(tower.prototype)){geometry.computeBoundingBox();towerBox.union(geometry.boundingBox);}
const towerTop=tower.position[1]+towerBox.max.y*tower.scale[1];
const inside=pose(tower.position[0],tower.position[1]+(towerBox.max.y+towerBox.min.y)*tower.scale[1]*.5,tower.position[2]);
assert.equal(world.check(inside,inside)?.reason,'obstacle','A tower must stop an airplane at its actual height');
const above=pose(tower.position[0],towerTop+25,tower.position[2]);
assert.equal(world.check(above,above),null,'Walking footprints must not become infinitely tall flight obstacles');
assert.equal(world.check(pose(tower.position[0]-100,inside.position.y,tower.position[2]),pose(tower.position[0]+100,inside.position.y,tower.position[2]))?.reason,'obstacle','Swept collision must catch a tower crossed between samples');
assert(world.colliderCount>9500,'Flight obstacles must include real trees, props and buildings');

// Exercise integration lifecycle without a GPU or the user's browser.
globalThis.window=new EventTarget();
globalThis.document=Object.assign(new EventTarget(),{hidden:false,body:{},activeElement:null});
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(48,16/9,.1,12000);
const flight=new CityFlight({data,geometryMap},scene,camera,{tabIndex:0,focus(){}});flight.start();
const edges=[
  {side:'east',position:[data.bounds.max[0]-1,300,0],yaw:Math.PI/2,axis:0,sign:1,bound:data.bounds.max[0]},
  {side:'west',position:[data.bounds.min[0]+1,300,0],yaw:-Math.PI/2,axis:0,sign:-1,bound:data.bounds.min[0]},
  {side:'south',position:[0,300,data.bounds.max[1]-1],yaw:0,axis:2,sign:1,bound:data.bounds.max[1]},
  {side:'north',position:[0,300,data.bounds.min[1]+1],yaw:Math.PI,axis:2,sign:-1,bound:data.bounds.min[1]},
];
const cityEdgeCrossings=[];
for(const edge of edges){
  flight.setPose(edge.position,edge.yaw,0,0,45);for(let i=0;i<10;i++)flight.update(.1);
  const s=flight.snapshot(),outwardDistance=(s.position[edge.axis]-edge.bound)*edge.sign;
  assert(s.active&&!s.paused&&!s.crashed&&s.status==='flying',`${edge.side}: flight must continue beyond the city`);
  assert(outwardDistance>30,`${edge.side}: the aircraft must cross the real map edge and keep moving outward`);
  assert(Math.abs(s.yaw-edge.yaw)<1e-12,`${edge.side}: crossing must not change the heading`);
  assert(!/edge|limit|ceiling/i.test(s.warning??''),`${edge.side}: there must be no artificial flight-area warning`);
  cityEdgeCrossings.push({side:edge.side,outwardDistance,yaw:s.yaw,position:s.position,active:s.active,paused:s.paused});
}
flight.setPose([-560,719.9,250],Math.PI/2,.25,0,55);flight.controller.state.flightPathAngle=.2;flight.update(.1);
const crossing720=flight.snapshot();assert(crossing720.active&&!crossing720.paused&&crossing720.position[1]>720,'Climbing through 720m must remain unrestricted');
flight.setPose([-560,2001,250],Math.PI/2,0,0,45);flight.update(.1);
const above2000=flight.snapshot();assert(above2000.active&&!above2000.paused&&above2000.position[1]>2000&&!above2000.crashed,'Flight above 2000m must remain active');
assert(Math.abs(above2000.yaw-Math.PI/2)<1e-12,'Altitude must not trigger an automatic heading change');
flight.setPose([10000,2001,10000],Math.PI/2,0,0,45);flight.update(.1);const distant=flight.snapshot();
assert(distant.active&&!distant.paused&&distant.position[0]>10004&&distant.position[2]===10000,'Flight far outside the authored city must not teleport or pause');
flight.setPaused(true);const manualPause=flight.controller.state.position.clone();flight.update(.1);
assert(flight.paused&&flight.controller.state.position.equals(manualPause),'Manual pause must still freeze unrestricted flight');
flight.setPaused(false);
window.dispatchEvent(new Event('blur'));const held=flight.controller.state.position.clone();flight.update(.1);
assert(flight.paused&&flight.controller.state.position.equals(held),'Losing focus must freeze flight until resumed');
flight.setPaused(false);flight.update(.1);assert(!flight.controller.state.position.equals(held),'Explicit Resume must continue flight');
flight.setPose([-560,0,250]);flight.update(.05);assert.equal(flight.status,'crashed');
flight.reset();assert(flight.status==='flying'&&!flight.crashed&&flight.controller.state.position.y===240,'Reset must recover from water contact');
flight.setPose(inside.position.toArray());flight.update(.05);assert.equal(flight.status,'crashed','City buildings must still stop the airplane');
flight.reset();assert(flight.status==='flying'&&!flight.crashed,'Reset must recover after a tower collision');
flight.exit();assert(!flight.active&&!flight.aircraft.root.visible&&!flight.input.enabled,'Exiting must release controls and hide the aircraft');
flight.dispose();assert.equal(scene.children.length,0,'Disposing must remove the flight model');

const report={passed:true,sourceHash:data.sourceHash,checks,frameRateDrift,colliderCount:world.colliderCount,tower:{id:tower.id,roofHeight:towerTop},groundTakeoff:ground.state.takeoffs,brakeStopped:brake.state.speed===0,initialFlightClear:true,waterContact:true,finiteBuildingHeight:true,sweptBuildingCollision:true,outsideCityGround,cityEdgeCrossings,crossing720,above2000,distantFlight:distant,pauseFocusRecovery:true,exitDisposal:true};
fs.writeFileSync(path.join(root,'../comparisons/flight_physics_report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));
