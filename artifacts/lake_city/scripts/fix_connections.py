"""Connected pond bridges and marina approaches for the shared city scene.

Call build_connections(scene, pond, lake) after the base park and marina surfaces
have been laid out, before vegetation clearance masks are derived. This only
adds geometry, path records and conservative overlapping support rectangles.
"""
import math
import numpy as np
from shapely.geometry import LineString, Point, box
from shapely.ops import nearest_points, unary_union
from citylib import world
from landscape_assets import box as box_part, tube


def _lines(geometry):
    if geometry.is_empty:return []
    if geometry.geom_type=='LineString':return [geometry]
    if hasattr(geometry,'geoms'):
        return [line for g in geometry.geoms for line in _lines(g)]
    return []


def _support(scene, footprint, height):
    # Long horizontal strips keep the support query small. The interior raster
    # margin and slight overlap account for the controller's inset on each box.
    interior=footprint.buffer(-.55)
    if interior.is_empty:return 0
    minx,minz,maxx,maxz=interior.bounds
    step=1.0; rows=[]
    for z in np.arange(math.floor(minz),math.ceil(maxz),step):
        start=None;end=None
        for x in np.arange(math.floor(minx),math.ceil(maxx)+step,step):
            accepted=x<maxx and interior.covers(box(x,z,x+step,z+step))
            if accepted:
                if start is None:start=x
                end=x+step
            elif start is not None:
                rows.append([float(start-.64),float(z-.64),float(end+.64),float(z+step+.64)])
                start=end=None
    merged=[]
    for row in rows:
        match=next((m for m in reversed(merged) if m[0]==row[0] and m[2]==row[2] and row[1]<=m[3]),None)
        if match is not None:match[3]=max(match[3],row[3])
        else:merged.append(row)
    scene.walkSurfaces.extend(dict(bounds=bounds,height=height) for bounds in merged)
    return len(merged)


def _deck(scene, name, line, width, height, stage, region, rails=False, junctions=None):
    footprint=line.buffer(width/2,cap_style=2,join_style=1)
    scene.surface(footprint,height-.04,'connection_deck_base',stage,region)
    parts=[]
    # Every board follows the same sampled curve as the visible deck surface.
    for i,distance in enumerate(np.arange(.12,line.length-.05,.34)):
        p=line.interpolate(distance);q=line.interpolate(min(line.length,distance+.1))
        tangent=math.atan2(q.x-p.x,q.y-p.y)
        box_part(parts,f'{name}_board_{i:04d}',[width,.075,.323],[p.x,height-.01,p.y],
                 'connection_wood_a' if i%5 else 'connection_wood_b',[0,tangent,0])
    if rails:
        exclusion=junctions if junctions is not None else Point(0,0).buffer(0)
        for side in ['left','right']:
            rail=line.parallel_offset(width/2-.13,side,join_style=1).difference(exclusion)
            for rail_index,segment in enumerate(_lines(rail)):
                if segment.length<.8:continue
                sampled=[segment.interpolate(float(d)) for d in np.arange(0,segment.length,2.8)]
                sampled.append(segment.interpolate(segment.length))
                for j,p in enumerate(sampled):
                    tube(parts,f'{name}_{side}_{rail_index}_post_{j}',[p.x,height-.15,p.y],[p.x,height+1.11,p.y],.044,'connection_metal',7)
                for j,(a,b) in enumerate(zip(sampled,sampled[1:])):
                    for level in [.38,1.11]:
                        tube(parts,f'{name}_{side}_{rail_index}_rail_{j}',[a.x,height+level,a.y],[b.x,height+level,b.y],.031,'connection_metal',7)
    scene.prototype(name,parts)
    scene.add(name,[0,0,0],region=region,stage=stage,id=name.upper())
    scene.paths.append(dict(id='PATH_'+name.upper(),points=list(line.coords),width=width,closed=False,stage=stage))
    supports=_support(scene,footprint,height+.028)
    return dict(name=name,lengthM=round(line.length,2),widthM=width,supportRectangles=supports)


def build_connections(scene, pond, lake):
    """Add physical and walkable surfaces; return a compact construction report."""
    for name,color in [('connection_deck_base','#655842'),('connection_wood_a','#ad9571'),('connection_wood_b','#a18a66'),('connection_metal','#485451')]:
        scene.material(name,color,roughness=.82,metalness=.22 if name=='connection_metal' else 0)
    result=[]
    existing_paths=list(scene.paths)
    bridge_path=next((p for p in existing_paths if p['id']=='PATH_PARK_CROSS_367'),None)
    if bridge_path:
        line=LineString(bridge_path['points'])
        crossing=line.intersection(pond.buffer(9))
        other_routes=[]
        for p in existing_paths:
            if p['id']==bridge_path['id'] or not p['id'].startswith('PATH_PARK_'):continue
            other_routes.append(LineString(p['points']).buffer(p['width']/2+1.1))
        openings=unary_union(other_routes) if other_routes else Point(0,0).buffer(0)
        for index,segment in enumerate(_lines(crossing)):
            if segment.length<3:continue
            result.append(_deck(scene,f'pond_bridge_{index+1:02d}',segment,6.0,.40,4,'REG_PARK',True,openings))
    # Some organic park paths skim the bank. Bridge only portions actually over
    # water, with short bank overlap, to maintain those existing traced routes.
    for p in existing_paths:
        if not p['id'].startswith('PATH_PARK_') or p['id']=='PATH_PARK_CROSS_367':continue
        line=LineString(p['points'])
        if line.intersection(pond).length<1.0:continue
        for index,segment in enumerate(_lines(line.intersection(pond.buffer(4)))):
            if segment.length<1.0 or not segment.intersects(pond):continue
            name=p['id'].replace('PATH_PARK_','pond_walk_').lower()+f'_{index+1:02d}'
            openings=unary_union([LineString(q['points']).buffer(q['width']/2+1.1) for q in existing_paths if q['id']!=p['id'] and q['id'].startswith('PATH_PARK_')])
            result.append(_deck(scene,name,segment,p['width']+.5,.40,4,'REG_PARK',True,openings))
    def point(u,v):
        p=world(u,v);return (p[0],p[2])
    spine=LineString([point(105,408),point(105,480)])
    fingers=[LineString([point(104,v),point(153,v)]) for v in [420,438,455,471]]
    shore_loop=LineString(lake.buffer(11,resolution=8).exterior.coords)
    target=Point(point(105,444));shore=nearest_points(shore_loop,target)[0]
    approach=LineString([shore.coords[0],target.coords[0]])
    openings=unary_union([f.buffer(3.4) for f in fingers]+[approach.buffer(3.8)])
    result.append(_deck(scene,'marina_spine',spine,12.0,.40,9,'REG_WATERFRONT',True,openings))
    minx,minz,maxx,maxz=spine.bounds
    scene.walkSurfaces.append(dict(bounds=[minx-5.5,minz-.5,maxx+5.5,maxz+.5],height=.428))
    for index,line in enumerate(fingers):
        result.append(_deck(scene,f'marina_finger_{index+1:02d}',line,4.2,.40,9,'REG_WATERFRONT'))
    approach_openings=unary_union([spine.buffer(6.8),shore_loop.buffer(3.5)])
    result.append(_deck(scene,'marina_shore_approach',approach,5.4,.40,9,'REG_WATERFRONT',True,approach_openings))
    return result
