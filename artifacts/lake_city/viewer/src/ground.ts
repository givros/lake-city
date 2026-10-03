import type {LoadedCity} from './scene';
import type {Vec2} from './types';

type GroundInput=Pick<LoadedCity,'data'|'geometryMap'>;
type Bounds=[number,number,number,number];
interface Triangle {x:number;z:number;y:number;ux:number;uz:number;uy:number;vx:number;vz:number;vy:number;inverse:number;deck:boolean}
interface Polygon {points:Vec2[];bounds:Bounds}
const EPSILON=1e-6;

function polygon(points:Vec2[]):Polygon {
  let minX=Infinity,minZ=Infinity,maxX=-Infinity,maxZ=-Infinity;
  for(const [x,z] of points){minX=Math.min(minX,x);minZ=Math.min(minZ,z);maxX=Math.max(maxX,x);maxZ=Math.max(maxZ,z);}
  return {points,bounds:[minX,minZ,maxX,maxZ]};
}
function inBounds(x:number,z:number,b:Bounds){return x>=b[0]-EPSILON&&z>=b[1]-EPSILON&&x<=b[2]+EPSILON&&z<=b[3]+EPSILON;}
function contains(x:number,z:number,p:Polygon):boolean {
  if(!inBounds(x,z,p.bounds))return false;
  let inside=false;
  for(let i=0,j=p.points.length-1;i<p.points.length;j=i++){
    const a=p.points[i],b=p.points[j];
    if((a[1]>z)!==(b[1]>z)&&x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0])inside=!inside;
  }
  return inside;
}

/** Exact CPU support queries over the already loaded city meshes. No extra fetches. */
export class Ground {
  private readonly triangles:Triangle[]=[];
  private readonly cells=new Map<number,number[]>();
  private readonly waters:Polygon[];
  private readonly holes:Polygon[];
  private readonly supportBounds:Bounds[];
  private readonly bounds:Bounds;
  private readonly minCellX:number;
  private readonly minCellZ:number;
  private readonly columns:number;
  readonly cellSize=32;
  readonly stepHeight=.45;
  readonly stats:{triangles:number;cells:number;references:number;maximumCellTriangles:number};

  constructor(city:GroundInput){
    const data=city.data;
    this.bounds=[data.bounds.min[0],data.bounds.min[1],data.bounds.max[0],data.bounds.max[1]];
    this.minCellX=Math.floor(this.bounds[0]/this.cellSize);
    this.minCellZ=Math.floor(this.bounds[1]/this.cellSize);
    const maxCellX=Math.floor(this.bounds[2]/this.cellSize),maxCellZ=Math.floor(this.bounds[3]/this.cellSize);
    this.columns=maxCellX-this.minCellX+1;
    this.waters=data.waterPolygons.map(polygon);
    this.holes=(data.waterHolePolygons??[]).map(polygon);
    this.supportBounds=(data.walkSurfaces??[]).map(s=>s.bounds);
    const maximumDeckHeight=Math.max(.5,...(data.walkSurfaces??[]).map(s=>s.height))+.005;
    let references=0;
    for(const instance of data.instances){
      const surface=instance.prototype.startsWith('surfaces_');
      const deck=!surface&&/^(?:pond_bridge_|pond_walk_|marina_(?:spine|finger_|shore_approach)|dock_module$)/.test(instance.prototype);
      if(!surface&&!deck)continue;
      const prototype=data.prototypes[instance.prototype],geometries=city.geometryMap.get(instance.prototype);
      if(!prototype||!geometries)continue;
      const c=Math.cos(instance.rotation),s=Math.sin(instance.rotation);
      const [px,py,pz]=instance.position,[sx,sy,sz]=instance.scale;
      for(let part=0;part<geometries.length;part++){
        const material=prototype.meshes[part].material;
        // Water, railings, mooring posts and every building/prop prototype are excluded.
        if(/water/i.test(material)||(deck&&!/wood/i.test(material)))continue;
        const geometry=geometries[part],position=geometry.getAttribute('position'),index=geometry.index;
        const count=index?index.count:position.count;
        const point=(i:number)=>{
          const k=index?index.getX(i):i,x=position.getX(k)*sx,z=position.getZ(k)*sz;
          return [px+c*x+s*z,py+position.getY(k)*sy,pz-s*x+c*z];
        };
        for(let k=0;k+2<count;k+=3){
          const a=point(k),b=point(k+1),d=point(k+2);
          if(![...a,...b,...d].every(Number.isFinite))continue;
          const ux=b[0]-a[0],uz=b[2]-a[2],uy=b[1]-a[1],vx=d[0]-a[0],vz=d[2]-a[2],vy=d[1]-a[1];
          const determinant=ux*vz-uz*vx;
          if(Math.abs(determinant)<1e-10)continue;
          // Reject side walls and steep faces. Surface ramps remain sampleable.
          const nx=uy*vz-uz*vy,nz=ux*vy-uy*vx;
          if(Math.abs(determinant)/Math.hypot(nx,determinant,nz)<.7)continue;
          if(deck&&(Math.max(a[1],b[1],d[1])>maximumDeckHeight||Math.max(a[1],b[1],d[1])-Math.min(a[1],b[1],d[1])>.03))continue;
          const minX=Math.max(this.bounds[0],Math.min(a[0],b[0],d[0])),maxX=Math.min(this.bounds[2],Math.max(a[0],b[0],d[0]));
          const minZ=Math.max(this.bounds[1],Math.min(a[2],b[2],d[2])),maxZ=Math.min(this.bounds[3],Math.max(a[2],b[2],d[2]));
          if(minX>maxX||minZ>maxZ)continue;
          const id=this.triangles.length;
          this.triangles.push({x:a[0],z:a[2],y:a[1],ux,uz,uy,vx,vz,vy,inverse:1/determinant,deck:deck||material==='connection_deck_base'});
          const cx0=Math.max(this.minCellX,Math.floor((minX-EPSILON)/this.cellSize));
          const cz0=Math.max(this.minCellZ,Math.floor((minZ-EPSILON)/this.cellSize));
          for(let x=cx0;x<=Math.min(maxCellX,Math.floor((maxX+EPSILON)/this.cellSize));x++){
            for(let z=cz0;z<=Math.min(maxCellZ,Math.floor((maxZ+EPSILON)/this.cellSize));z++){
              const key=this.key(x,z);let cell=this.cells.get(key);
              if(!cell){cell=[];this.cells.set(key,cell);}cell.push(id);references++;
            }
          }
        }
      }
    }
    let maximumCellTriangles=0;
    for(const cell of this.cells.values())maximumCellTriangles=Math.max(maximumCellTriangles,cell.length);
    this.stats={triangles:this.triangles.length,cells:this.cells.size,references,maximumCellTriangles};
  }

  private key(x:number,z:number){return x-this.minCellX+(z-this.minCellZ)*this.columns;}

  /** Return a real top surface, or null for water, out-of-bounds or unsupported space. */
  heightAt(x:number,z:number,previousHeight?:number):number|null {
    if(!Number.isFinite(x)||!Number.isFinite(z)||!inBounds(x,z,this.bounds))return null;
    const water=this.waters.some(p=>contains(x,z,p))&&!this.holes.some(p=>contains(x,z,p));
    const explicitSupport=water&&this.supportBounds.some(b=>inBounds(x,z,b));
    const ceiling=previousHeight!==undefined&&Number.isFinite(previousHeight)?previousHeight+this.stepHeight:Infinity;
    let height=-Infinity;
    for(const id of this.cells.get(this.key(Math.floor(x/this.cellSize),Math.floor(z/this.cellSize)))??[]){
      const t=this.triangles[id];
      if(water&&!t.deck&&!explicitSupport)continue;
      const dx=x-t.x,dz=z-t.z;
      const u=(dx*t.vz-dz*t.vx)*t.inverse,v=(t.ux*dz-t.uz*dx)*t.inverse;
      if(u<-EPSILON||v<-EPSILON||u+v>1+EPSILON)continue;
      const y=t.y+u*t.uy+v*t.vy;
      if(y<=ceiling+EPSILON&&y>height)height=y;
    }
    return Number.isFinite(height)?height:null;
  }

  at(x:number,z:number,previousHeight?:number){return this.heightAt(x,z,previousHeight);}
}
