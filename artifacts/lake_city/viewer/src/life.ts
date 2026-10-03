import * as THREE from 'three/webgpu';
import {assetUrl} from './assets';
import {TrafficSimulation,type TrafficNetwork} from './traffic';
import {TrafficSignals} from './traffic-signals';
import {Pedestrians} from './pedestrians';
import {CityCollision} from './collision';
import type {LoadedCity} from './scene';

export class CityLife {
  readonly root=new THREE.Group();readonly traffic:TrafficSimulation;readonly pedestrians:Pedestrians;readonly network:TrafficNetwork;readonly signals:TrafficSignals;
  paused=false;time=0;revision=0;private accumulator=0;
  private batches:{mesh:THREE.InstancedMesh;ids:number[]}[]=[];
  private vehicleSourceExact=true;private vehicleTriangles=0;
  private matrix=new THREE.Matrix4();private position=new THREE.Vector3();private quaternion=new THREE.Quaternion();private axis=new THREE.Vector3(0,1,0);private scale=new THREE.Vector3(1,1,1);
  static async create(city:LoadedCity,collision:CityCollision,scene:THREE.Scene){
    const response=await fetch(assetUrl('traffic_network.json'));if(!response.ok)throw new Error('The street traffic plan could not be loaded.');const network:TrafficNetwork=await response.json();
    if(network.sourceHash!==city.data.sourceHash)throw new Error('The traffic plan does not match this city.');
    const pedestrians=await Pedestrians.create(city,collision,network.roadCorridors,80);return new CityLife(city,network,pedestrians,scene);
  }
  private constructor(city:LoadedCity,network:TrafficNetwork,pedestrians:Pedestrians,scene:THREE.Scene){
    this.network=network;const fleet=city.promotedVehicles.map(i=>({id:i.id,prototype:i.prototype as 'car_sedan'|'car_suv'|'delivery_van',sourceInstanceId:i.id}));this.traffic=new TrafficSimulation(network,{count:fleet.length+84,fleet,seed:1937});this.pedestrians=pedestrians;this.signals=new TrafficSignals(city.data,this.traffic);this.root.add(this.signals.root);this.root.name='CityLife';this.root.add(pedestrians.root);scene.add(this.root);
    for(const prototype of ['car_sedan','car_suv','delivery_van']){const ids=this.traffic.actors.flatMap((a,i)=>a.prototype===prototype?[i]:[]);if(!ids.length)continue;
      for(const [part,geometry] of city.geometryMap.get(prototype)!.entries()){const materialName=city.data.prototypes[prototype].meshes[part].material,mesh=new THREE.InstancedMesh(geometry,city.materialMap.get(materialName),ids.length);mesh.name=`moving_${prototype}_${part}`;mesh.layers.enable(1);mesh.castShadow=true;mesh.receiveShadow=true;mesh.frustumCulled=false;mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);this.root.add(mesh);this.batches.push({mesh,ids});this.vehicleSourceExact=this.vehicleSourceExact&&mesh.geometry===geometry&&mesh.material===city.materialMap.get(materialName);this.vehicleTriangles+=(geometry.index?.count??0)/3*ids.length;}
    }
    this.sync();
  }
  private sync(){for(const batch of this.batches){for(let i=0;i<batch.ids.length;i++){const a=this.traffic.actors[batch.ids[i]];this.position.fromArray(a.position);this.quaternion.setFromAxisAngle(this.axis,a.rotation);this.matrix.compose(this.position,this.quaternion,this.scale);batch.mesh.setMatrixAt(i,this.matrix);}batch.mesh.instanceMatrix.needsUpdate=true;}this.signals.update();}
  update(elapsed:number){if(this.paused||document.hidden)return false;return this.step(Math.min(.25,Math.max(0,elapsed)));}
  setPaused(paused:boolean){this.paused=paused;this.accumulator=0;}
  step(elapsed:number){if(!Number.isFinite(elapsed)||elapsed<0||elapsed>60)throw new Error('Life step must be between0 and60 seconds.');this.accumulator+=elapsed;let steps=0;while(this.accumulator>=1/30-1e-9){this.traffic.update(1/30);this.pedestrians.update(1/30);this.time+=1/30;this.accumulator-=1/30;steps++;}if(steps){this.sync();this.revision++;}return steps>0;}
  auditVehicleTransforms(){let compared=0,mismatches=0;const stored=new THREE.Matrix4(),expected=new THREE.Matrix4();for(const batch of this.batches)for(let i=0;i<batch.ids.length;i++){const a=this.traffic.actors[batch.ids[i]];expected.compose(new THREE.Vector3(...a.position),new THREE.Quaternion().setFromAxisAngle(this.axis,a.rotation),this.scale);batch.mesh.getMatrixAt(i,stored);for(let k=0;k<16;k++){compared++;if(stored.elements[k]!==Math.fround(expected.elements[k]))mismatches++;}}return {compared,mismatches,passed:mismatches===0,parts:this.batches.length,actors:this.traffic.actors.length};}
  snapshot(){return {time:this.time,paused:this.paused,revision:this.revision,actors:[...this.traffic.actors.map(a=>({...a,type:'vehicle',yaw:a.rotation,scale:1,position:[...a.position]})),...this.pedestrians.snapshot()]};}
  stats(){return {time:this.time,paused:this.paused,revision:this.revision,traffic:this.traffic.stats(),pedestrians:this.pedestrians.stats(),vehicleMeshParts:this.batches.length,vehicles:this.traffic.actors.length,promotedSourceVehicles:this.traffic.actors.filter(a=>a.sourceInstanceId).length,additionalVehicles:this.traffic.actors.filter(a=>!a.sourceInstanceId).length,vehicleSourceExact:this.vehicleSourceExact,vehicleTriangles:this.vehicleTriangles,signals:this.signals.stats()};}
  dispose(){this.pedestrians.dispose();this.signals.dispose();for(const {mesh} of this.batches)mesh.dispose();this.root.removeFromParent();}
}

