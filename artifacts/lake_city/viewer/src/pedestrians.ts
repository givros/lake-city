import * as THREE from 'three/webgpu';
import {assetUrl} from './assets';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {clone} from 'three/addons/utils/SkeletonUtils.js';
import {CityCollision} from './collision';
import {Ground} from './ground';
import type {LoadedCity} from './scene';
import type {Vec2} from './types';

type Corridor={id:string;points:number[][];width:number};
type Route={id:string;points:Vec2[];lengths:number[];length:number;closed:boolean};
type Walker={id:string;root:THREE.Group;mixer:THREE.AnimationMixer;walk:THREE.AnimationAction;idle:THREE.AnimationAction;route:Route;distance:number;direction:number;speed:number;cruise:number;wait:number;walkWeight:number;scale:number;surface:number;offset:number;travelled:number;stationaryFor:number;maxStationary:number;colors:Record<string,string>};
const segmentDistance=(x:number,z:number,a:number[],b:number[])=>{const dx=b[0]-a[0],dz=b[1]-a[1],t=Math.max(0,Math.min(1,((x-a[0])*dx+(z-a[1])*dz)/(dx*dx+dz*dz||1)));return Math.hypot(x-a[0]-dx*t,z-a[1]-dz*t);};
const palettes=[['#bb8562','#435d70','#353b40'],['#e0b58f','#a87651','#4b5457'],['#825238','#6b7860','#343e4d'],['#c59673','#866d80','#394552'],['#dfbfa1','#c7c5b4','#485460'],['#66432f','#647e82','#5b5047']];

function makeRoutes(city:LoadedCity,collision:CityCollision,corridors:Corridor[],ground:Ground){
  const roads=corridors.flatMap(c=>c.points.slice(1).map((b,i)=>({a:c.points[i],b,r:c.width/2+.65,minX:Math.min(c.points[i][0],b[0])-c.width/2-1,maxX:Math.max(c.points[i][0],b[0])+c.width/2+1,minZ:Math.min(c.points[i][1],b[1])-c.width/2-1,maxZ:Math.max(c.points[i][1],b[1])+c.width/2+1})));
  const safe=(x:number,z:number)=>ground.heightAt(x,z)!==null&&!collision.blocked(x,z)&&!roads.some(r=>x>=r.minX&&x<=r.maxX&&z>=r.minZ&&z<=r.maxZ&&segmentDistance(x,z,r.a,r.b)<r.r);
  const routes:Route[]=[];
  const push=(id:string,points:Vec2[],closed=false)=>{if(points.length<2)return;const lengths=[0];for(let i=1;i<points.length;i++)lengths.push(lengths.at(-1)!+Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1]));if(lengths.at(-1)!>=18)routes.push({id,points,lengths,length:lengths.at(-1)!,closed});};
  for(const path of city.data.paths){if(!/sidewalk|^PATH_PARK_|^PATH_LAKE_COMPLETE_LOOP$|^PATH_BLOCK_/.test(path.id)||/EXPRESS|HIGHWAY|RAMP/i.test(path.id))continue;const sampled:Vec2[]=[];
    for(let i=1;i<path.points.length;i++){const a=path.points[i-1],b=path.points[i],n=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/.75));for(let j=0;j<n;j++)sampled.push([a[0]+(b[0]-a[0])*j/n,a[1]+(b[1]-a[1])*j/n]);}sampled.push(path.points.at(-1)!);
    let part:Vec2[]=[],number=0,allSafe=true;for(const [index,p] of sampled.entries()){const a=sampled[Math.max(0,index-1)],b=sampled[Math.min(sampled.length-1,index+1)],len=Math.hypot(b[0]-a[0],b[1]-a[1])||1,ox=(b[1]-a[1])/len*.5,oz=-(b[0]-a[0])/len*.5;if(safe(...p)&&safe(p[0]+ox,p[1]+oz)&&safe(p[0]-ox,p[1]-oz))part.push(p);else{allSafe=false;push(`${path.id}:${number++}`,part);part=[];}}push(`${path.id}:${number}`,part,path.closed&&allSafe);
  }
  return {routes,safe};
}
function pose(route:Route,d:number){let lo=0,hi=route.lengths.length-1;while(lo+1<hi){const m=(lo+hi)>>1;if(route.lengths[m]<=d)lo=m;else hi=m;}const a=route.points[lo],b=route.points[Math.min(lo+1,route.points.length-1)],t=(d-route.lengths[lo])/(route.lengths[Math.min(lo+1,route.lengths.length-1)]-route.lengths[lo]||1);return {x:a[0]+(b[0]-a[0])*t,z:a[1]+(b[1]-a[1])*t,yaw:Math.atan2(b[0]-a[0],b[1]-a[1])};}
export class Pedestrians {
  readonly root=new THREE.Group();readonly walkers:Walker[]=[];readonly routes:Route[];readonly metadata:any;readonly ground:Ground;readonly safe:(x:number,z:number)=>boolean;
  readonly timings:Record<string,number>={};private original:THREE.Object3D;private materials:THREE.Material[]=[];
  static async create(city:LoadedCity,collision:CityCollision,corridors:Corridor[],count=80){const [gltf,metadata]=await Promise.all([new GLTFLoader().loadAsync(assetUrl('characters/pedestrian.glb')),fetch(assetUrl('characters/pedestrian.json')).then(r=>{if(!r.ok)throw new Error('Pedestrian information could not be loaded.');return r.json();})]);return new Pedestrians(city,collision,corridors,count,gltf.scene,gltf.animations,metadata);}
  private constructor(city:LoadedCity,collision:CityCollision,corridors:Corridor[],count:number,original:THREE.Object3D,clips:THREE.AnimationClip[],metadata:any){
    const start=performance.now();this.original=original;this.metadata=metadata;this.ground=new Ground(city);this.timings.ground=performance.now()-start;const {routes,safe}=makeRoutes(city,collision,corridors,this.ground);this.timings.routes=performance.now()-start-this.timings.ground;this.routes=routes;this.safe=safe;this.root.name='CityPedestrians';
    if(!routes.length)throw new Error('No safe pedestrian routes were found.');
    const walkClip=clips.find(c=>c.name==='Walk'),idleClip=clips.find(c=>c.name==='Idle');if(!walkClip||!idleClip)throw new Error('The pedestrian asset is missing its original Walk or Idle clip.');
    let seed=49113;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
    const anchors=city.data.landmarks.map(l=>l.walkPosition??l.lookAt);
    for(let i=0;i<count;i++){
      let route:Route,distance:number;
      if(i<40){const anchor=anchors[Math.floor(i/8)%anchors.length];let best={distance:Infinity,route:routes[0],arc:0};for(const r of routes.filter(r=>r.length>=68))for(let k=0;k<r.points.length;k++){const p=r.points[k],d=Math.hypot(p[0]-anchor[0],p[1]-anchor[2]);if(d<best.distance)best={distance:d,route:r,arc:r.lengths[k]};}route=best.route;distance=Math.max(2,Math.min(route.length-2,best.arc+(i%8-3.5)*7.3));}
      else{const eligible=routes.filter(r=>r.length>45);route=eligible[Math.floor(random()*eligible.length)]??routes[i%routes.length];distance=2+random()*(route.length-4);}
      // Keep initial neighbors separated even on short civic sidewalk segments.
      for(let attempt=0;attempt<20&&this.walkers.some(w=>w.route===route&&Math.abs(w.distance-distance)<2);attempt++)distance=2+random()*(route.length-4);
      const body=clone(original),root=new THREE.Group();root.name=`pedestrian_${String(i).padStart(3,'0')}`;root.add(body);const scale=metadata.recommended_uniform_scale*(.96+(i%5)*.02);root.scale.setScalar(scale);this.root.add(root);
      const palette=palettes[i%palettes.length],colors={CharacterMaterial:palette[0],LongSleeveShirtMaterial:palette[1],PantsMaterial:palette[2]};
      body.traverse(object=>{if(object instanceof THREE.Mesh){object.layers.enable(1);object.castShadow=true;object.receiveShadow=true;object.frustumCulled=true;if(object instanceof THREE.SkinnedMesh)object.boundingSphere=new THREE.Sphere(new THREE.Vector3(0,.5,0),2);const paint=(m:THREE.Material)=>{const n=m.clone() as THREE.MeshStandardMaterial;const c=colors[m.name as keyof typeof colors];if(c)n.color.set(c);this.materials.push(n);return n;};object.material=Array.isArray(object.material)?object.material.map(paint):paint(object.material);}});
      const mixer=new THREE.AnimationMixer(body),walk=mixer.clipAction(walkClip),idle=mixer.clipAction(idleClip);walk.play();idle.play();walk.time=random()*walkClip.duration;idle.time=random()*idleClip.duration;
      const waiting=i%11===0,walker:Walker={id:root.name,root,mixer,walk,idle,route,distance,direction:i%3===0?-1:1,speed:waiting?0:1.25,cruise:1.12+random()*.36,wait:waiting?1.5+random()*3:0,walkWeight:waiting?0:1,scale,surface:0,travelled:0,stationaryFor:0,maxStationary:0,offset:i%3===0?-.48:.48,colors};this.walkers.push(walker);this.apply(walker,0);
    }
  }
  private apply(w:Walker,dt:number,previousDistance=w.distance){
    const oldX=w.root.position.x,oldZ=w.root.position.z;const oldOffset=w.offset;let offset=dt?THREE.MathUtils.damp(w.offset,w.direction*.48,3,dt):w.direction*.48;
    let p=pose(w.route,w.distance),x=p.x+Math.cos(p.yaw)*offset,z=p.z-Math.sin(p.yaw)*offset;
    const clear=(px:number,pz:number)=>this.walkers.every(other=>other===w||Math.hypot(px-other.root.position.x,pz-other.root.position.z)>=.82);
    if(dt&&!clear(x,z)){
      // Hold longitudinal movement while completing the turn into the return lane.
      // Actual-space separation also covers joins between two pedestrian paths.
      w.distance=previousDistance;w.speed=0;p=pose(w.route,w.distance);x=p.x+Math.cos(p.yaw)*offset;z=p.z-Math.sin(p.yaw)*offset;
      if(!clear(x,z)){offset=oldOffset;x=p.x+Math.cos(p.yaw)*offset;z=p.z-Math.sin(p.yaw)*offset;}
    }
    if(dt){const advance=Math.hypot(x-oldX,z-oldZ);w.travelled+=advance;w.stationaryFor=advance<.001?w.stationaryFor+dt:0;w.maxStationary=Math.max(w.maxStationary,w.stationaryFor);}
    w.offset=offset;w.root.position.set(x,0,z);const yaw=p.yaw+(w.direction<0?Math.PI:0),difference=Math.atan2(Math.sin(yaw-w.root.rotation.y),Math.cos(yaw-w.root.rotation.y));w.root.rotation.y=dt?w.root.rotation.y+Math.max(-dt*3.5,Math.min(dt*3.5,difference)):yaw;
    const support=this.ground.heightAt(x,z);if(support===null)throw new Error(`Unsupported pedestrian route: ${w.route.id}`);w.surface=support;
    if(dt)w.walkWeight=THREE.MathUtils.damp(w.walkWeight,w.speed>.05?1:0,8,dt);w.walk.setEffectiveWeight(w.walkWeight);w.idle.setEffectiveWeight(1-w.walkWeight);w.walk.setEffectiveTimeScale(w.speed>0?w.speed/1.32:1);w.mixer.update(dt);
    const feet=THREE.MathUtils.lerp(this.metadata.clips.Idle.recommended_ground_offset_at_scale_1,this.metadata.clips.Walk.recommended_ground_offset_at_scale_1,w.walkWeight);w.root.position.y=w.surface+feet*w.scale;
  }
  update(dt:number){for(const w of this.walkers){const previousDistance=w.distance;if(w.wait>0){w.wait=Math.max(0,w.wait-dt);w.speed=0;}else{
    const ahead=this.walkers.some(o=>o!==w&&o.route===w.route&&o.direction===w.direction&&(o.distance-w.distance)*w.direction>0&&(o.distance-w.distance)*w.direction<1.35);
    const turningEnd=this.walkers.some(o=>o!==w&&o.route===w.route&&o.wait>0&&Math.abs(o.distance-w.distance)<2.5&&(o.distance<1||o.distance>w.route.length-1));
    const current=pose(w.route,w.distance),vx=Math.sin(current.yaw)*w.direction*w.cruise,vz=Math.cos(current.yaw)*w.direction*w.cruise;
    const yieldCrossing=this.walkers.some(o=>{
      if(o===w||o.route===w.route||w.id<o.id)return false;
      const dx=o.root.position.x-w.root.position.x,dz=o.root.position.z-w.root.position.z;if(dx*dx+dz*dz>36)return false;
      const other=pose(o.route,o.distance),rx=Math.sin(other.yaw)*o.direction*o.cruise-vx,rz=Math.cos(other.yaw)*o.direction*o.cruise-vz;
      const closest=Math.max(0,Math.min(2.5,-(dx*rx+dz*rz)/(rx*rx+rz*rz||1)));
      return closest>0&&Math.hypot(dx+rx*closest,dz+rz*closest)<1.15;
    });
    w.speed=ahead||turningEnd||yieldCrossing?0:w.cruise;
    if(w.speed){w.distance+=w.speed*dt*w.direction;if(w.distance>=w.route.length||w.distance<=0){if(w.route.closed)w.distance=(w.distance+w.route.length)%w.route.length;else{w.distance=Math.max(0,Math.min(w.route.length,w.distance));w.direction*=-1;w.wait=1.8+(Number(w.id.slice(-2))%5)*.45;w.speed=0;}}}
    }this.apply(w,dt,previousDistance);
  }}
  snapshot(){return this.walkers.map(w=>({id:w.id,type:'pedestrian',asset:this.metadata.asset,position:w.root.position.toArray(),rotation:w.root.rotation.y,yaw:w.root.rotation.y,scale:w.scale,speed:w.speed,distanceTravelled:w.travelled,maxStationarySeconds:w.maxStationary,stationarySeconds:w.stationaryFor,routeId:w.route.id,routeDistance:w.distance,surfaceY:w.surface,feetOffset:w.root.position.y-w.surface,walkTime:w.walk.time,idleTime:w.idle.time,walkWeight:w.walkWeight,idleWeight:1-w.walkWeight,clipPhase:w.walk.time/w.walk.getClip().duration,clipSpeed:w.walk.getEffectiveTimeScale(),materialColors:w.colors}));}
  inspect(id:string){const w=this.walkers.find(a=>a.id===id);if(!w)return null;w.root.updateMatrixWorld(true);let minY=Infinity,maxY=-Infinity,triangles=0,bones=0,meshes=0;const p=new THREE.Vector3();w.root.traverse(o=>{if(o instanceof THREE.Bone)bones++;if(o instanceof THREE.SkinnedMesh){meshes++;o.skeleton.update();triangles+=(o.geometry.index?.count??o.geometry.getAttribute('position').count)/3;for(let i=0;i<o.geometry.getAttribute('position').count;i++){o.getVertexPosition(i,p);p.applyMatrix4(o.matrixWorld);minY=Math.min(minY,p.y);maxY=Math.max(maxY,p.y);}}});return {id,meshes,bones,triangles,minY,maxY,surface:w.surface,lowestSoleGap:minY-w.surface,height:maxY-minY,root:w.root.position.toArray(),walkTime:w.walk.time,idleTime:w.idle.time};}
  stats(){return {count:this.walkers.length,timings:this.timings,routes:this.routes.length,maximumStationarySeconds:Math.max(...this.walkers.map(w=>w.maxStationary)),stalled:this.walkers.filter(w=>w.stationaryFor>15).map(w=>w.id),moving:this.walkers.filter(w=>w.speed>0).length,idle:this.walkers.filter(w=>w.speed===0).length,unsafe:this.walkers.filter(w=>!this.safe(w.root.position.x,w.root.position.z)).map(w=>w.id),triangles:this.metadata.total_triangles*this.walkers.length,bonesPerActor:this.metadata.bone_count,assetSHA256:this.metadata.asset_sha256};}
  dispose(){for(const w of this.walkers){w.mixer.stopAllAction();w.mixer.uncacheRoot(w.mixer.getRoot());w.root.traverse(o=>{if(o instanceof THREE.SkinnedMesh)o.skeleton.dispose();});}for(const m of this.materials)m.dispose();const geometries=new Set<THREE.BufferGeometry>(),materials=new Set<THREE.Material>();this.original.traverse(o=>{if(o instanceof THREE.Mesh){geometries.add(o.geometry);for(const m of Array.isArray(o.material)?o.material:[o.material])materials.add(m);}});for(const g of geometries)g.dispose();for(const m of materials)m.dispose();this.root.removeFromParent();}
}
