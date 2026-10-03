import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {stripTypeScriptTypes} from 'node:module';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const source=fs.readFileSync(path.join(root,'src/traffic.ts'),'utf8');
const js=stripTypeScriptTypes(source);
const {TrafficSimulation,trafficActorsOverlap}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
const network=JSON.parse(fs.readFileSync(path.join(root,'public/assets/traffic_network.json'),'utf8'));
const seconds=Number(process.argv[2]??1800),count=Number(process.argv[3]??84),seed=Number(process.argv[4]??1937),dt=.1;
const fleet=process.argv.includes('--source-fleet')?JSON.parse(fs.readFileSync(path.join(root,'../source_scene.json'),'utf8')).instances.filter(i=>['car_sedan','car_suv','delivery_van'].includes(i.prototype)).map(i=>({id:i.id,prototype:i.prototype,sourceInstanceId:i.id})):undefined;
const simulation=new TrafficSimulation(network,{count,seed,fleet});
const report={durationSeconds:seconds,seed,actors:count,collisionPairs:[],nonfinite:0,maxSpeed:0,minMoving:count,maxMoving:0,endpointGaps:[],checkpoints:[],actorProgress:[]};
const segmentHints=new Map(),lastProgress=simulation.actors.map(a=>a.distanceTravelled);report.minimum120SecondProgress=Infinity;report.minimum120SecondProgressActor=null;
const paths=new Map([...network.lanes,...network.turns].map(p=>[p.id,p])),lanes=new Map(network.lanes.map(p=>[p.id,p]));
for(const turn of network.turns){
  for(const [a,b] of [[turn.points[0],lanes.get(turn.from).points.at(-1)],[turn.points.at(-1),lanes.get(turn.to).points[0]]]){
    const gap=Math.hypot(...a.map((v,k)=>v-b[k]));if(gap>.025)report.endpointGaps.push({turn:turn.id,gap});
  }
}
let offRoute=0,groundContactErrors=0,reservationErrors=0;
for(let tick=0;tick<seconds/dt;tick++){
  simulation.update(dt);
  if(tick%5===0){
    const actors=simulation.actors;
    for(let i=0;i<actors.length;i++){
      const a=actors[i];if(![...a.position,a.rotation,a.speed].every(Number.isFinite))report.nonfinite++;
      report.maxSpeed=Math.max(report.maxSpeed,a.speed);
      for(let j=i+1;j<actors.length;j++){const b=actors[j];if(Math.abs(a.position[0]-b.position[0])>8||Math.abs(a.position[2]-b.position[2])>8)continue;if(trafficActorsOverlap(a,b)){if(report.collisionPairs.length<12)report.collisionPairs.push([tick*dt,a.id,b.id]);}}
      // Independently measure distance to the full graph segment in XZ.
      const p=paths.get(a.laneId),hint=segmentHints.get(a.id);let nearest=Infinity,ground=0,bestSegment=1;
      const scan=(start,end)=>{for(let k=start;k<end;k++){
        const q=p.points[k-1],r=p.points[k],dx=r[0]-q[0],dz=r[2]-q[2],t=Math.max(0,Math.min(1,((a.position[0]-q[0])*dx+(a.position[2]-q[2])*dz)/(dx*dx+dz*dz||1)));
        const dist=Math.hypot(a.position[0]-q[0]-dx*t,a.position[2]-q[2]-dz*t);
        if(dist<nearest){nearest=dist;ground=q[1]+(r[1]-q[1])*t;bestSegment=k;}
      }};
      if(hint?.path===a.laneId)scan(Math.max(1,hint.segment-32),Math.min(p.points.length,hint.segment+33));
      if(nearest>1e-5)scan(1,p.points.length);
      segmentHints.set(a.id,{path:a.laneId,segment:bestSegment});
      if(nearest>1e-5)offRoute++;
      if(Math.abs(a.position[1]+network.vehicles[a.prototype].minY-ground)>1e-5)groundContactErrors++;
      if(p.junction&&!simulation.junctionState(p.junction).actorIds.includes(a.id))reservationErrors++;
    }
  }
  if(tick%100===0){const stats=simulation.stats();report.minMoving=Math.min(report.minMoving,stats.moving);report.maxMoving=Math.max(report.maxMoving,stats.moving);}
  if((tick+1)%1200===0){for(const [i,a] of simulation.actors.entries()){const moved=a.distanceTravelled-lastProgress[i];if(moved<report.minimum120SecondProgress){report.minimum120SecondProgress=moved;report.minimum120SecondProgressActor=a.id;}lastProgress[i]=a.distanceTravelled;}}
  if(tick%3000===0){const stats=simulation.stats();report.checkpoints.push(stats);console.log(JSON.stringify(stats));}
}
report.final=simulation.stats();report.offRouteSamples=offRoute;report.groundContactErrors=groundContactErrors;report.reservationErrors=reservationErrors;
report.diagnostics=simulation.diagnostics();
report.actorProgress=simulation.actors.map(a=>({id:a.id,distance:a.distanceTravelled,turns:a.completedTurns,wait:a.waitSeconds}));
report.sourceFleetCount=fleet?.length??0;report.sourceFleetPreserved=!fleet||fleet.every(f=>simulation.actors.some(a=>a.id===f.id&&a.prototype===f.prototype&&a.sourceInstanceId===f.id));
const a=new TrafficSimulation(network,{seed:781,count:84}),b=new TrafficSimulation(network,{seed:781,count:84});
for(let i=0;i<1200;i++)a.update(.1);for(let i=0;i<2400;i++)b.update(.05);
report.maximumFrameRateDrift=Math.max(...a.actors.map((p,i)=>Math.hypot(...p.position.map((v,k)=>v-b.actors[i].position[k]))));
report.minimumActorDistance=Math.min(...report.actorProgress.map(a=>a.distance));
report.passed=report.sourceFleetPreserved&&report.collisionPairs.length===0&&report.nonfinite===0&&report.endpointGaps.length===0&&offRoute===0&&groundContactErrors===0&&reservationErrors===0&&report.maxSpeed<=12.001&&report.maximumFrameRateDrift<1e-7&&report.final.longestWaitSeconds<90&&report.final.redStops>10&&report.final.restarts>10&&report.minimumActorDistance>seconds*(count>180?.75:1.3)&&report.minimum120SecondProgress>5;
const out=path.join(root,'../comparisons/',process.argv[5]??'traffic_simulation_report.json');fs.writeFileSync(out,JSON.stringify(report,null,2));
console.log(JSON.stringify({...report,actorProgress:undefined,checkpoints:undefined},null,2));
assert(report.passed,'Traffic simulation invariant failed; inspect traffic_simulation_report.json.');
