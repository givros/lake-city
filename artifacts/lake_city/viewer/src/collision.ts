import type {CityData,Vec2} from './types';
import {VEHICLE_PROTOTYPES} from './types';

interface Solid {x:number;z:number;hx:number;hz:number;c:number;s:number;id:string}
export const BODY = { radius:0.32, eye:1.72, height:1.78, step:0.45, speed:3.9, fastSpeed:11.5, ground:0.15 };
export function inPolygon(x:number,z:number,points:Vec2[]):boolean {
  let inside=false;
  for(let i=0,j=points.length-1;i<points.length;j=i++) {
    const [xi,zi]=points[i], [xj,zj]=points[j];
    if(((zi>z)!==(zj>z)) && x<(xj-xi)*(z-zi)/(zj-zi)+xi)inside=!inside;
  }
  return inside;
}
export class CityCollision {
  private cells = new Map<string,Solid[]>();
  readonly staticColliderIds=new Set<string>();
  readonly cellSize=48;
  private waterBounds:number[][]=[];private holeBounds:number[][]=[];
  constructor(readonly data:CityData){
    const bounds=(p:Vec2[])=>[Math.min(...p.map(v=>v[0])),Math.min(...p.map(v=>v[1])),Math.max(...p.map(v=>v[0])),Math.max(...p.map(v=>v[1]))];
    this.waterBounds=data.waterPolygons.map(bounds);this.holeBounds=(data.waterHolePolygons??[]).map(bounds);
    for(const instance of data.instances){
      if(VEHICLE_PROTOTYPES.has(instance.prototype))continue;
      const footprint=data.prototypes[instance.prototype]?.collision;
      if(!footprint)continue;
      this.staticColliderIds.add(instance.id);
      const c=Math.cos(instance.rotation),s=Math.sin(instance.rotation);
      const solid:Solid={x:instance.position[0],z:instance.position[2],hx:Math.abs(footprint[0]*instance.scale[0]),hz:Math.abs(footprint[1]*instance.scale[2]),c,s,id:instance.id};
      const bx=Math.abs(c)*solid.hx+Math.abs(s)*solid.hz+BODY.radius;
      const bz=Math.abs(s)*solid.hx+Math.abs(c)*solid.hz+BODY.radius;
      for(let x=Math.floor((solid.x-bx)/this.cellSize);x<=Math.floor((solid.x+bx)/this.cellSize);x++)for(let z=Math.floor((solid.z-bz)/this.cellSize);z<=Math.floor((solid.z+bz)/this.cellSize);z++) {
        const key=`${x},${z}`;if(!this.cells.has(key))this.cells.set(key,[]);this.cells.get(key)!.push(solid);
      }
    }
  }
  support(x:number,z:number,previousHeight=BODY.ground):number|null{
    let height=BODY.ground,hasDeck=false;
    for(const surface of this.data.walkSurfaces??[]){
      const [a,b,c,d]=surface.bounds;
      if(x>=a+BODY.radius&&x<=c-BODY.radius&&z>=b+BODY.radius&&z<=d-BODY.radius&&surface.height<=previousHeight+BODY.step){height=Math.max(height,surface.height);hasDeck=true;}
    }
    if(!hasDeck&&this.isWater(x,z))return null;
    return height;
  }
  isWater(x:number,z:number):boolean {
    const contains=(b:number[])=>x>=b[0]&&z>=b[1]&&x<=b[2]&&z<=b[3];
    if(this.data.waterHolePolygons?.some((p,i)=>contains(this.holeBounds[i])&&inPolygon(x,z,p)))return false;
    return this.data.waterPolygons.some((p,i)=>contains(this.waterBounds[i])&&inPolygon(x,z,p));
  }
  blocked(x:number,z:number,height=BODY.ground):string|null {
    const [minX,minZ]=this.data.bounds.min,[maxX,maxZ]=this.data.bounds.max;
    if(x<minX+BODY.radius||x>maxX-BODY.radius||z<minZ+BODY.radius||z>maxZ-BODY.radius)return 'map boundary';
    for(const [ox,oz] of [[0,0],[BODY.radius,0],[-BODY.radius,0],[0,BODY.radius],[0,-BODY.radius]])if(this.support(x+ox,z+oz,height)===null)return 'water';
    for(const solid of this.cells.get(`${Math.floor(x/this.cellSize)},${Math.floor(z/this.cellSize)}`)??[]){
      const dx=x-solid.x,dz=z-solid.z;
      const lx=solid.c*dx-solid.s*dz,lz=solid.s*dx+solid.c*dz;
      const qx=Math.max(Math.abs(lx)-solid.hx,0),qz=Math.max(Math.abs(lz)-solid.hz,0);
      if(qx*qx+qz*qz<BODY.radius*BODY.radius)return solid.id;
    }
    return null;
  }
  safePoint(x:number,z:number):[number,number,number] {
    for(let r=0;r<100;r+=r===0?2:3){
      const n=Math.max(1,Math.ceil(r*3));
      for(let i=0;i<n;i++){
        const a=i/n*Math.PI*2,px=x+Math.cos(a)*r,pz=z+Math.sin(a)*r;
        if(!this.blocked(px,pz))return [px,this.support(px,pz)??BODY.ground,pz];
      }
    }
    throw new Error('No accessible walking position near this destination.');
  }
  move(x:number,z:number,dx:number,dz:number,height:number):[number,number,number]{
    const length=Math.hypot(dx,dz),steps=Math.max(1,Math.ceil(length/.18));
    for(let i=0;i<steps;i++){
      const nx=x+dx/steps,nz=z+dz/steps;
      if(!this.blocked(nx,nz,height)){x=nx;z=nz;}
      else{if(!this.blocked(nx,z,height))x=nx;if(!this.blocked(x,nz,height))z=nz;}
      height=this.support(x,z,height)??height;
    }
    return [x,height,z];
  }
}
