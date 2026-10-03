"""Derive safe, right-hand moving traffic lanes from the authored street plan.

No source geometry is changed. Source vehicles are promoted into live traffic;
their authored curb footprints remain conservative route clearance guides.
Short dead ends, narrow local lanes and highway ramps are outside this network.
"""
import hashlib,json,math,sys
from pathlib import Path
from collections import defaultdict,Counter
import numpy as np
from shapely.geometry import LineString,Point,Polygon
from shapely.ops import unary_union,substring
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from citylib import primitive

def rounded_point(p):return tuple(round(float(v),5) for v in p)
def unit(v):
    v=np.asarray(v,float);return v/max(np.linalg.norm(v),1e-10)
def samples(line,step=1.4):
    return [list(line.interpolate(float(d)).coords)[0] for d in np.linspace(0,line.length,max(2,int(math.ceil(line.length/step))+1))]
def footprint(p,t,length,width):
    d=unit(t)*length/2;r=np.array([-t[1],t[0]])*width/2;p=np.asarray(p)
    return Polygon([p-d-r,p+d-r,p+d+r,p-d+r])
def bezier(a,b,c,d,step=.75):
    a,b,c,d=map(lambda p:np.asarray(p,float),(a,b,c,d));length=sum(np.linalg.norm(y-x) for x,y in [(a,b),(b,c),(c,d)])
    return [(a*(1-t)**3+3*b*(1-t)**2*t+3*c*(1-t)*t*t+d*t**3).tolist() for t in np.linspace(0,1,max(3,int(length/step)+1))]
def strongly_connected(graph):
    # Iterative Kosaraju avoids recursion depth depending on scene scale.
    seen=set();order=[]
    for start in graph:
        if start in seen:continue
        stack=[(start,False)]
        while stack:
            n,done=stack.pop()
            if done:order.append(n);continue
            if n in seen:continue
            seen.add(n);stack.append((n,True));stack.extend((q,False) for q in graph[n] if q not in seen)
    rev={n:[] for n in graph}
    for n,qs in graph.items():
        for q in qs:rev[q].append(n)
    seen=set();groups=[]
    for start in reversed(order):
        if start in seen:continue
        group=[];stack=[start];seen.add(start)
        while stack:
            n=stack.pop();group.append(n)
            for q in rev[n]:
                if q not in seen:seen.add(q);stack.append(q)
        groups.append(group)
    return groups

def main():
    spec=json.loads((ROOT/'scene_spec.json').read_text());source=json.loads((ROOT/'source_scene.json').read_text());city=json.loads((ROOT/'viewer/public/assets/city.json').read_text())
    roads=[r for r in spec['streets'] if r['width']>=10 and not any(s in r['id'] for s in ('EXPRESS','RAMP','HIGHWAY'))]
    lines=[LineString(r['points']) for r in roads]
    noded=list(unary_union(lines).geoms)
    edges=[]
    for line in sorted(noded,key=lambda g:(tuple(g.coords[0]),tuple(g.coords[-1]))):
        if line.length<35:continue
        mid=line.interpolate(.5,normalized=True);ri=min(range(len(lines)),key=lambda i:lines[i].distance(mid));owner=lines[ri]
        a,b=rounded_point(line.coords[0]),rounded_point(line.coords[-1])
        if a==b:continue
        dist=owner.project(mid);od=np.asarray(owner.interpolate(min(owner.length,dist+.1)).coords[0])-owner.interpolate(max(0,dist-.1)).coords[0]
        ld=np.asarray(line.interpolate(min(line.length,line.length/2+.1)).coords[0])-line.interpolate(max(0,line.length/2-.1)).coords[0]
        if np.dot(od,ld)<0:line=LineString(list(line.coords)[::-1]);a,b=b,a
        edges.append({'line':line,'a':a,'b':b,'road':roads[ri]})
    # Remove unsupported open ends instead of making cars vanish or U-turn.
    while True:
        deg=Counter(n for e in edges for n in (e['a'],e['b']));kept=[e for e in edges if deg[e['a']]>=2 and deg[e['b']]>=2]
        if len(kept)==len(edges):break
        edges=kept
    nodes=sorted(set(n for e in edges for n in (e['a'],e['b'])));ids={p:f'J{i:03}' for i,p in enumerate(nodes)}
    roundabouts=[((u-725)*1.5,(v-544)*1.5) for u in (724,997) for v in (151,581,804,981)]
    incident=defaultdict(list)
    for e in edges:
        incident[e['a']].append(e);incident[e['b']].append(e)
    junctions=[];trim={}
    for p in nodes:
        # Stop the vehicle centre six metres before the corner fillet so a
        # waiting opposing van cannot intrude into a permitted turn's sweep.
        circle=any(math.dist(p,q)<.1 for q in roundabouts);trim[p]=20 if circle else max(e['road']['width']/2 for e in incident[p])+8.5
        jid=ids[p];phase=int(hashlib.sha256(jid.encode()).hexdigest()[:8],16)%28
        junctions.append({'id':jid,'position':[p[0],.112 if circle else .095,p[1]],'control':'roundabout' if circle else 'signal' if len(incident[p])>=3 else 'priority','phaseOffset':phase,'clearanceRadius':trim[p],'incoming':[],'outgoing':[]})
    jmap={j['id']:j for j in junctions}
    # Road envelope follows the real asphalt, including the raised roundabouts.
    asphalt=unary_union([ln.buffer(r['width']/2,resolution=12) for ln,r in zip(lines,roads)]+[Point(p).buffer(17,resolution=48) for p in roundabouts])
    asphalt=asphalt.difference(unary_union([Point(p).buffer(8.3,resolution=48) for p in roundabouts]))
    drivable=asphalt.buffer(.035)
    vehicle_info={}
    for name in ['car_sedan','car_suv','delivery_van']:
        verts=np.concatenate([primitive(p)[0] for p in source['prototypes'][name]['parts']]);low=verts.min(axis=0);high=verts.max(axis=0)
        vehicle_info[name]={'length':round(float(high[2]-low[2]),5),'width':round(float(high[0]-low[0]),5),'minY':round(float(low[1]),5)}
    max_length=max(v['length'] for v in vehicle_info.values());max_width=max(v['width'] for v in vehicle_info.values())
    parked=[]
    for i in source['instances']:
        if i['prototype'] not in vehicle_info:continue
        v=vehicle_info[i['prototype']];rot=i['rotation'];t=np.array([math.sin(rot),math.cos(rot)]);p=[i['position'][0],i['position'][2]]
        parked.append(footprint(p,t,v['length']*i['scale'][2],v['width']*i['scale'][0]).buffer(.12))
    parked_tree=STRtree(parked)
    rejection=Counter();reject_examples=[]
    def safe(path,label):
        ln=LineString(path)
        for d in np.linspace(0,ln.length,max(2,math.ceil(ln.length/1.8)+1)):
            p=np.asarray(ln.interpolate(float(d)).coords[0]);a=np.asarray(ln.interpolate(max(0,float(d)-.1)).coords[0]);b=np.asarray(ln.interpolate(min(ln.length,float(d)+.1)).coords[0]);t=unit(b-a)
            poly=footprint(p,t,max_length,max_width)
            if not drivable.covers(poly):
                rejection['outside_asphalt']+=1
                if len(reject_examples)<20:reject_examples.append([label,'outside_asphalt',p.tolist()])
                return False
            if any(poly.intersection(parked[int(k)]).area>1e-6 for k in parked_tree.query(poly)):
                rejection['parked_vehicle_clearance']+=1
                if len(reject_examples)<20:reject_examples.append([label,'parked_vehicle_clearance',p.tolist()])
                return False
        return True
    lanes=[]
    for ei,e in enumerate(edges):
        rd=e['road'];width=rd['width'];positive=3.5 if width>=18 else max(.8,min(2.5,width/2-4.3));negative=3.5 if width>=18 else max(1.5,3.0-positive)
        # The organic lakeshore has tighter bends than the grid. Use its clear
        # outer lane width so opposing long vehicles retain turning clearance.
        if rd['id']=='RD_LAKESHORE':negative=3.2
        for reverse,offset in [(False,positive),(True,negative)]:
            a,b=(e['b'],e['a']) if reverse else (e['a'],e['b']);base=LineString(list(e['line'].coords)[::-1]) if reverse else e['line']
            # Shapely left in XZ is the driver's right because Z points south.
            off=base.offset_curve(offset,join_style=1)
            if off.geom_type!='LineString' or off.length<trim[a]+trim[b]+12:continue
            off=substring(off,trim[a],off.length-trim[b]);points=samples(off,1.3);lid=f'L{ei:03}{"B" if reverse else "A"}'
            if not safe(points,lid):continue
            height=.1 if rd['id']=='RD_LAKESHORE' else .095
            lane={'id':lid,'from':ids[a],'to':ids[b],'roadId':rd['id'],'width':width,'offset':offset,'points':[[round(x,5),height,round(z,5)] for x,z in points],'length':round(off.length,5),'speedLimit':10 if width<18 else 12,'oppositeEdge':ei,'turns':[]}
            lanes.append(lane);jmap[lane['from']]['outgoing'].append(lid);jmap[lane['to']]['incoming'].append(lid)
    lmap={l['id']:l for l in lanes};turns=[]
    for junction in junctions:
        center=np.array([junction['position'][0],junction['position'][2]])
        stopped_approaches={}
        for lid in junction['incoming']:
            lane=lmap[lid];line=LineString([[p[0],p[2]] for p in lane['points']]);bodies=[]
            for back in (0,2,4,6):
                dd=max(0,line.length-back);p=np.asarray(line.interpolate(dd).coords[0]);q=np.asarray(line.interpolate(max(0,dd-.1)).coords[0]);bodies.append(footprint(p,unit(p-q),max_length+.25,max_width+.2))
            stopped_approaches[lid]=unary_union(bodies)
        for incoming in junction['incoming']:
            il=lmap[incoming];a=np.array(il['points'][-1])[::2];it=unit(a-np.array(il['points'][-2])[::2])
            for outgoing in junction['outgoing']:
                ol=lmap[outgoing]
                if il['oppositeEdge']==ol['oppositeEdge']:continue
                b=np.array(ol['points'][0])[::2];ot=unit(np.array(ol['points'][1])[::2]-b);dot=np.dot(it,ot);cross=it[0]*ot[1]-it[1]*ot[0]
                kind='straight' if dot>.8 else 'right' if cross>0 else 'left';tid=f'T{len(turns):04}'
                if junction['control']=='roundabout':
                    start=math.atan2(a[1]-center[1],a[0]-center[0])-.29;end=math.atan2(b[1]-center[1],b[0]-center[0])+.29
                    while end>=start:end-=2*math.pi
                    radius=12.4;p=center+radius*np.array([math.cos(start),math.sin(start)]);q=center+radius*np.array([math.cos(end),math.sin(end)])
                    pt=np.array([math.sin(start),-math.cos(start)]);qt=np.array([math.sin(end),-math.cos(end)])
                    entry=bezier(a,a+it*3.8,p-pt*2.0,p);arc=[(center+radius*np.array([math.cos(t),math.sin(t)])).tolist() for t in np.linspace(start,end,max(3,int((start-end)*radius/.65)+1))];exit=bezier(q,q+qt*2.0,b-ot*3.8,b)
                    points=entry[:-1]+arc[:-1]+exit
                else:
                    # Tangent-preserving cubic fillet through the actual junction.
                    ia=a+it*6;ib=b-ot*6;dist=np.linalg.norm(ib-ia);c=.34*dist if kind=='straight' else .52*dist
                    points=[a.tolist()]+bezier(ia,ia+it*c,ib-ot*c,ib)+[b.tolist()]
                if not safe(points,tid):continue
                # Other approaches may queue at red; test that worst-case van
                # footprint before admitting any turn, independent of runtime.
                blockers=unary_union([p for lid,p in stopped_approaches.items() if lid!=incoming]);turn_line=LineString(points);blocked=False
                for dd in np.linspace(0,turn_line.length,max(2,math.ceil(turn_line.length/.9)+1)):
                    p=np.asarray(turn_line.interpolate(float(dd)).coords[0]);q=np.asarray(turn_line.interpolate(max(0,float(dd)-.1)).coords[0]);r=np.asarray(turn_line.interpolate(min(turn_line.length,float(dd)+.1)).coords[0]);body=footprint(p,unit(r-q),max_length,max_width)
                    if body.intersection(blockers).area>1e-6:blocked=True;break
                if blocked:rejection['queued_approach_clearance']+=1;continue
                line=LineString(points);height=.112 if junction['control']=='roundabout' else .095
                point3=[[round(x,5),height,round(z,5)] for x,z in points];point3[0][1]=il['points'][-1][1];point3[-1][1]=ol['points'][0][1]
                turn={'id':tid,'junction':junction['id'],'from':incoming,'to':outgoing,'kind':kind,'axis':'EW' if abs(it[0])>abs(it[1]) else 'NS','points':point3,'length':round(line.length,5),'speedLimit':5 if junction['control']=='roundabout' else 4 if kind=='right' else 5.5 if kind=='left' else 8}
                turns.append(turn);il['turns'].append(tid)
    graph={l['id']:[] for l in lanes}
    for t in turns:graph[t['from']].append(t['to'])
    groups=strongly_connected(graph);keep=set(max(groups,key=lambda g:sum(lmap[n]['length'] for n in g)))
    lanes=[l for l in lanes if l['id'] in keep];turns=[t for t in turns if t['from'] in keep and t['to'] in keep];tkeep={t['id'] for t in turns}
    for l in lanes:l['turns']=[t for t in l['turns'] if t in tkeep]
    used_j={l[k] for l in lanes for k in ('from','to')};junctions=[j for j in junctions if j['id'] in used_j]
    for j in junctions:
        j['incoming']=[l for l in j['incoming'] if l in keep];j['outgoing']=[l for l in j['outgoing'] if l in keep]
    result={'version':1,'sourceHash':city['sourceHash'],'units':'metres','axes':'X east / Y up / Z south; vehicle nose +Z','drivingSide':'right','vehicles':vehicle_info,'lanes':lanes,'turns':turns,'junctions':junctions,'roadCorridors':[{'id':r['id'],'points':r['points'],'width':r['width']} for r in roads],'metadata':{'defaultVehicleCount':84+len(parked),'eligibleRoads':len(roads),'laneCount':len(lanes),'turnCount':len(turns),'junctionCount':len(junctions),'laneMetres':round(sum(l['length'] for l in lanes)),'roundabouts':sum(j['control']=='roundabout' for j in junctions),'signalizedJunctions':sum(j['control']=='signal' for j in junctions),'sourceVehiclesPromoted':len(parked),'fixedVehicles':0,'trajectoryValidation':'Full maximum vehicle footprint sampled every <=1.8 m against real asphalt, roundabout islands and conservative authored curb clearances; all source vehicles are animated.','excluded':'Narrow local access streets, express roads, ramps, dead-end stubs, and trajectories crossing authored curb clearances.','rejectedCandidates':dict(rejection),'strongComponentsBeforePrune':sorted([len(g) for g in groups],reverse=True),'seed':1937}}
    out=ROOT/'viewer/public/assets/traffic_network.json';out.write_text(json.dumps(result,separators=(',',':')))
    report={**result['metadata'],'sourceHash':city['sourceHash'],'examples':reject_examples,'networkSha256':hashlib.sha256(out.read_bytes()).hexdigest(),'bounds':{'minX':min(p[0] for l in lanes for p in l['points']),'maxX':max(p[0] for l in lanes for p in l['points']),'minZ':min(p[2] for l in lanes for p in l['points']),'maxZ':max(p[2] for l in lanes for p in l['points'])}}
    (ROOT/'comparisons/traffic_network_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    assert len(lanes)>=60 and all(l['turns'] for l in lanes),'Traffic network is too sparse or has a dead end.'

if __name__=='__main__':main()
