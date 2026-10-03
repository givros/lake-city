import * as THREE from 'three/webgpu';
import {assetUrl} from './assets';

import {color,materialColor,positionWorld,mx_noise_float,mix,normalWorld,cameraPosition,float,reflector} from 'three/tsl';

import type {CityData,Instance,MaterialData,MeshData} from './types';
import {VEHICLE_PROTOTYPES} from './types';



export interface LoadedCity {data:CityData;root:THREE.Group;promotedVehicles:Instance[];auditPromotions:()=>Record<string,unknown>;geometryMap:Map<string,THREE.BufferGeometry[]>;materialMap:Map<string,THREE.Material>;inventory:{prototypeTriangles:number;instancedTriangles:number;instances:number;meshBatches:number;geometryBytes:number;fixedVisibleInstances:number;promotedVehicleInstances:number;fixedVisibleTriangles:number;promotedVehicleTriangles:number};transferAudit:{passed:boolean;attributeFloatsCompared:number;indicesCompared:number;matrixFloatsCompared:number};geometries:THREE.BufferGeometry[];materials:THREE.Material[];reflectors:ReturnType<typeof reflector>[];renderReflections:(renderer:THREE.WebGPURenderer,camera:THREE.Camera)=>void}

const matrix=new THREE.Matrix4(),rotation=new THREE.Quaternion(),axis=new THREE.Vector3(0,1,0),position=new THREE.Vector3(),scale=new THREE.Vector3();

export async function loadCity(scene:THREE.Scene,progress:(message:string)=>void):Promise<LoadedCity>{

  progress('Reading the city plan…');

  const response=await fetch(assetUrl('city.json'));if(!response.ok)throw new Error('The city data could not be loaded.');

  const data:CityData=await response.json();
  const promotedVehicles=data.instances.filter(i=>VEHICLE_PROTOTYPES.has(i.prototype)),promotedIds=new Set(promotedVehicles.map(i=>i.id));
  const retiredDraws:{mesh:THREE.BatchedMesh;index:number;id:string}[]=[];

  progress('Loading architecture & landscape…');

  const geoResponse=await fetch(assetUrl('geometry.bin'));if(!geoResponse.ok)throw new Error('The city geometry could not be loaded.');

  const binary=await geoResponse.arrayBuffer();

  const isWaterMaterial=(name:string)=>/water|lake_surface|pond_surface/i.test(name);

  const waterPlane=(instance:Instance,mesh:MeshData)=>instance.position[1]+new Float32Array(binary,mesh.positionOffset,mesh.positionCount)[1]*instance.scale[1];

  const materialKey=(instance:Instance,mesh:MeshData)=>isWaterMaterial(mesh.material)?`${mesh.material}@${waterPlane(instance,mesh)}`:mesh.material;

  const root=new THREE.Group();root.name='LakeCity';root.matrixAutoUpdate=false;

  const materials:THREE.Material[]=[],reflectors:ReturnType<typeof reflector>[]=[];

  const reflectionPasses:{key:string;material:THREE.Material;update:(frame:any)=>void;mesh?:THREE.BatchedMesh}[]=[];

  const materialMap=new Map<string,THREE.Material>();

  const makeSurfaceNode=(size:number,strength:number)=>materialColor.mul(mx_noise_float(positionWorld.mul(size)).mul(strength).add(1));

  const surfaceNodes=new Map<string,ReturnType<typeof makeSurfaceNode>>();

  for(const [name,record] of Object.entries(data.materials)){

    const values=typeof record==='string'?{color:record}:record as MaterialData;

    const mat=new THREE.MeshStandardNodeMaterial({color:values.color,roughness:values.roughness??.82,metalness:values.metalness??0});

    mat.name=name;

    const isWater=isWaterMaterial(name);

    if(isWater){

      const planes=new Map<string,number>();

      for(const instance of data.instances)for(const mesh of data.prototypes[instance.prototype].meshes)if(mesh.material===name)planes.set(materialKey(instance,mesh),waterPlane(instance,mesh));

      for(const [key,height] of planes){

      const reflection=reflector({resolutionScale:1,bounces:false,generateMipmaps:false,samples:4});

      // Reflection captures are submitted in full before the beauty pass.

      // A nested capture can otherwise replace the indirect instance-ID texture

      // used by already encoded BatchedMesh draws in the outer pass.

      const reflectionBase=reflection.reflector;

      const updateReflection=reflectionBase.updateBefore.bind(reflectionBase);

      reflectionBase.updateBefore=()=>false;

      reflection.target.rotation.x=-Math.PI/2;

      reflection.target.position.y=height;

      scene.add(reflection.target);reflectors.push(reflection);

      const fresnel=float(1).sub(normalWorld.dot(cameraPosition.sub(positionWorld).normalize()).abs()).pow(5).mul(.78).add(.04);

      const detail=mx_noise_float(positionWorld.mul(.18)).mul(.025).add(.975);

      const water=new THREE.MeshBasicNodeMaterial();

      water.name=key;water.colorNode=mix(color(values.color).mul(detail),reflection.rgb,fresnel);water.side=THREE.DoubleSide;

      materialMap.set(key,water);materials.push(water);

      reflectionPasses.push({key,material:water,update:updateReflection});

      }

      mat.dispose();continue;

    }

    if(/grass|meadow|lawn|soil|sand|asphalt|pav|concrete|stone|bark/i.test(name)){

      const size=/grass|meadow|lawn/i.test(name)?.65:/asphalt/i.test(name)?7:3.5;

      const strength=/grass|meadow|lawn/i.test(name)?.10:.035;

      const key=`${size}:${strength}`;

      if(!surfaceNodes.has(key))surfaceNodes.set(key,makeSurfaceNode(size,strength));

      mat.colorNode=surfaceNodes.get(key)!;

    }

    if(/leaf|foliage|canopy/i.test(name))mat.side=THREE.DoubleSide;

    materialMap.set(name,mat);materials.push(mat);

  }

  const geometryMap=new Map<string,THREE.BufferGeometry[]>(),geometries:THREE.BufferGeometry[]=[];

  let prototypeTriangles=0;

  for(const [name,prototype] of Object.entries(data.prototypes)){

    const meshes=prototype.meshes.map(mesh=>{

      const geometry=new THREE.BufferGeometry();

      const positions=new Float32Array(binary,mesh.positionOffset,mesh.positionCount),normals=new Float32Array(binary,mesh.normalOffset,mesh.positionCount),indices=new Uint32Array(binary,mesh.indexOffset,mesh.indexCount);

      geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.setAttribute('normal',new THREE.BufferAttribute(normals,3));geometry.setIndex(new THREE.BufferAttribute(indices,1));

      geometry.computeBoundingBox();geometry.computeBoundingSphere();prototypeTriangles+=mesh.indexCount/3;geometries.push(geometry);return geometry;

    });geometryMap.set(name,meshes);

  }

  const batches=new Map<string,{instances:{instance:Instance;geometry:THREE.BufferGeometry}[];geometries:Set<THREE.BufferGeometry>}>();let instancedTriangles=0;

  for(const instance of data.instances){

    data.prototypes[instance.prototype].meshes.forEach((mesh,part)=>{

      const key=materialKey(instance,mesh),geometry=geometryMap.get(instance.prototype)![part];

      if(!batches.has(key))batches.set(key,{instances:[],geometries:new Set()});

      const batch=batches.get(key)!;batch.instances.push({instance,geometry});batch.geometries.add(geometry);instancedTriangles+=mesh.indexCount/3;

    });

  }

  progress('Placing the city’s neighborhoods…');

  const transferAudit={passed:true,attributeFloatsCompared:0,indicesCompared:0,matrixFloatsCompared:0};

  const checkedMatrix=new THREE.Matrix4();

  for(const [key,batch] of batches){

    let vertices=0,indices=0;

    for(const geometry of batch.geometries){vertices+=geometry.getAttribute('position').count;indices+=geometry.index!.count;}

    const mesh=new THREE.BatchedMesh(batch.instances.length,vertices,indices,materialMap.get(key));

    mesh.name=key;mesh.sortObjects=false;mesh.perObjectFrustumCulled=true;

    const geometryIds=new Map<THREE.BufferGeometry,number>();

    for(const geometry of batch.geometries){

      const geometryId=mesh.addGeometry(geometry);geometryIds.set(geometry,geometryId);

      const range=mesh.getGeometryRangeAt(geometryId)!;

      for(const attribute of ['position','normal']){

        const before=geometry.getAttribute(attribute).array,after=mesh.geometry.getAttribute(attribute).array;

        for(let i=0;i<before.length;i++){transferAudit.attributeFloatsCompared++;if(before[i]!==after[range.vertexStart*3+i])transferAudit.passed=false;}

      }

      const before=geometry.index!.array,after=mesh.geometry.index!.array;

      for(let i=0;i<before.length;i++){transferAudit.indicesCompared++;if(before[i]+range.vertexStart!==after[range.indexStart+i])transferAudit.passed=false;}

    }

    if(!(mesh.geometry.index!.array instanceof Uint32Array))mesh.geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(mesh.geometry.index!.array),1));

    const sourceIds:string[]=[];

    for(const entry of batch.instances){

      const {instance,geometry}=entry;

      const index=mesh.addInstance(geometryIds.get(geometry)!);

      rotation.setFromAxisAngle(axis,instance.rotation);position.fromArray(instance.position);scale.fromArray(instance.scale);matrix.compose(position,rotation,scale);

      mesh.setMatrixAt(index,matrix);sourceIds[index]=instance.id;
      if(promotedIds.has(instance.id)){mesh.setVisibleAt(index,false);retiredDraws.push({mesh,index,id:instance.id});}

      mesh.getMatrixAt(index,checkedMatrix);

      for(let i=0;i<16;i++){transferAudit.matrixFloatsCompared++;if(Math.fround(matrix.elements[i])!==checkedMatrix.elements[i])transferAudit.passed=false;}

    }

    mesh.userData.sourceInstances=sourceIds;

    mesh.layers.enable(2);mesh.matrixAutoUpdate=false;mesh.castShadow=!/water/i.test(key);mesh.receiveShadow=true;

    mesh.computeBoundingBox();mesh.computeBoundingSphere();root.add(mesh);

    const reflectionPass=reflectionPasses.find(pass=>pass.key===key);if(reflectionPass)reflectionPass.mesh=mesh;

  }

  if(!transferAudit.passed)throw new Error('The city geometry transfer failed its precision check.');

  scene.add(root);root.updateMatrixWorld(true);

  const reflectionFrustum=new THREE.Frustum(),viewProjection=new THREE.Matrix4();

  const renderReflections=(renderer:THREE.WebGPURenderer,camera:THREE.Camera)=>{

    viewProjection.multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse);

    reflectionFrustum.setFromProjectionMatrix(viewProjection,camera.coordinateSystem,camera.reversedDepth);

    for(const pass of reflectionPasses)if(pass.mesh&&reflectionFrustum.intersectsObject(pass.mesh))pass.update({renderer,scene,camera,material:pass.material});

  };

  const promotedVehicleTriangles=promotedVehicles.reduce((sum,i)=>sum+data.prototypes[i.prototype].meshes.reduce((n,m)=>n+m.indexCount/3,0),0);
  const auditPromotions=()=>({sourceVehicleIds:[...promotedIds],promotedSourceCount:promotedVehicles.length,retiredFixedParts:retiredDraws.length,remainingVisibleFixedParts:retiredDraws.filter(r=>r.mesh.getVisibleAt(r.index)).map(r=>r.id),geometryPolicy:'Original source geometry and matrices retained for exact transfer audit; authored fixed draw entries disabled in every camera pass and replaced one-to-one by moving actors'});
  return {data,root,promotedVehicles,auditPromotions,geometryMap,materialMap,inventory:{prototypeTriangles,instancedTriangles,instances:data.instances.length,meshBatches:root.children.length,geometryBytes:binary.byteLength,fixedVisibleInstances:data.instances.length-promotedVehicles.length,promotedVehicleInstances:promotedVehicles.length,fixedVisibleTriangles:instancedTriangles-promotedVehicleTriangles,promotedVehicleTriangles},transferAudit,geometries,materials,reflectors,renderReflections};

}

