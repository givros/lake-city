/** Deterministic street traffic. No renderer dependencies or scene mutations. */
export type TrafficPoint=[number,number,number];
export type TrafficVehicle='car_sedan'|'car_suv'|'delivery_van';
export interface TrafficLane {id:string;from:string;to:string;roadId:string;width:number;offset:number;points:TrafficPoint[];length:number;speedLimit:number;oppositeEdge:number;turns:string[]}
export interface TrafficTurn {id:string;junction:string;from:string;to:string;kind:'left'|'right'|'straight';axis:'NS'|'EW';points:TrafficPoint[];length:number;speedLimit:number}
export interface TrafficJunction {id:string;position:TrafficPoint;control:'signal'|'roundabout'|'priority';phaseOffset:number;clearanceRadius:number;incoming:string[];outgoing:string[]}
export interface TrafficNetwork {version:number;sourceHash:string;vehicles:Record<TrafficVehicle,{length:number;width:number;minY:number}>;lanes:TrafficLane[];turns:TrafficTurn[];junctions:TrafficJunction[];roadCorridors:{id:string;points:[number,number][];width:number}[];metadata:Record<string,unknown>}
export type TrafficState='driving'|'turning'|'waiting_signal'|'waiting_junction'|'queued';
export interface TrafficActor {id:string;prototype:TrafficVehicle;sourceInstanceId?:string;position:TrafficPoint;rotation:number;speed:number;laneId:string;state:TrafficState;length:number;width:number;distanceTravelled:number;completedTurns:number;waitSeconds:number}
export interface TrafficFleetEntry {id:string;prototype:TrafficVehicle;sourceInstanceId?:string}
/** count is the total fleet size; supplied identities fill its first entries. */
export interface TrafficOptions {count?:number;seed?:number;fleet?:TrafficFleetEntry[]}
type Path={points:TrafficPoint[];cumulative:number[];tangents:[number,number][];length:number};
type Driver={actor:TrafficActor;lane:TrafficLane;turn:TrafficTurn|null;next:TrafficTurn;s:number;cruise:number;reserved:string|null;waitSince:number;wasStopped:boolean;stoppedForSignal:boolean};
type Reservation={actor:string;turn:string;exitLane:string};
const STEP=1/30,GAP=2.8,ACCEL=1.65,BRAKE=2.8,CELL=12;
const clamp=(v:number,a:number,b:number)=>Math.max(a,Math.min(b,v));
const direction=(a:TrafficPoint,b:TrafficPoint):[number,number]=>{const x=b[0]-a[0],z=b[2]-a[2],d=Math.hypot(x,z)||1;return [x/d,z/d];};

/** Includes mirrors and bumpers; intended for pure simulation validation too. */
export function trafficActorsOverlap(a:TrafficActor,b:TrafficActor,padding=0):boolean{
  const dx=b.position[0]-a.position[0],dz=b.position[2]-a.position[2];
  if(dx*dx+dz*dz>Math.pow(Math.hypot(a.length,a.width)/2+Math.hypot(b.length,b.width)/2+padding*2,2))return false;
  const at=[Math.sin(a.rotation),Math.cos(a.rotation)],ar=[at[1],-at[0]],bt=[Math.sin(b.rotation),Math.cos(b.rotation)],br=[bt[1],-bt[0]];
  for(const axis of [at,ar,bt,br]){
    const ra=Math.abs(axis[0]*at[0]+axis[1]*at[1])*(a.length/2+padding)+Math.abs(axis[0]*ar[0]+axis[1]*ar[1])*(a.width/2+padding);
    const rb=Math.abs(axis[0]*bt[0]+axis[1]*bt[1])*(b.length/2+padding)+Math.abs(axis[0]*br[0]+axis[1]*br[1])*(b.width/2+padding);
    if(Math.abs(dx*axis[0]+dz*axis[1])>=ra+rb-1e-7)return false;
  }
  return true;
}

export class TrafficSimulation {
  readonly actors:TrafficActor[]=[];
  readonly network:TrafficNetwork;
  private drivers:Driver[]=[];
  private lanes=new Map<string,TrafficLane>();
  private turns=new Map<string,TrafficTurn>();
  private junctions=new Map<string,TrafficJunction>();
  private paths=new Map<string,Path>();
  private reservations=new Map<string,Reservation[]>();
  private turnBodies=new Map<string,TrafficActor[]>();
  private turnConflicts=new Map<string,boolean>();
  private rngState:number;
  private accumulator=0;
  private elapsed=0;
  private redStopCount=0;
  private restartCount=0;
  private safetyHoldCount=0;
  private safetyExamples:{time:number;actor:string;other:string;path:string;otherPath:string;position:TrafficPoint;otherPosition:TrafficPoint}[]=[];
  private maxWait=0;

  constructor(network:TrafficNetwork,options:TrafficOptions={}){
    if(network.version!==1||network.lanes.length===0)throw new Error('Unsupported or empty traffic network.');
    this.network=network;this.rngState=(options.seed??1937)>>>0;
    for(const l of network.lanes){this.lanes.set(l.id,l);this.paths.set(l.id,this.makePath(l.points));}
    for(const t of network.turns){this.turns.set(t.id,t);const p=this.makePath(t.points);p.tangents[0]=this.paths.get(t.from)!.tangents.at(-1)!;p.tangents[p.tangents.length-1]=this.paths.get(t.to)!.tangents[0];this.paths.set(t.id,p);}
    for(const j of network.junctions)this.junctions.set(j.id,j);
    const fleet=options.fleet??[],count=options.count??(fleet.length||84);
    if(!Number.isSafeInteger(count)||count<1||count<fleet.length)throw new Error('Traffic count must be a positive integer covering every supplied fleet entry.');
    const identities=new Set<string>();
    for(const entry of fleet){if(!entry.id||identities.has(entry.id)||!network.vehicles[entry.prototype])throw new Error(`Invalid or duplicate traffic fleet entry ${entry.id}.`);identities.add(entry.id);}
    const candidates=network.lanes.filter(l=>this.paths.get(l.id)!.length>45),weights=candidates.map(l=>this.paths.get(l.id)!.length),sum=weights.reduce((a,b)=>a+b,0);
    const maximumLength=Math.max(...Object.values(network.vehicles).map(v=>v.length));
    const capacity=candidates.reduce((n,l)=>n+Math.floor(Math.max(0,this.paths.get(l.id)!.length-42)/(maximumLength+GAP+7)),0);
    if(count>capacity)throw new Error(`Traffic fleet of ${count} exceeds the safe initial distribution capacity of ${capacity}.`);
    for(let i=0;i<count;i++){
      let placed=false;
      for(let attempt=0;attempt<3000&&!placed;attempt++){
        let roll=this.random()*sum,index=0;while(index<weights.length-1&&roll>=weights[index]){roll-=weights[index];index++;}
        const lane=candidates[index],path=this.paths.get(lane.id)!,s=8+this.random()*Math.max(1,path.length-42),r=this.random();
        const fixed=fleet[i],prototype:TrafficVehicle=fixed?.prototype??(r<.65?'car_sedan':r<.92?'car_suv':'delivery_van'),size=network.vehicles[prototype];
        const generatedId=`traffic_${String(i-fleet.length).padStart(3,'0')}`,id=fixed?.id??generatedId;
        if(!fixed&&identities.has(id))throw new Error(`Generated traffic identity ${id} conflicts with a supplied vehicle.`);
        const actor:TrafficActor={id,prototype,...(fixed?.sourceInstanceId?{sourceInstanceId:fixed.sourceInstanceId}:{}),position:[0,0,0],rotation:0,speed:0,laneId:lane.id,state:'driving',length:size.length,width:size.width,distanceTravelled:0,completedTurns:0,waitSeconds:0};
        this.pose(actor,lane.id,s);
        if(this.actors.some(other=>trafficActorsOverlap(actor,other,3.5)))continue;
        const driver:Driver={actor,lane,turn:null,next:this.chooseTurn(lane),s,cruise:.84+this.random()*.16,reserved:null,waitSince:0,wasStopped:false,stoppedForSignal:false};
        actor.speed=Math.min(lane.speedLimit*driver.cruise,Math.sqrt(2*BRAKE*Math.max(0,path.length-s-14)));
        this.actors.push(actor);this.drivers.push(driver);placed=true;
      }
      if(!placed)throw new Error(`Could not safely distribute traffic actor ${i}.`);
    }
  }

  /** Fixed steps preserve behavior across rendering rates. A suspended tab does
   * not fast-forward the city when it resumes. Call repeatedly for offline QA. */
  update(dt:number):void{
    if(!Number.isFinite(dt)||dt<=0)return;
    this.accumulator+=Math.min(dt,.25);
    while(this.accumulator+1e-10>=STEP){this.step(STEP);this.accumulator-=STEP;}
  }

  junctionState(id:string){
    const j=this.junctions.get(id);if(!j)return null;
    const t=(this.elapsed+j.phaseOffset)%28;
    const phase=j.control!=='signal'?'yield':t<10?'NS':t<12?'NS_amber':t<14?'all_red':t<24?'EW':t<26?'EW_amber':'all_red';
    const actorIds=(this.reservations.get(id)??[]).map(r=>r.actor);
    return {id,control:j.control,phase,occupied:actorIds.length>0,actorId:actorIds[0]??null,actorIds};
  }

  snapshot(){return {time:this.elapsed,actors:this.actors.map(a=>({...a,position:[...a.position] as TrafficPoint})),junctions:this.network.junctions.map(j=>this.junctionState(j.id)),stats:this.stats()};}
  diagnostics(){return {safetyExamples:this.safetyExamples,waitingDrivers:this.drivers.filter(d=>d.actor.waitSeconds>45).map(d=>({id:d.actor.id,state:d.actor.state,wait:d.actor.waitSeconds,lane:d.lane.id,turn:d.turn?.id,next:d.next.id,s:d.s,length:this.paths.get(d.turn?.id??d.lane.id)!.length,reserved:d.reserved,reservation:d.reserved?this.reservations.get(d.reserved):null,position:d.actor.position})),reservations:[...this.reservations.entries()]};}
  stats(){
    return {time:this.elapsed,actors:this.actors.length,moving:this.actors.filter(a=>a.speed>.25).length,stopped:this.actors.filter(a=>a.speed<=.25).length,waitingAtSignals:this.actors.filter(a=>a.state==='waiting_signal').length,queued:this.actors.filter(a=>a.state==='queued').length,turning:this.actors.filter(a=>a.state==='turning').length,completedTurns:this.actors.reduce((n,a)=>n+a.completedTurns,0),distanceTravelled:this.actors.reduce((n,a)=>n+a.distanceTravelled,0),redStops:this.redStopCount,restarts:this.restartCount,collisionAvoidanceStops:this.safetyHoldCount,longestWaitSeconds:this.maxWait,activeJunctions:this.reservations.size};
  }

  private random():number{let t=this.rngState+=0x6D2B79F5;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return ((t^t>>>14)>>>0)/4294967296;}
  private chooseTurn(lane:TrafficLane):TrafficTurn{
    const choices=lane.turns.map(id=>this.turns.get(id)!).filter(Boolean);
    if(!choices.length)throw new Error(`Traffic lane ${lane.id} has no onward route.`);
    const weights=choices.map(t=>t.kind==='straight'?4:t.kind==='right'?2:1);let n=this.random()*weights.reduce((a,b)=>a+b,0);
    for(let i=0;i<choices.length;i++){n-=weights[i];if(n<=0)return choices[i];}return choices.at(-1)!;
  }
  private makePath(points:TrafficPoint[]):Path{
    const cumulative=[0],tangents:[number,number][]=[];
    for(let i=1;i<points.length;i++)cumulative.push(cumulative[i-1]+Math.hypot(points[i][0]-points[i-1][0],points[i][2]-points[i-1][2]));
    for(let i=0;i<points.length;i++){
      const a=direction(points[Math.max(0,i-1)],points[Math.min(points.length-1,i+1)]);tangents.push(a);
    }
    return {points,cumulative,tangents,length:cumulative.at(-1)!};
  }
  private pose(actor:TrafficActor,id:string,distance:number):void{
    const p=this.paths.get(id)!,s=clamp(distance,0,p.length);let lo=0,hi=p.cumulative.length-1;
    while(lo+1<hi){const mid=(lo+hi)>>1;if(p.cumulative[mid]<=s)lo=mid;else hi=mid;}
    const t=(s-p.cumulative[lo])/(p.cumulative[hi]-p.cumulative[lo]||1),a=p.points[lo],b=p.points[hi],ta=p.tangents[lo],tb=p.tangents[hi];
    actor.position[0]=a[0]+(b[0]-a[0])*t;actor.position[1]=a[1]+(b[1]-a[1])*t-this.network.vehicles[actor.prototype].minY;actor.position[2]=a[2]+(b[2]-a[2])*t;
    actor.rotation=Math.atan2(ta[0]+(tb[0]-ta[0])*t,ta[1]+(tb[1]-ta[1])*t);actor.laneId=id;
  }
  private permits(turn:TrafficTurn):boolean{const state=this.junctionState(turn.junction)!;return state.control!=='signal'||state.phase===turn.axis;}
  private owns(junction:string,id:string):boolean{return this.reservations.get(junction)?.some(r=>r.actor===id)??false;}
  private conflicts(a:TrafficTurn,b:TrafficTurn):boolean{
    if(a.from===b.from||a.to===b.to)return true;
    if(this.junctions.get(a.junction)!.control==='roundabout')return true;
    const key=[a.id,b.id].sort().join(':');const known=this.turnConflicts.get(key);if(known!==undefined)return known;
    const bodies=(turn:TrafficTurn)=>{
      if(this.turnBodies.has(turn.id))return this.turnBodies.get(turn.id)!;
      const path=this.paths.get(turn.id)!,count=Math.ceil(path.length/1.2),items:TrafficActor[]=[];
      for(let i=0;i<=count;i++){
        const body:TrafficActor={id:'clearance',prototype:'delivery_van',position:[0,0,0],rotation:0,speed:0,laneId:turn.id,state:'turning',length:Math.max(...Object.values(this.network.vehicles).map(v=>v.length))+2,width:Math.max(...Object.values(this.network.vehicles).map(v=>v.width))+.3,distanceTravelled:0,completedTurns:0,waitSeconds:0};
        this.pose(body,turn.id,path.length*i/count);items.push(body);
      }
      this.turnBodies.set(turn.id,items);return items;
    };
    const aa=bodies(a),bb=bodies(b);const result=aa.some(x=>bb.some(y=>trafficActorsOverlap(x,y)));
    this.turnConflicts.set(key,result);return result;
  }
  private step(dt:number):void{
    this.elapsed+=dt;
    const byLane=new Map<string,Driver[]>(),turningFrom=new Map<string,Driver[]>();
    for(const d of this.drivers){
      if(!d.turn){if(!byLane.has(d.lane.id))byLane.set(d.lane.id,[]);byLane.get(d.lane.id)!.push(d);}
      else{if(!turningFrom.has(d.turn.from))turningFrom.set(d.turn.from,[]);turningFrom.get(d.turn.from)!.push(d);}
      if(d.reserved&&!d.turn){const list=this.reservations.get(d.reserved)??[],reservation=list.find(r=>r.actor===d.actor.id);if(reservation?.exitLane===d.lane.id&&d.s>d.actor.length/2+1.4){const remaining=list.filter(r=>r.actor!==d.actor.id);if(remaining.length)this.reservations.set(d.reserved,remaining);else this.reservations.delete(d.reserved);d.reserved=null;}}
    }
    for(const list of byLane.values())list.sort((a,b)=>b.s-a.s);
    const requests=this.drivers.filter(d=>!d.turn&&!d.reserved&&this.paths.get(d.lane.id)!.length-d.s<Math.max(14,d.actor.speed*1.5)).sort((a,b)=>b.actor.waitSeconds-a.actor.waitSeconds||a.actor.id.localeCompare(b.actor.id));
    for(const d of requests){
      // A queued follower must never reserve a junction ahead of its own leader.
      if(byLane.get(d.lane.id)?.[0]!==d)continue;
      const exitClear=(t:TrafficTurn)=>{const lead=byLane.get(t.to)?.at(-1);return !lead||lead.s>=(d.actor.length+lead.actor.length)/2+GAP+8;};
      const cost=(t:TrafficTurn)=>(byLane.get(t.to)?.length??0)/this.paths.get(t.to)!.length;
      if(d.actor.waitSeconds>3&&!exitClear(d.next)){
        const alternatives=d.lane.turns.map(id=>this.turns.get(id)!).filter(t=>exitClear(t)&&this.permits(t)).sort((a,b)=>cost(a)-cost(b)||a.id.localeCompare(b.id));
        if(alternatives.length)d.next=alternatives[0];
      }
      const turn=d.next,existing=this.reservations.get(turn.junction)??[];
      if(!this.permits(turn)||existing.some(r=>this.conflicts(turn,this.turns.get(r.turn)!)))continue;
      const nearest=byLane.get(turn.to)?.at(-1);
      if(nearest&&nearest.s<(d.actor.length+nearest.actor.length)/2+GAP+8)continue;
      this.reservations.set(turn.junction,[...existing,{actor:d.actor.id,turn:turn.id,exitLane:turn.to}]);d.reserved=turn.junction;
    }
    const cells=new Map<string,Driver[]>();
    const cell=(a:TrafficActor)=>`${Math.floor(a.position[0]/CELL)},${Math.floor(a.position[2]/CELL)}`;
    for(const d of this.drivers){const k=cell(d.actor);if(!cells.has(k))cells.set(k,[]);cells.get(k)!.push(d);}
    // Front-to-back order on each lane reduces one-step braking jitter.
    const order=[...this.drivers].sort((a,b)=>a.actor.laneId.localeCompare(b.actor.laneId)||b.s-a.s);
    for(const d of order){
      const actor=d.actor,path=this.paths.get(d.turn?.id??d.lane.id)!;let available=Infinity,desired=d.turn?d.turn.speedLimit:d.lane.speedLimit*d.cruise,reason:TrafficState=d.turn?'turning':'driving';
      const considerLeader=(leader:Driver,distance:number)=>{
        const gap=distance-(actor.length+leader.actor.length)/2-GAP;available=Math.min(available,Math.max(0,gap));
        desired=Math.min(desired,Math.max(0,leader.actor.speed+(gap-actor.speed*1.1)*.6));if(gap<actor.speed*1.2+3)reason='queued';
      };
      if(!d.turn){
        const list=byLane.get(d.lane.id)??[],index=list.indexOf(d);if(index>0)considerLeader(list[index-1],list[index-1].s-d.s);
        for(const other of turningFrom.get(d.lane.id)??[])considerLeader(other,path.length-d.s+other.s);
        const owns=this.owns(d.next.junction,actor.id);
        if(!owns){available=Math.min(available,Math.max(0,path.length-d.s));if(path.length-d.s<Math.max(6,actor.speed*2))reason=this.permits(d.next)?'waiting_junction':'waiting_signal';}
        else {const lead=byLane.get(d.next.to)?.at(-1);if(lead)considerLeader(lead,path.length-d.s+this.paths.get(d.next.id)!.length+lead.s);}
        desired=Math.min(desired,Math.sqrt(d.next.speedLimit*d.next.speedLimit+2*BRAKE*Math.max(0,path.length-d.s)));
      }else{const lead=byLane.get(d.turn.to)?.at(-1);if(lead)considerLeader(lead,path.length-d.s+lead.s);}
      desired=Math.min(desired,Math.sqrt(2*BRAKE*Math.max(0,available)));
      let speed=actor.speed+clamp(desired-actor.speed,-BRAKE*dt,ACCEL*dt),advance=Math.min((actor.speed+speed)*.5*dt,available);
      if(advance<.0001){advance=0;speed=0;}
      // Compute an exact next path pose before committing; explicit junction
      // reservations do the ordinary control, this prevents residual conflicts.
      let s=d.s+advance,lane=d.lane,turn=d.turn,completed=false;
      if(s>=path.length-1e-8){
        if(turn){s=Math.max(0,s-path.length);lane=this.lanes.get(turn.to)!;turn=null;completed=true;}
        else if(this.owns(d.next.junction,actor.id)){s=Math.max(0,s-path.length);turn=d.next;}
        else{s=path.length;speed=0;}
      }
      const oldPosition:[number,number,number]=[...actor.position],oldRotation=actor.rotation,oldId=actor.laneId,oldCell=cell(actor);
      this.pose(actor,turn?.id??lane.id,s);let unsafe=false;
      const cx=Math.floor(actor.position[0]/CELL),cz=Math.floor(actor.position[2]/CELL);
      for(let x=cx-1;x<=cx+1&&!unsafe;x++)for(let z=cz-1;z<=cz+1&&!unsafe;z++)for(const other of cells.get(`${x},${z}`)??[]){if(other!==d&&trafficActorsOverlap(actor,other.actor,.09)){unsafe=true;if(this.safetyExamples.length<24&&!this.safetyExamples.some(e=>e.actor===actor.id&&e.other===other.actor.id))this.safetyExamples.push({time:this.elapsed,actor:actor.id,other:other.actor.id,path:actor.laneId,otherPath:other.actor.laneId,position:[...actor.position],otherPosition:[...other.actor.position]});break;}}
      if(unsafe){actor.position=oldPosition;actor.rotation=oldRotation;actor.laneId=oldId;speed=0;advance=0;reason='queued';this.safetyHoldCount++;}
      else{
        d.s=s;d.lane=lane;d.turn=turn;
        if(completed){actor.completedTurns++;d.next=this.chooseTurn(lane);}
        const newCell=cell(actor);if(newCell!==oldCell){const bucket=cells.get(oldCell)!;bucket.splice(bucket.indexOf(d),1);if(!cells.has(newCell))cells.set(newCell,[]);cells.get(newCell)!.push(d);}
      }
      actor.speed=speed;actor.distanceTravelled+=advance;actor.state=d.turn?'turning':reason;
      if(speed<.18){actor.waitSeconds+=dt;this.maxWait=Math.max(this.maxWait,actor.waitSeconds);if(!d.wasStopped&&actor.state==='waiting_signal'){this.redStopCount++;d.stoppedForSignal=true;}d.wasStopped=true;}
      else {if(d.wasStopped&&speed>.8){this.restartCount++;d.wasStopped=false;d.stoppedForSignal=false;}actor.waitSeconds=0;}
    }
  }
}
