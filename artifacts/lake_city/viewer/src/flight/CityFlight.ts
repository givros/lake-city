import * as THREE from 'three/webgpu';
import type {LoadedCity} from '../scene';
import {AirplaneModel} from './assets/AirplaneModel';
import {ManualFlightController} from './controller';
import {PilotInput} from './input';
import {PilotCamera} from './camera';
import {FlightCollision,type FlightPose} from './collision';
import {DEG,type Controls} from './types';

const NEUTRAL:Controls={throttle:0,pitch:0,roll:0,rudder:0,brake:false};
export type FlightStatus='inactive'|'flying'|'paused'|'crashed';

/** The source Cropper Seven aircraft and dynamics, integrated without altering city assets. */
export class CityFlight {
  readonly aircraft:AirplaneModel;
  readonly controller:ManualFlightController;
  readonly input:PilotInput;
  readonly collision:FlightCollision;
  readonly pilotCamera:PilotCamera;
  revision=0;
  private activeValue=false;
  private pausedValue=true;
  private crashReasonValue:string|null=null;
  private disposed=false;
  private readonly pose=new THREE.Euler(0,0,0,'YXZ');
  private readonly previous:FlightPose={position:new THREE.Vector3(),yaw:0,pitch:0,bank:0};

  constructor(city:LoadedCity,private readonly scene:THREE.Scene,camera:THREE.PerspectiveCamera,canvas:HTMLCanvasElement){
    this.collision=new FlightCollision(city);
    this.controller=new ManualFlightController(this.collision.sampleGround);
    this.input=new PilotInput(canvas);this.input.enabled=false;
    this.pilotCamera=new PilotCamera(camera);
    this.aircraft=new AirplaneModel();this.aircraft.root.name='Cropper Seven — Lake City';
    this.aircraft.root.visible=false;
    this.aircraft.root.traverse(object=>{if(object instanceof THREE.Mesh)object.layers.enable(1);});
    scene.add(this.aircraft.root);
    window.addEventListener('blur',this.onBlur);
    document.addEventListener('visibilitychange',this.onVisibility);
  }

  get active(){return this.activeValue;}
  get paused(){return this.pausedValue;}
  get crashed(){return this.controller.state.crashed;}
  get status():FlightStatus{return !this.active?'inactive':this.crashed?'crashed':this.paused?'paused':'flying';}

  start():void{if(this.disposed)return;this.activeValue=true;this.aircraft.root.visible=true;this.reset();}

  reset():void{
    if(this.disposed)return;
    this.controller.start();
    const state=this.controller.state;
    state.position.set(-560,240,250);state.yaw=Math.PI/2;state.pitch=2.4*DEG;
    state.speed=45;state.throttle=.72;state.rpm=720+state.throttle*1780;
    state.grounded=false;state.phase='flight';state.altitude=240;
    this.crashReasonValue=null;this.pausedValue=!this.active;
    this.input.reset();this.input.enabled=this.active;
    this.pilotCamera.reset();this.syncPose();this.pilotCamera.update(0,state);this.revision++;
  }

  exit():void{
    this.activeValue=false;this.pausedValue=true;
    this.input.enabled=false;this.aircraft.root.visible=false;this.revision++;
  }

  setPaused(value:boolean):void{
    if(!this.active)return;
    this.pausedValue=value||this.crashed;
    this.input.enabled=!this.pausedValue;
    if(this.pausedValue)this.input.reset();
    this.revision++;
  }

  /** Apply the flight pose independently of animation (also useful for deterministic checks). */
  syncPose():void{
    const state=this.controller.state;
    this.aircraft.root.position.copy(state.position);
    this.pose.set(-state.pitch,state.yaw,state.bank,'YXZ');this.aircraft.root.quaternion.setFromEuler(this.pose);
    this.aircraft.root.updateMatrixWorld(true);
  }

  /** Deterministic QA placement; the product UI enters flight through start/reset only. */
  setPose(position:[number,number,number],yaw=Math.PI/2,pitch=0,bank=0,speed=45):void{
    this.controller.start();const s=this.controller.state;
    s.position.fromArray(position);s.yaw=yaw;s.pitch=pitch;s.bank=bank;s.speed=speed;
    s.throttle=.72;s.rpm=720+s.throttle*1780;s.grounded=false;s.phase='flight';
    s.altitude=Math.max(0,s.position.y-this.collision.sampleGround(s.position.x,s.position.z));
    this.crashReasonValue=null;this.input.reset();
    this.pausedValue=!this.active;this.input.enabled=this.active;
    this.pilotCamera.reset();this.syncPose();this.pilotCamera.update(0,s);this.revision++;
  }

  update(dt:number):boolean{
    if(!this.active||this.paused||this.disposed||!Number.isFinite(dt)||dt<=0)return false;
    if(document.hidden){this.setPaused(true);return true;}
    const s=this.controller.state;
    this.previous.position.copy(s.position);this.previous.yaw=s.yaw;this.previous.pitch=s.pitch;this.previous.bank=s.bank;
    this.controller.update(dt,this.input.controls);
    const hit=this.collision.check(this.previous,s);
    if(hit||s.crashed){
      this.crashReasonValue=hit?.reason==='water'?'Water contact':hit?.reason==='obstacle'?'Collision with the city':hit?.reason==='terrain'?'Ground contact':'Hard landing';
      s.crashed=true;s.phase='crashed';s.speed=s.verticalSpeed=s.throttle=s.rpm=0;
      s.pitchRate=s.rollRate=s.yawRate=0;this.setPaused(true);
    }
    this.syncPose();this.aircraft.update(Math.min(dt,.12),s,this.paused?NEUTRAL:this.input.controls);
    this.pilotCamera.update(Math.min(dt,.12),s);this.revision++;
    return true;
  }

  snapshot(){
    const s=this.controller.state;
    const warning=this.crashed?this.crashReasonValue:s.stallSeverity>.4?'Low airspeed — lower the nose and add throttle':null;
    return {active:this.active,paused:this.paused,status:this.status,position:s.position.toArray(),yaw:s.yaw,pitch:s.pitch,bank:s.bank,
      speed:s.speed,speedKmh:s.speed*3.6,altitude:s.altitude,verticalSpeed:s.verticalSpeed,throttle:s.throttle,rpm:s.rpm,
      grounded:s.grounded,crashed:s.crashed,phase:s.phase,stallSeverity:s.stallSeverity,warning,crashReason:this.crashReasonValue,
      controls:{...this.input.controls},revision:this.revision,collisionObjects:this.collision.colliderCount,aircraft:this.aircraft.diagnostics};
  }

  private readonly onBlur=()=>{if(this.active)this.setPaused(true);};
  private readonly onVisibility=()=>{if(document.hidden&&this.active)this.setPaused(true);};

  dispose():void{
    if(this.disposed)return;this.exit();this.disposed=true;
    window.removeEventListener('blur',this.onBlur);document.removeEventListener('visibilitychange',this.onVisibility);
    this.input.dispose();this.scene.remove(this.aircraft.root);this.aircraft.dispose();
  }
}
