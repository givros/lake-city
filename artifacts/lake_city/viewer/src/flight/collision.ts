import {Box3, Vector3} from 'three/webgpu';
import {Ground} from '../ground';
import {inPolygon} from '../collision';
import type {LoadedCity} from '../scene';
import {VEHICLE_PROTOTYPES,type Vec2} from '../types';
import type {FlightState} from './types';

interface Solid {id:string;prototype:string;x:number;y:number;z:number;c:number;s:number;min:Vector3;max:Vector3}
interface WaterArea {points:Vec2[];minX:number;maxX:number;minZ:number;maxZ:number}
export interface FlightPose {position:Vector3;yaw:number;pitch:number;bank:number}
export interface FlightHit {reason:'obstacle'|'water'|'terrain';id:string;prototype?:string}
// Overlapping fuselage, wing and undercarriage probes preserve the full wingspan.
// Wheels are handled by the authored three-point landing solver on solid ground.
const PROBES=[
  [0,2.15,3.4,.85,0],[0,2.15,1.8,1,0],[0,2.0,0,1,0],
  [0,2.0,-1.7,.75,0],[0,2.15,-3.2,.55,0],[0,2.6,-4.4,.45,0],
  [-1.8,2.5,.0,.42,0],[-3.3,2.5,.0,.36,0],[-4.7,2.5,.0,.32,0],[-5.65,2.5,.0,.25,0],
  [1.8,2.5,.0,.42,0],[3.3,2.5,.0,.36,0],[4.7,2.5,.0,.32,0],[5.65,2.5,.0,.25,0],
  [-1.7,2.4,-4.5,.3,0],[1.7,2.4,-4.5,.3,0],[0,2.42,4.34,1.86,0],
  [-1.76,.52,.72,.52,1],[1.76,.52,.72,.52,1],[0,.20,-4.67,.20,1],
] as const;

function worldProbe(p:readonly number[],pose:FlightPose,out:Vector3){
  const sb=Math.sin(pose.bank),cb=Math.cos(pose.bank),sp=Math.sin(pose.pitch),cp=Math.cos(pose.pitch);
  const sy=Math.sin(pose.yaw),cy=Math.cos(pose.yaw),bx=p[0]*cb-p[1]*sb,by=p[0]*sb+p[1]*cb;
  const pz=p[2]*cp-by*sp;
  return out.set(pose.position.x+bx*cy+pz*sy,pose.position.y+by*cp+p[2]*sp,pose.position.z-bx*sy+pz*cy);
}

/** Segment against a radius-expanded oriented box; catches thin objects between frames. */
function sweptBox(a:Vector3,b:Vector3,r:number,solid:Solid):boolean{
  const ax=a.x-solid.x,az=a.z-solid.z,bx=b.x-solid.x,bz=b.z-solid.z;
  const origin=[solid.c*ax-solid.s*az,a.y-solid.y,solid.s*ax+solid.c*az];
  const target=[solid.c*bx-solid.s*bz,b.y-solid.y,solid.s*bx+solid.c*bz];
  let lo=0,hi=1;
  for(let axis=0;axis<3;axis++){
    const min=solid.min.getComponent(axis)-r,max=solid.max.getComponent(axis)+r,delta=target[axis]-origin[axis];
    if(Math.abs(delta)<1e-10){if(origin[axis]<min||origin[axis]>max)return false;continue;}
    let first=(min-origin[axis])/delta,last=(max-origin[axis])/delta;
    if(first>last)[first,last]=[last,first];
    lo=Math.max(lo,first);hi=Math.min(hi,last);if(lo>hi)return false;
  }
  return true;
}

/** City-height-aware obstacles, independent of the walking-only collision footprints. */
export class FlightCollision {
  readonly ground:Ground;
  readonly colliderCount:number;
  private readonly waters:WaterArea[];
  private readonly islands:WaterArea[];
  private readonly cells=new Map<string,Solid[]>();
  private readonly start=new Vector3();
  private readonly end=new Vector3();
  private readonly candidates=new Set<Solid>();
  private readonly cellSize=48;
  private readonly maximumGroundHeight:number;

  constructor(city:LoadedCity){
    const area=(points:Vec2[]):WaterArea=>({points,minX:Math.min(...points.map(p=>p[0])),maxX:Math.max(...points.map(p=>p[0])),minZ:Math.min(...points.map(p=>p[1])),maxZ:Math.max(...points.map(p=>p[1]))});
    this.waters=city.data.waterPolygons.map(area);this.islands=(city.data.waterHolePolygons??[]).map(area);
    const boxes=new Map<string,Box3>();
    const surfaceBoxes=new Map<string,Box3>();
    for(const [id,geometries] of city.geometryMap){
      if(VEHICLE_PROTOTYPES.has(id)||id==='neighborhood_parking_markings')continue;
      const box=new Box3();
      for(const geometry of geometries){if(!geometry.boundingBox)geometry.computeBoundingBox();box.union(geometry.boundingBox!);}
      if(id.startsWith('surfaces_')){surfaceBoxes.set(id,box);continue;}
      if(!box.isEmpty()&&box.max.y-box.min.y>.25)boxes.set(id,box);
    }
    let maximumGroundHeight=Math.max(0,...(city.data.walkSurfaces??[]).map(surface=>surface.height));
    const supportExtent=new Box3(),point=new Vector3();
    for(const instance of city.data.instances){
      const box=surfaceBoxes.get(instance.prototype);if(!box||box.isEmpty())continue;
      const c=Math.cos(instance.rotation),s=Math.sin(instance.rotation),[px,py,pz]=instance.position,[sx,sy,sz]=instance.scale;
      for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){
        point.set(px+c*x*sx+s*z*sz,py+y*sy,pz-s*x*sx+c*z*sz);supportExtent.expandByPoint(point);
        maximumGroundHeight=Math.max(maximumGroundHeight,point.y);
      }
    }
    // Ground uses these bounds only to index existing triangles. Keep the walking
    // map unchanged while sampling the real forest floor beyond the city blocks.
    const bounds=supportExtent.isEmpty()?city.data.bounds:{min:[supportExtent.min.x,supportExtent.min.z] as Vec2,max:[supportExtent.max.x,supportExtent.max.z] as Vec2};
    this.ground=new Ground({data:{...city.data,bounds},geometryMap:city.geometryMap});
    this.maximumGroundHeight=maximumGroundHeight+.05;
    let colliderCount=0;
    for(const instance of city.data.instances){
      const box=boxes.get(instance.prototype);if(!box)continue;
      const scale=new Vector3(...instance.scale),a=box.min.clone().multiply(scale),b=box.max.clone().multiply(scale);
      const min=a.clone().min(b),max=a.clone().max(b),[x,y,z]=instance.position,c=Math.cos(instance.rotation),s=Math.sin(instance.rotation);
      const solid:Solid={id:instance.id,prototype:instance.prototype,x,y,z,c,s,min,max};
      const cx=(min.x+max.x)*.5,cz=(min.z+max.z)*.5,hx=(max.x-min.x)*.5,hz=(max.z-min.z)*.5;
      const worldX=x+c*cx+s*cz,worldZ=z-s*cx+c*cz,extentX=Math.abs(c)*hx+Math.abs(s)*hz,extentZ=Math.abs(s)*hx+Math.abs(c)*hz;
      for(let ix=Math.floor((worldX-extentX)/this.cellSize);ix<=Math.floor((worldX+extentX)/this.cellSize);ix++){
        for(let iz=Math.floor((worldZ-extentZ)/this.cellSize);iz<=Math.floor((worldZ+extentZ)/this.cellSize);iz++){
          const key=`${ix},${iz}`;let cell=this.cells.get(key);if(!cell){cell=[];this.cells.set(key,cell);}cell.push(solid);
        }
      }
      colliderCount++;
    }
    this.colliderCount=colliderCount;
  }

  sampleGround=(x:number,z:number):number=>this.ground.heightAt(x,z)??0;

  private isWater(x:number,z:number):boolean{
    const contains=(area:WaterArea)=>x>=area.minX&&x<=area.maxX&&z>=area.minZ&&z<=area.maxZ&&inPolygon(x,z,area.points);
    return this.waters.some(contains)&&!this.islands.some(contains);
  }

  check(previous:FlightPose,current:FlightState):FlightHit|null{
    this.candidates.clear();
    const minX=Math.floor((Math.min(previous.position.x,current.position.x)-8)/this.cellSize),maxX=Math.floor((Math.max(previous.position.x,current.position.x)+8)/this.cellSize);
    const minZ=Math.floor((Math.min(previous.position.z,current.position.z)-8)/this.cellSize),maxZ=Math.floor((Math.max(previous.position.z,current.position.z)+8)/this.cellSize);
    for(let x=minX;x<=maxX;x++)for(let z=minZ;z<=maxZ;z++)for(const solid of this.cells.get(`${x},${z}`)??[])this.candidates.add(solid);
    for(const probe of PROBES){
      const a=worldProbe(probe,previous,this.start),b=worldProbe(probe,current,this.end),radius=probe[3];
      for(const solid of this.candidates)if(sweptBox(a,b,radius,solid))return {reason:'obstacle',id:solid.id,prototype:solid.prototype};
      // Ground is flat across most blocks, but interpolation also checks raised banks/decks.
      const steps=Math.max(1,Math.ceil(a.distanceTo(b)/.65));
      for(let i=0;i<=steps;i++){
        const t=i/steps,x=a.x+(b.x-a.x)*t,z=a.z+(b.z-a.z)*t,bottom=a.y+(b.y-a.y)*t-radius;
        if(bottom>this.maximumGroundHeight)continue;
        const ground=this.ground.heightAt(x,z);
        if(ground===null){if(bottom<=.02&&this.isWater(x,z))return {reason:'water',id:'water'};}
        else if(!probe[4]&&bottom<ground-.045)return {reason:'terrain',id:'terrain'};
      }
    }
    return null;
  }
}
