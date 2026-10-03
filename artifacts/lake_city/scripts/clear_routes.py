"""Resolve small-furniture and trunk intrusions into final public walking routes.

Run once after dressing and before Scene.flush(). Instance IDs and source
prototypes remain unchanged; only clear, nearby ground placements are accepted.
"""
import math
from collections import defaultdict, Counter
from shapely.geometry import Polygon, LineString, Point, MultiPoint, box
from shapely.affinity import rotate, translate, scale as scale_geometry
from shapely.ops import unary_union
from shapely.strtree import STRtree
import numpy as np
from citylib import primitive


class PlacementIndex:
    def __init__(self):self.shapes={};self.cells=defaultdict(set)
    def keys(self,p):
        a,b,c,d=p.bounds
        return [(x,z) for x in range(math.floor(a/12),math.floor(c/12)+1) for z in range(math.floor(b/12),math.floor(d/12)+1)]
    def set(self,key,p):
        old=self.shapes.get(key)
        if old is not None:
            for cell in self.keys(old):self.cells[cell].discard(key)
        self.shapes[key]=p
        for cell in self.keys(p):self.cells[cell].add(key)
    def blocked(self,p,ignore):
        nearby=set()
        for key in self.keys(p):nearby.update(self.cells[key])
        return any(k!=ignore and self.shapes[k].intersects(p) for k in nearby)



def _clear_shelter_trees(s, lake, pond, placed, roadmask, park, index, trunk_shape):
    """Narrow final check against the actual six shelter structural volumes."""
    shelters=[i for i in s.instances if i['prototype']=='bus_shelter']
    if not shelters:return dict(detected=0,relocated=[],removed=[],unresolved=[])
    vertex_cache={}
    def vertices(name):
        if name not in vertex_cache:
            vertex_cache[name]=np.concatenate([primitive(p)[0] for p in s.prototypes[name]['parts']])
        return vertex_cache[name]
    sv=vertices('bus_shelter');lo=sv.min(axis=0);hi=sv.max(axis=0)
    volumes=[]
    for inst in shelters:
        sx,sy,sz=inst.get('scale',[1,1,1]);x,y,z=inst['position']
        footprint=box(float(lo[0]*sx),float(lo[2]*sz),float(hi[0]*sx),float(hi[2]*sz))
        footprint=translate(rotate(footprint,-inst.get('rotation',0),origin=(0,0),use_radians=True),x,z).buffer(.30)
        volumes.append((inst['id'],footprint,float(y+lo[1]*sy),float(y+hi[1]*sy+.30)))
    route_shapes=[LineString(p['points']).buffer(p.get('width',3)/2+.55) for p in s.paths if len(p.get('points',[]))>1 and (p['id'].startswith('PATH_') or p['id'].endswith('_sidewalk'))]
    route_tree=STRtree(route_shapes)
    building_area=unary_union(placed).buffer(.25) if placed else Polygon()
    forbidden=unary_union([lake.buffer(.6),pond.buffer(.6),roadmask,building_area])
    bounds=box(-1087,-815.5,1087,815.5)
    def projected(inst,ceiling=None,floor=None,x=None,z=None):
        pts=vertices(inst['prototype']);sx,sy,sz=inst.get('scale',[1,1,1])
        if ceiling is not None:
            height=(ceiling-inst['position'][1])/sy
            bottom=(floor-inst['position'][1])/sy if floor is not None else -float('inf')
            tri=pts.reshape(-1,3,3)
            selected=[pts[(pts[:,1]>=bottom)&(pts[:,1]<=height)]]
            # Project only the occupied vertical slab. Root geometry underneath
            # the shelter's foundation must not trigger a visible clash.
            for plane in [bottom,height]:
                if not np.isfinite(plane):continue
                for a,b in [(0,1),(1,2),(2,0)]:
                    first=tri[:,a];last=tri[:,b];cross=(first[:,1]<plane)!=(last[:,1]<plane)
                    first=first[cross];last=last[cross]
                    if len(first):
                        t=(plane-first[:,1])/(last[:,1]-first[:,1]);selected.append(first+(last-first)*t[:,None])
            pts=np.concatenate(selected)
        if not len(pts):return Polygon()
        p=MultiPoint(pts[:,[0,2]]).convex_hull
        p=scale_geometry(p,xfact=sx,yfact=sz,origin=(0,0))
        p=rotate(p,-inst.get('rotation',0),origin=(0,0),use_radians=True)
        return translate(p,inst['position'][0] if x is None else x,inst['position'][2] if z is None else z)
    conflicts=[]
    for inst in s.instances:
        if not inst['prototype'].startswith('tree_'):continue
        center=Point(inst['position'][0],inst['position'][2])
        if all(poly.distance(center)>9 for _,poly,_,_ in volumes):continue
        hit=[sid for sid,poly,bottom,top in volumes if projected(inst,top,bottom).intersects(poly)]
        if hit:conflicts.append((inst,hit))
    relocated=[];removed=[]
    for inst,hit in conflicts:
        old=list(inst['position']);accepted=None
        full_local=projected(inst)
        low_polys=[(poly,projected(inst,top,bottom)) for _,poly,bottom,top in volumes]
        for radius in [3,4.5,6,8,10,12,15]:
            for j in range(32):
                angle=j*math.tau/32;x=old[0]+math.cos(angle)*radius;z=old[2]+math.sin(angle)*radius
                footprint=trunk_shape(inst,x,z)
                if forbidden.intersects(footprint.buffer(.30)) or not bounds.covers(footprint):continue
                if any(route_shapes[int(k)].intersects(footprint) for k in route_tree.query(footprint)):continue
                if index.blocked(footprint.buffer(.6),inst['id']):continue
                if inst.get('region')=='REG_PARK' and not park.covers(footprint):continue
                if any(translate(low,x-old[0],z-old[2]).intersects(poly) for poly,low in low_polys):continue
                if translate(full_local,x-old[0],z-old[2]).intersects(building_area):continue
                accepted=(x,z,footprint);break
            if accepted:break
        if accepted:
            x,z,footprint=accepted;inst['position']=[x,old[1],z];index.set(inst['id'],footprint)
            relocated.append(dict(id=inst['id'],prototype=inst['prototype'],region=inst.get('region'),fromPosition=old,toPosition=list(inst['position']),shelters=hit))
        else:
            removed.append(dict(id=inst['id'],prototype=inst['prototype'],region=inst.get('region'),position=old,shelters=hit,reason='No legal planting within 15m after shelter, route, road, water, building and prop clearance checks.'))
    if removed:
        ids={r['id'] for r in removed};s.instances[:]=[inst for inst in s.instances if inst['id'] not in ids]
    unresolved=[]
    for inst in s.instances:
        if not inst['prototype'].startswith('tree_'):continue
        center=Point(inst['position'][0],inst['position'][2])
        if all(poly.distance(center)>9 for _,poly,_,_ in volumes):continue
        if any(projected(inst,top,bottom).intersects(poly) for _,poly,bottom,top in volumes):unresolved.append(inst['id'])
    return dict(detected=len(conflicts),relocated=relocated,removed=removed,unresolved=unresolved)


def clear_routes(s, lake, pond, placed, roadmask, park):
    """Return relocation evidence and explicit unresolved IDs, without deletion."""
    fixed_bounds={
        'bicycle':(-.34,-1.02,.34,1.02), 'shrub':(-.93,-.84,.93,.84),
        'park_fence':(-1.25,-.10,1.25,.10), 'park_pavilion':(-4.18,-4.18,4.18,4.18),
        'playground_swing':(-2.1,-1.12,2.1,1.12), 'playground_slide':(-.72,-1.35,.72,3.70),
        'soccer_goal':(-3.75,-1.97,3.75,.1), 'basketball_hoop':(-.98,-1.78,.98,.66),
        'tennis_net':(-6.5,-.09,6.5,.09),
    }
    movable={'bench','trash_bin','picnic_table','flower_planter','park_sign','bicycle','bike_rack','bollard','shrub','park_fence','street_lamp','traffic_light'}
    prefixes=('PATH_PARK','PATH_LAKE','PATH_POND','PATH_MARINA')
    paths=[p for p in s.paths if p['id'].startswith(prefixes) and len(p.get('points',[]))>1]
    if not paths:return dict(relocated=[],unresolved=[],counts={},notes='No relevant public paths in scene.')
    lines=[LineString(p['points']) for p in paths]
    corridors=[line.buffer(p.get('width',3)/2+.45,cap_style=1,join_style=1) for line,p in zip(lines,paths)]
    corridor_tree=STRtree(corridors)
    # Keep water and carriageways free. A conservative building setback also
    # protects projecting entrances and near-wall pedestrian space.
    buildings=unary_union(placed).buffer(.22) if placed else Polygon()
    water=unary_union([lake,pond]).buffer(.45)
    carriageways=roadmask.buffer(-5.3)
    forbidden=unary_union([buildings,water,carriageways])
    index=PlacementIndex();local_bounds={}
    def shape(inst,x=None,z=None,rotation=None):
        name=inst['prototype'];sx,_,sz=inst.get('scale',[1,1,1])
        if name in local_bounds:bounds=local_bounds[name]
        else:
            collision=s.prototypes.get(name,{}).get('collision')
            bounds=(-collision[0],-collision[1],collision[0],collision[1]) if collision else fixed_bounds.get(name)
            local_bounds[name]=bounds
        if bounds is None:return None
        p=box(bounds[0]*sx,bounds[1]*sz,bounds[2]*sx,bounds[3]*sz)
        angle=inst.get('rotation',0) if rotation is None else rotation
        # Three.js positive Y rotation is clockwise in the X/Z plan.
        p=rotate(p,-angle,origin=(0,0),use_radians=True)
        return translate(p,inst['position'][0] if x is None else x,inst['position'][2] if z is None else z)
    for inst in s.instances:
        p=shape(inst)
        if p is not None:index.set(inst['id'],p)
    def intrudes(p):
        return any(corridors[int(i)].intersects(p) for i in corridor_tree.query(p))
    candidates=[]
    for inst in s.instances:
        if inst['prototype'] not in movable and not inst['prototype'].startswith('tree_'):continue
        footprint=index.shapes.get(inst['id'])
        if footprint is not None and intrudes(footprint):candidates.append(inst)
    # Benches and tables get useful places first; bins and smaller props follow.
    priority={'bench':0,'picnic_table':1,'flower_planter':2,'trash_bin':3}
    candidates.sort(key=lambda inst:(priority.get(inst['prototype'],4),inst['id']))
    relocated=[];unresolved=[];counts=Counter()
    for inst in candidates:
        old=list(inst['position']);old_rotation=inst.get('rotation',0);origin=Point(old[0],old[2])
        route_index=min(range(len(lines)),key=lambda i:lines[i].distance(origin))
        line=lines[route_index];distance=line.project(origin)
        trial=[]
        # Parallel offsets favor a normal furniture strip beside the same route.
        for along in [0,-3,3,-6,6,-10,10]:
            station=max(0,min(line.length,distance+along));point=line.interpolate(station)
            a=line.interpolate(max(0,station-.5));b=line.interpolate(min(line.length,station+.5))
            dx,dz=b.x-a.x,b.y-a.y;length=math.hypot(dx,dz) or 1;nx,nz=-dz/length,dx/length
            for offset in [3,4.5,6,8,10,12,15]:
                for sign in [1,-1]:trial.append((point.x+nx*offset*sign,point.y+nz*offset*sign))
        for radius in [3,4.5,6,8,10,12,15]:
            for j in range(20):
                angle=j*math.tau/20
                trial.append((old[0]+math.cos(angle)*radius,old[2]+math.sin(angle)*radius))
        trial=[p for p in trial if 2.9<=math.dist(p,(old[0],old[2]))<=15.01]
        trial.sort(key=lambda p:math.dist(p,(old[0],old[2])))
        accepted=None
        for x,z in trial:
            rotation=old_rotation
            if inst['prototype']=='bench':
                facing=line.interpolate(line.project(Point(x,z)))
                rotation=math.atan2(facing.x-x,facing.y-z)
            footprint=shape(inst,x,z,rotation)
            if footprint is None or intrudes(footprint) or forbidden.intersects(footprint.buffer(.12)):continue
            if index.blocked(footprint.buffer(.25),inst['id']):continue
            # Stay within the soft exploration boundary as well as within the
            # local 15m placement neighborhood.
            if not box(-1087.0,-815.5,1087.0,815.5).covers(footprint):continue
            accepted=(x,z,rotation,footprint);break
        if accepted is None:
            unresolved.append(dict(id=inst['id'],prototype=inst['prototype'],position=old,path=paths[route_index]['id']))
            continue
        x,z,rotation,footprint=accepted
        inst['position']=[x,old[1],z];inst['rotation']=rotation
        index.set(inst['id'],footprint)
        relocated.append(dict(id=inst['id'],prototype=inst['prototype'],fromPosition=old,toPosition=list(inst['position']),fromRotation=old_rotation,toRotation=rotation,path=paths[route_index]['id'],distanceM=round(math.hypot(x-old[0],z-old[2]),3)))
        counts[inst['prototype']]+=1
    shelter_clearance=_clear_shelter_trees(s,lake,pond,placed,roadmask,park,index,shape)
    return dict(shelterTreeClearance=shelter_clearance,relocated=relocated,unresolved=unresolved,counts=dict(counts),checkedPaths=len(paths),detectedIntrusions=len(candidates),notes='Small furniture and trunk collisions moved locally. Fountains, buildings, sports assemblies and pavilions remain fixed. Every accepted footprint clears route width plus 0.45m, water, carriageways, buildings and other solid props.')
