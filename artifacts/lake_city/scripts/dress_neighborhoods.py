"""Purposeful entrance, garden and parking assemblies for occupied city parcels.

Call after landscape prototype registration and before Scene.flush(). All
placements consume actual building footprints and the existing street network.
"""
import math
import random
from collections import Counter, defaultdict
from shapely.geometry import Point, LineString, Polygon, box
from shapely.affinity import rotate
from shapely.ops import unary_union, nearest_points, substring
from shapely.strtree import STRtree
from landscape_assets import box as box_part


def _poly(center, width, depth, direction=(0,1)):
    x,z=center;dx,dz=direction;tx,tz=dz,-dx
    return Polygon([(x+tx*a+dx*b,z+tz*a+dz*b) for a,b in [(-width/2,-depth/2),(width/2,-depth/2),(width/2,depth/2),(-width/2,depth/2)]])


def _lines(geometry):
    if geometry.is_empty:return []
    if geometry.geom_type=='LineString':return [geometry]
    return [l for part in getattr(geometry,'geoms',[]) for l in _lines(part)]


class Occupied:
    def __init__(self):self.cells=defaultdict(list)
    def keys(self,p):
        a,b,c,d=p.bounds
        return [(x,z) for x in range(math.floor(a/12),math.floor(c/12)+1) for z in range(math.floor(b/12),math.floor(d/12)+1)]
    def intersects(self,p):
        seen=set()
        for key in self.keys(p):
            for index,q in self.cells[key]:
                if index in seen:continue
                seen.add(index)
                if q.intersects(p):return True
        return False
    def add(self,p):
        identity=id(p)
        for key in self.keys(p):self.cells[key].append((identity,p))


def dress_neighborhoods(s, roadmask, placed, lake, pond, park):
    rng=random.Random(724511);counts=Counter();parts=[]
    for name,color in [('yard_grass','#778b51'),('yard_soil','#625442'),('yard_gravel','#b6ac91'),('yard_paving','#c8c2ad'),('yard_parking','#62676a'),('yard_white','#dedbc9'),('yard_edging','#aeb09e')]:
        s.material(name,color,roughness=.91)
    buildings=list(s.buildings)
    footprints=[Polygon(b['footprint']).buffer(.04) for b in buildings]
    building_tree=STRtree(footprints)
    building_protos={b['prototype'] for b in buildings}
    solids=[]
    for inst in s.instances:
        if inst['prototype'] in building_protos:continue
        col=s.prototypes.get(inst['prototype'],{}).get('collision')
        if not col:continue
        x,_,z=inst['position'];sx,_,sz=inst.get('scale',[1,1,1]);hx,hz=col[0]*sx,col[1]*sz
        p=box(x-hx-.20,z-hz-.20,x+hx+.20,z+hz+.20)
        solids.append(rotate(p,inst.get('rotation',0),origin=(x,z),use_radians=True))
    solid_tree=STRtree(solids) if solids else None
    protected=[lake.buffer(6),pond.buffer(3),park.buffer(1)]
    # Respect playing surfaces when finding sports-campus parking.
    for key,source_parts in s.surface_parts.items():
        for part in source_parts:
            if part.get('material') not in ['sports_turf','sports_blue','sports_red']:continue
            if part.get('vertices'):
                protected.append(Polygon([(v[0],v[2]) for v in part['vertices']]).convex_hull.buffer(2))
    protection=unary_union(protected)
    road_inner=roadmask.buffer(-1.5)
    sidewalk_paths=[p for p in s.paths if p['id'].startswith('RD_') and p['id'].endswith('_sidewalk') and len(p['points'])>1]
    sidewalks=[LineString(p['points']) for p in sidewalk_paths]
    approach_polys=[]
    all_paths=[p for p in s.paths if len(p.get('points',[]))>1]
    unconnected=[]

    def hits(tree,polys,shape):
        if tree is None:return False
        return any(polys[int(i)].intersects(shape) for i in tree.query(shape))

    def clear_route(line,width,owner=None,allow_road=False):
        envelope=line.buffer(width/2+.16,cap_style=2,join_style=2)
        if envelope.intersects(protection):return False
        if hits(building_tree,footprints,envelope):return False
        if hits(solid_tree,solids,envelope):return False
        return True

    def to_sidewalk(start, lead, direction, width=1.8, max_length=76):
        if not sidewalks:return None
        nearest=sorted(range(len(sidewalks)),key=lambda i:sidewalks[i].distance(Point(start)))[:7]
        dx,dz=direction;tx,tz=dz,-dx;candidates=[]
        for index in nearest:
            target=nearest_points(Point(lead),sidewalks[index])[1]
            target=(target.x,target.y)
            # Prefer a short right-angle garden path, with a short axial lead.
            points_sets=[[start,lead,target],[start,lead,(target[0],lead[1]),target],[start,lead,(lead[0],target[1]),target]]
            for shift in [-3.2,3.2,-6.0,6.0,-10.0,10.0]:
                side=(lead[0]+tx*shift,lead[1]+tz*shift)
                points_sets.extend([[start,lead,side,target],[start,lead,side,(target[0],side[1]),target],[start,lead,side,(side[0],target[1]),target]])
            for coordinates in points_sets:
                coords=[coordinates[0]]
                for p in coordinates[1:]:
                    if math.dist(p,coords[-1])>.04:coords.append(p)
                if len(coords)<2:continue
                line=LineString(coords)
                if line.length>max_length or not line.is_simple or not line.is_valid:continue
                # Sidewalk records represent one street side. Stop at the first
                # visible sidewalk reached, avoiding a driveway across traffic.
                pieces=_lines(line.intersection(road_inner))
                if pieces:
                    distance=min(line.project(Point(seg.coords[0])) for seg in pieces)
                    if distance>.3:line=substring(line,0,min(line.length,distance+.65))
                if line.length<.35 or not clear_route(line,width):continue
                candidates.append((line.length+.4*len(coords),line,index))
            if candidates and candidates[0][0]<10:break
        return min(candidates,key=lambda c:c[0])[1:] if candidates else None

    # Complete entrances first so every later planting decision sees the routes.
    for i,(b,footprint) in enumerate(zip(buildings,footprints)):
        if b['region']=='REG_PARK':continue
        direction=b.get('frontageDirection',[0,1]);dx,dz=direction
        entrance=b.get('entrance',[footprint.centroid.x,footprint.bounds[3]])
        start=(entrance[0]+dx*1.2,entrance[1]+dz*1.2)
        lead=(entrance[0]+dx*2.0,entrance[1]+dz*2.0)
        width=1.8 if b['prototype'].startswith(('house_','townhouse_')) else 2.6
        if width>2:
            start=(entrance[0]+dx*1.65,entrance[1]+dz*1.65);lead=(entrance[0]+dx*2.7,entrance[1]+dz*2.7)
        selected=to_sidewalk(start,lead,direction,width)
        if selected is None and width>2:
            width=1.8
            selected=to_sidewalk(start,lead,direction,width)
        if selected is None:unconnected.append(b['id']);continue
        line,index=selected
        coords=[tuple(entrance),*list(line.coords)]
        approach=LineString(coords)
        p=approach.buffer(width/2,cap_style=2,join_style=2)
        s.surface(p,.19,'yard_paving',9,b['region'])
        path=dict(id=f'PATH_ENTRANCE_{b["id"]}',points=list(approach.coords),width=width,closed=False,stage=9,connectsTo=sidewalk_paths[index]['id'])
        s.paths.append(path);all_paths.append(path);approach_polys.append(p);counts['connectedEntrances']+=1
    routes=[LineString(p['points']).buffer(p.get('width',2)/2+.70) for p in all_paths if not p['id'].startswith('RD_')]
    route_tree=STRtree(routes) if routes else None
    occupied=Occupied()
    # Planting and furniture avoid existing trunks, solid props, building
    # projections, all public routes, roads, water and protected park lawns.
    def clear(shape,reserve=False):
        if shape.intersects(protection) or shape.intersects(roadmask):return False
        if hits(building_tree,footprints,shape.buffer(.20)):return False
        if hits(solid_tree,solids,shape.buffer(.10)):return False
        if hits(route_tree,routes,shape):return False
        if occupied.intersects(shape):return False
        if reserve:occupied.add(shape)
        return True
    def prop(name,x,z,direction=(0,1),scale=1.0):
        dims={'shrub':(1.9,1.7),'flower_planter':(1.5,.75),'park_fence':(2.5,.18),'bench':(1.9,.85),'trash_bin':(.65,.65)}
        if name not in s.prototypes:return False
        w,d=dims[name];shape=_poly((x,z),w*scale+.18,d*scale+.18,direction)
        if not clear(shape,True):return False
        s.add(name,[x,.18,z],rotation=math.atan2(direction[0],direction[1]),scale=[scale]*3,region='REG_NEIGHBORHOOD_DETAIL',stage=9)
        counts[name]+=1;return True
    def garden_pad(center,w,d,direction,region):
        shape=_poly(center,w,d,direction)
        if not clear(shape):return False
        s.surface(shape,.171,'yard_grass',9,region)
        # Fine flush gravel border, without adding a navigation obstacle.
        s.surface(shape.boundary.buffer(.095),.182,'yard_gravel',9,region)
        counts['gardenPads']+=1
        return True

    for i,(b,footprint) in enumerate(zip(buildings,footprints)):
        if b['region']=='REG_PARK':continue
        dx,dz=b.get('frontageDirection',[0,1]);direction=(dx,dz);tx,tz=dz,-dx
        x,z=b.get('entrance',[footprint.centroid.x,footprint.bounds[3]])
        proto=b['prototype'];cx,cz=footprint.centroid.x,footprint.centroid.y
        minx,minz,maxx,maxz=footprint.bounds
        fw=(maxx-minx)*abs(tx)+(maxz-minz)*abs(tz)
        fd=(maxx-minx)*abs(dx)+(maxz-minz)*abs(dz)
        if proto.startswith(('house_','townhouse_')):
            # Two planted frontage strips leave an explicit central gate.
            for sign in [-1,1]:
                offset=max(2.8,min(4.1,fw*.27))
                installed=False
                for dist in [2.4,4.3,6.3]:
                    center=(x+dx*dist+tx*sign*offset,z+dz*dist+tz*sign*offset)
                    if not garden_pad(center,3.2,1.7,direction,b['region']):continue
                    for j in [-.76,.76]:
                        if prop('shrub',center[0]+tx*j,center[1]+tz*j,direction,.62):installed=True
                    break
                if not installed and i%3==0:
                    prop('flower_planter',x+dx*.78+tx*sign*2.8,z+dz*.78+tz*sign*2.8,direction)
            # Short street-facing fence wings keep a 3.8m central gateway.
            if i%3==0:
                for sign in [-1,1]:
                    prop('park_fence',x+dx*5.8+tx*sign*3.2,z+dz*5.8+tz*sign*3.2,direction,.88)
            # Rear garden planting provides a private courtyard identity.
            if i%2==0:
                rear=(cx-dx*(fd/2+3.2),cz-dz*(fd/2+3.2))
                if garden_pad(rear,min(7.2,fw*.65),3.4,direction,b['region']):
                    for j in [-2.15,0,2.15]:prop('shrub',rear[0]+tx*j,rear[1]+tz*j,direction,.74)
        elif proto.startswith(('apartment_','tower_')) and i%3==0:
            # A restrained common garden belongs to a real apartment/tower court.
            for side in [-1,1]:
                center=(cx+tx*side*(fw/2+7),cz+tz*side*(fw/2+7))
                if not garden_pad(center,8.5,10.5,direction,b['region']):continue
                s.surface(_poly(center,2.4,10.5,direction),.188,'yard_paving',9,b['region'])
                for a in [-3.0,3.0]:
                    for c in [-3.6,0,3.6]:
                        if a>0 and c==0:continue
                        prop('shrub',center[0]+tx*a+dx*c,center[1]+tz*a+dz*c,direction,.90)
                prop('bench',center[0]+tx*2.9,center[1]+tz*2.9,(-tx,-tz))
                garden_line=LineString([(center[0]-dx*5.25,center[1]-dz*5.25),(center[0]+dx*5.25,center[1]+dz*5.25)])
                s.paths.append(dict(id=f'PATH_GARDEN_{b["id"]}',points=list(garden_line.coords),width=2.4,closed=False,stage=9))
                counts['pocketGardens']+=1;break
        elif proto.startswith(('commercial_','sports_hall','school','library','hotel','rail_station')):
            for sign in [-1,1]:
                prop('flower_planter',x+dx*2.2+tx*sign*min(fw*.3,6),z+dz*2.2+tz*sign*min(fw*.3,6),direction)
            if proto.startswith(('commercial_','sports_hall','hotel')):
                # Small off-street parking groups, with a connected apron.
                for side in [-1,1]:
                    center=(cx+tx*side*(fw/2+10.5),cz+tz*side*(fw/2+10.5))
                    pad=_poly(center,14.5,12.0)
                    if not clear(pad):continue
                    drive_start=(center[0],center[1]+6.0)
                    selected=to_sidewalk(drive_start,(drive_start[0],drive_start[1]+2.0),(0,1),3.7,58)
                    if selected is None:continue
                    driveway,_=selected
                    if hits(route_tree,routes,driveway.buffer(1.85)) or occupied.intersects(driveway.buffer(1.85)):continue
                    s.surface(pad,.176,'yard_parking',9,b['region']);s.surface(driveway.buffer(1.85,cap_style=2),.178,'yard_parking',9,b['region'])
                    for j in range(6):
                        xx=center[0]-6.7+j*2.68
                        box_part(parts,'parking_stall_line',[.09,.025,5.65],[xx,.201,center[1]-2.95],'yard_white')
                    box_part(parts,'parking_front_line',[13.4,.025,.09],[center[0],.201,center[1]-.12],'yard_white')
                    for j in range(5):
                        if rng.random()<.68:
                            car='car_sedan' if j%3 else 'car_suv'
                            if car in s.prototypes:s.add(car,[center[0]-5.36+j*2.68,.19,center[1]-2.95],rotation=math.pi,region='REG_PARKING',stage=9);counts['parkedCars']+=1
                    occupied.add(pad);occupied.add(driveway.buffer(2.0));counts['parkingCourts']+=1;break
    if parts:
        s.prototype('neighborhood_parking_markings',parts)
        s.add('neighborhood_parking_markings',[0,0,0],region='REG_NEIGHBORHOOD_DETAIL',stage=9)
    counts['eligibleBuildings']=sum(b['region']!='REG_PARK' for b in buildings)
    counts['unconnectedEntrances']=len(unconnected)
    counts['uniqueMarkingTriangles']=len(parts)*12
    return dict(counts=counts,unconnectedBuildingIds=unconnected,notes='Added only verified clear routes and occupied-parcel dressing. Closed building entrances terminate at their threshold; unresolved approaches are explicitly listed.')
