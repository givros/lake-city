import * as THREE from 'three/webgpu';
import type {CityData} from './types';
import type {TrafficSimulation} from './traffic';

/** Switch the authored signal lenses with the same phases used by drivers. */
export class TrafficSignals {
  readonly root=new THREE.Group();
  private mesh:THREE.InstancedMesh;
  private linked:{junction:string;axis:'NS'|'EW'}[]=[];
  private signature='';
  private colors=['#4edb81','#ffc35c','#f34537'].map(c=>new THREE.Color(c));
  constructor(data:CityData,private simulation:TrafficSimulation){
    const lights=data.instances.filter(i=>i.prototype==='traffic_light');
    const geometry=new THREE.CircleGeometry(.101,12);
    const material=new THREE.MeshBasicNodeMaterial({color:0xffffff});
    this.mesh=new THREE.InstancedMesh(geometry,material,lights.length*3);
    this.mesh.name='ActiveTrafficSignalLenses';
    this.mesh.layers.enable(1);
    const placement=new THREE.Matrix4(),lens=new THREE.Matrix4(),orientation=new THREE.Quaternion();
    const up=new THREE.Vector3(0,1,0),color=new THREE.Color();
    for(const [i,light] of lights.entries()){
      const junction=[...simulation.network.junctions].sort((a,b)=>Math.hypot(a.position[0]-light.position[0],a.position[2]-light.position[2])-Math.hypot(b.position[0]-light.position[0],b.position[2]-light.position[2]))[0];
      const distance=junction?Math.hypot(junction.position[0]-light.position[0],junction.position[2]-light.position[2]):Infinity;
      this.linked.push({junction:distance<38?junction.id:'',axis:Math.abs(Math.sin(light.rotation))>.707?'EW':'NS'});
      orientation.setFromAxisAngle(up,light.rotation);
      placement.compose(new THREE.Vector3(...light.position),orientation,new THREE.Vector3(...light.scale));
      for(let lamp=0;lamp<3;lamp++){
        // Original lens front is local Z=.253; this stays clear of its surface.
        lens.makeTranslation(0,2.80+lamp*.30,.258);
        this.mesh.setMatrixAt(i*3+lamp,new THREE.Matrix4().multiplyMatrices(placement,lens));
        this.mesh.setColorAt(i*3+lamp,color.copy(this.colors[lamp]).multiplyScalar(.055));
      }
    }
    this.mesh.instanceMatrix.needsUpdate=true;
    this.mesh.computeBoundingBox();this.mesh.computeBoundingSphere();
    this.root.name='CityTrafficSignals';this.root.add(this.mesh);this.update();
  }
  update(){
    const states=this.linked.map(link=>{
      const state=this.simulation.junctionState(link.junction);
      if(!state)return 2;
      if(state.control!=='signal')return 1;
      return state.phase===link.axis?0:state.phase===link.axis+'_amber'?1:2;
    });
    const signature=states.join(',');if(signature===this.signature)return false;this.signature=signature;
    const color=new THREE.Color();
    states.forEach((active,i)=>{for(let lamp=0;lamp<3;lamp++)this.mesh.setColorAt(i*3+lamp,color.copy(this.colors[lamp]).multiplyScalar(lamp===active?2.4:.055));});
    if(this.mesh.instanceColor)this.mesh.instanceColor.needsUpdate=true;
    return true;
  }
  stats(){return {heads:this.linked.length,linkedToJunctions:this.linked.filter(x=>x.junction).length,states:this.signature};}
  dispose(){this.mesh.geometry.dispose();(this.mesh.material as THREE.Material).dispose();this.mesh.dispose();this.root.removeFromParent();}
}
