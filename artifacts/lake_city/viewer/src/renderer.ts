import * as THREE from 'three/webgpu';

import {shadow} from 'three/tsl';

export interface RendererBundle {renderer:THREE.WebGPURenderer;scene:THREE.Scene;sun:THREE.DirectionalLight;adapter:GPUAdapter;device:GPUDevice;environment:THREE.Texture;fitSun:(position:THREE.Vector3,walking:boolean)=>void;renderSun:(camera:THREE.Camera,revision?:number)=>void;shadowStats:()=>Record<string,unknown>;auditShadow:(camera:THREE.Camera)=>Promise<Record<string,unknown>>;dispose:()=>void;backendInfo:Record<string,unknown>}

export async function createRenderer(canvas:HTMLCanvasElement,fatal:(message:string)=>void):Promise<RendererBundle>{

  if(!isSecureContext||!navigator.gpu)throw new Error('This city needs WebGPU. Open the local address in a recent desktop Chrome or Edge browser with hardware acceleration enabled.');

  const adapter=await navigator.gpu.requestAdapter({powerPreference:'high-performance'});

  if(!adapter)throw new Error('A WebGPU graphics adapter is unavailable. Enable hardware acceleration in your desktop browser and reload.');

  const features:GPUFeatureName[]=[];

  for(const name of ['float32-filterable','core-features-and-limits'] as GPUFeatureName[])if(adapter.features.has(name))features.push(name);

  const device=await adapter.requestDevice({requiredFeatures:features});

  const renderer=new THREE.WebGPURenderer({canvas,antialias:true,alpha:false,device,powerPreference:'high-performance',logarithmicDepthBuffer:true});

  await renderer.init();

  const backend=renderer.backend as unknown as {isWebGPUBackend:boolean;device:GPUDevice};

  if(!backend.isWebGPUBackend||backend.device!==device)throw new Error('The city did not initialize with its required WebGPU backend.');

  let disposed=false;

  renderer.onDeviceLost=info=>{if(!disposed)fatal(`The graphics device was disconnected. ${info.message??''} Reload to rebuild the city.`);};

  device.addEventListener('uncapturederror',event=>{if(!disposed)fatal(`A graphics error interrupted the city: ${event.error.message}`);});

  renderer.setPixelRatio(window.devicePixelRatio);renderer.setSize(innerWidth,innerHeight);

  renderer.info.autoReset=false;

  renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.1;renderer.outputColorSpace=THREE.SRGBColorSpace;

  renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFShadowMap;

  const scene=new THREE.Scene();scene.matrixWorldAutoUpdate=false;scene.background=new THREE.Color('#b8d3df');

  scene.fog=new THREE.Fog('#bdd4db',3400,9000);

  const width=512,height=256,pixels=new Float32Array(width*height*4);

  const zenith=new THREE.Color('#8fbbd7'),horizon=new THREE.Color('#e4eee8'),ground=new THREE.Color('#728071');

  for(let y=0;y<height;y++){

    const latitude=Math.cos(y/(height-1)*Math.PI),c=latitude>=0?horizon.clone().lerp(zenith,Math.pow(latitude,.55)):horizon.clone().lerp(ground,Math.pow(-latitude,.3));

    for(let x=0;x<width;x++){const i=(y*width+x)*4;pixels[i]=c.r;pixels[i+1]=c.g;pixels[i+2]=c.b;pixels[i+3]=1;}

  }

  const sky=new THREE.DataTexture(pixels,width,height,THREE.RGBAFormat,THREE.FloatType);sky.mapping=THREE.EquirectangularReflectionMapping;sky.needsUpdate=true;

  const generator=new THREE.PMREMGenerator(renderer);const env=generator.fromEquirectangular(sky);scene.environment=env.texture;scene.environmentIntensity=.55;

  generator.dispose();sky.dispose();

  const sun=new THREE.DirectionalLight('#fff4dd',3.15);sun.position.set(-1000,1600,800);sun.castShadow=true;

  sun.shadow.mapSize.set(4096,4096);sun.shadow.bias=-.00006;sun.shadow.normalBias=.25;

  sun.shadow.camera.near=1;sun.shadow.camera.far=5200;sun.shadow.autoUpdate=false;

  scene.add(sun,sun.target);

  // Submit shadows before a beauty/reflection encoder starts. Nested passes

  // otherwise overwrite BatchedMesh's camera-specific indirect instance IDs.

  const dynamicShadow=sun.shadow.clone();

  sun.shadow.camera.layers.set(2);dynamicShadow.camera.layers.set(1);

  const sunNode:any=shadow(sun),actorNode:any=shadow(sun,dynamicShadow);

  for(const node of [sunNode,actorNode]){const setup=node.setupRenderTarget.bind(node);node.setupRenderTarget=(...args:any[])=>{const target=setup(...args as [any,any]);target.depthTexture.type=THREE.FloatType;return target;};}

  const drawActors=actorNode.renderShadow.bind(actorNode);

  actorNode.renderShadow=(frame:any)=>{

    // Copy cached nearest static depth, then depth-test full-detail moving actors

    // into the same map. Filtering the union keeps overlapping PCF edges exact.

    renderer.initRenderTarget(dynamicShadow.map!);

    renderer.copyTextureToTexture(sun.shadow.map!.depthTexture!,dynamicShadow.map!.depthTexture!);

    const clearDepth=renderer.autoClearDepth;try{renderer.autoClearDepth=false;drawActors(frame);}finally{renderer.autoClearDepth=clearDepth;}

  };

  const updateSun=sunNode.updateBefore.bind(sunNode),updateActors=actorNode.updateBefore.bind(actorNode);

  const setupCombined=actorNode.setupShadow.bind(actorNode);
  actorNode.setupShadow=(builder:any)=>{
    // The static cache is a depth source only. Lighting samples the complete
    // union once, without a redundant second set of PCF texture lookups.
    if(!sunNode.shadowMap){const cache=sunNode.setupRenderTarget(sun.shadow,builder);sunNode.shadowMap=cache.shadowMap;sun.shadow.map=cache.shadowMap;sun.shadow.camera.coordinateSystem=builder.camera.coordinateSystem;sun.shadow.camera.updateProjectionMatrix();}
    return setupCombined(builder);
  };
  sun.shadow.shadowNode=actorNode;sunNode.updateBefore=()=>{};actorNode.updateBefore=()=>{};

  let shadowFrame=0,lastRevision=-1,staticPasses=0,dynamicPasses=0;

  const renderSun=(camera:THREE.Camera,revision=0)=>{

    if(sun.shadow.needsUpdate){updateSun({renderer,scene,camera,frameId:++shadowFrame} as any);staticPasses++;dynamicShadow.needsUpdate=true;}

    if(dynamicShadow.needsUpdate||revision!==lastRevision){dynamicShadow.needsUpdate=true;updateActors({renderer,scene,camera,frameId:++shadowFrame} as any);dynamicPasses++;lastRevision=revision;}

  };

  const shadowStats=()=>({staticPasses,dynamicPasses,lastRevision,resolution:[4096,4096],staticLayer:2,dynamicLayer:1,staticMapId:sun.shadow.map?.texture.id,dynamicMapId:dynamicShadow.map?.texture.id,combination:'copy cached static depth32float, draw dynamic nearest depth, standard PCF of union'});

  const readDepth=async(texture:THREE.DepthTexture)=>{
    const width=texture.image.width!,height=texture.image.height!,size=width*height*4;
    const buffer=device.createBuffer({size,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});
    const encoder=device.createCommandEncoder();encoder.copyTextureToBuffer({texture:(renderer.backend as any).get(texture).texture,aspect:'depth-only'},{buffer,bytesPerRow:width*4,rowsPerImage:height},{width,height,depthOrArrayLayers:1});device.queue.submit([encoder.finish()]);await buffer.mapAsync(GPUMapMode.READ);const values=new Uint32Array(buffer.getMappedRange()).slice();buffer.unmap();buffer.destroy();return values;
  };
  const hash=(values:Uint32Array)=>{let result=2166136261;for(const value of values)result=Math.imul(result^value,16777619);return (result>>>0).toString(16);};
  const auditShadow=async(camera:THREE.Camera)=>{
    const cached=await readDepth(sun.shadow.map!.depthTexture!),combined=await readDepth(dynamicShadow.map!.depthTexture!);
    const draw=actorNode.renderShadow;actorNode.renderShadow=drawActors;dynamicShadow.camera.layers.set(0);dynamicShadow.needsUpdate=true;
    updateActors({renderer,scene,camera,frameId:++shadowFrame});
    const reference=await readDepth(dynamicShadow.map!.depthTexture!);let different=0;for(let i=0;i<combined.length;i++)if(combined[i]!==reference[i])different++;
    actorNode.renderShadow=draw;dynamicShadow.camera.layers.set(1);dynamicShadow.needsUpdate=true;
    const cachedAfter=await readDepth(sun.shadow.map!.depthTexture!);
    return {texels:combined.length,differentTexelsFromFullScene:different,staticHash:hash(cached),staticHashAfter:hash(cachedAfter),combinedHash:hash(combined),referenceHash:hash(reference),passed:different===0&&hash(cached)===hash(cachedAfter)};
  };
  const lightDirection=new THREE.Vector3(-.52,1,.38).normalize();let lastFit='';

  const fitSun=(target:THREE.Vector3,walking:boolean)=>{

    const extent=walking?230:1650;

    const center=walking?new THREE.Vector3(Math.round(target.x/32)*32,0,Math.round(target.z/32)*32):new THREE.Vector3();

    const key=`${extent}:${center.x}:${center.z}`;if(key===lastFit)return;lastFit=key;

    sun.target.position.copy(center);sun.position.copy(center).addScaledVector(lightDirection,2300);

    sun.shadow.camera.left=-extent;sun.shadow.camera.right=extent;sun.shadow.camera.top=extent;sun.shadow.camera.bottom=-extent;sun.shadow.camera.updateProjectionMatrix();sun.shadow.needsUpdate=true;

    dynamicShadow.camera.copy(sun.shadow.camera);dynamicShadow.camera.layers.set(1);dynamicShadow.needsUpdate=true;

    sun.updateMatrixWorld();sun.target.updateMatrixWorld();

  };fitSun(new THREE.Vector3(),false);

  const info=adapter.info;

  return {renderer,scene,sun,adapter,device,environment:env.texture,fitSun,renderSun,shadowStats,auditShadow,backendInfo:{name:'WebGPU',verifiedBackend:true,vendor:info.vendor,architecture:info.architecture,device:info.device,description:info.description,isFallbackAdapter:info.isFallbackAdapter,features:Array.from(device.features),limits:{maxTextureDimension2D:device.limits.maxTextureDimension2D,maxBufferSize:device.limits.maxBufferSize}},dispose(){disposed=true;env.dispose();sun.shadow.dispose();dynamicShadow.dispose();renderer.dispose();device.destroy();}};

}



