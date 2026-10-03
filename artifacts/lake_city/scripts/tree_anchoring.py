"""Anchor tree soil datums to actual rendered surface triangles.

Call anchor_trees(scene) after all placements/clearance moves and surface
construction, immediately before Scene.flush(). Only tree instance Y changes.
The tree prototypes use Y=0 for the soil collar and extend 0.52m below it.
"""
from collections import Counter
import numpy as np
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree
from citylib import primitive, _rotation

GROUND_MATERIALS={
    'forest_floor','grass','lawn','verge','garden_soil','wet_shore','shore_sand',
    'plaza','sidewalk','path','cycle_path','asphalt','yard_grass','yard_soil',
    'yard_gravel','yard_paving','yard_parking','sports_turf','sports_blue','sports_red',
}


def anchor_trees(scene, embed_depth=.06):
    """Plant roots below visible ground without changing X/Z, scale or canopy."""
    polygons=[];heights=[];roles=[]
    def add_parts(parts,instance=None):
        for part in parts:
            material=part.get('material')
            if material not in GROUND_MATERIALS or part.get('shape')!='mesh':continue
            positions,_=primitive(part)
            if not len(positions):continue
            if instance:
                sx,sy,sz=instance.get('scale',[1,1,1])
                positions=positions*np.array([sx,sy,sz])
                positions=positions@_rotation([0,instance.get('rotation',0),0]).T+instance['position']
            # Surface batches are planar; geometry from buildings/props is never
            # considered, even when their material happens to share a name.
            if float(np.ptp(positions[:,1]))>1e-4:continue
            y=float(positions[0,1])
            for tri in positions.reshape(-1,3,3):
                poly=Polygon([(float(v[0]),float(v[2])) for v in tri])
                if poly.area<=1e-8:continue
                polygons.append(poly);heights.append(y);roles.append(material)
    for parts in scene.surface_parts.values():add_parts(parts)
    # Also supports inspecting a previously flushed source scene in memory.
    for inst in scene.instances:
        if inst['prototype'].startswith('surfaces_'):
            add_parts(scene.prototypes[inst['prototype']].get('parts',[]),inst)
    if not polygons:
        return dict(anchoredCount=0,unresolvedIds=[i['id'] for i in scene.instances if i['prototype'].startswith('tree_')],reason='No rendered ground triangles available.')
    index=STRtree(polygons);unresolved=[];sampled=[];by_ground=Counter();old_gaps=[];delta=[]
    tree_count=0;flare_clearances=[];root_embed=[]
    local_bounds={}
    for name,prototype in scene.prototypes.items():
        if not name.startswith('tree_'):continue
        trunk=[];flares=[]
        for part in prototype.get('parts',[]):
            if part.get('name')=='rooted_trunk':trunk.append(primitive(part)[0])
            elif part.get('name','').startswith('root_flare_'):flares.append(primitive(part)[0])
        if trunk and flares:
            local_bounds[name]=(float(np.concatenate(trunk)[:,1].min()),float(np.concatenate(flares)[:,1].max()))
    for inst in scene.instances:
        if not inst['prototype'].startswith('tree_'):continue
        tree_count+=1;x,old_y,z=inst['position'];point=Point(x,z)
        hits=[int(i) for i in index.query(point) if polygons[int(i)].covers(point)]
        if not hits:
            # Numerical edge tolerance is millimetric, never a substitute for
            # a missing ground surface or for water holes in the terrain.
            hits=[int(i) for i in index.query(point.buffer(.001)) if polygons[int(i)].distance(point)<.001]
        if not hits:unresolved.append(inst['id']);continue
        hit=max(hits,key=lambda i:heights[i]);ground_y=heights[hit]
        new_y=ground_y-float(embed_depth)
        inst['position']=[x,new_y,z]
        by_ground[f'{roles[hit]}@{ground_y:.3f}']+=1
        old_gaps.append(old_y-ground_y);delta.append(new_y-old_y)
        sy=inst.get('scale',[1,1,1])[1]
        if inst['prototype'] in local_bounds:
            trunk_min,flare_max=local_bounds[inst['prototype']]
            flare_clearances.append(new_y+flare_max*sy-ground_y)
            root_embed.append(ground_y-(new_y+trunk_min*sy))
        if len(sampled)<12 or old_y-ground_y>.25 and len(sampled)<20:
            sampled.append(dict(id=inst['id'],prototype=inst['prototype'],groundMaterial=roles[hit],groundY=round(ground_y,6),oldY=old_y,newY=round(new_y,6),positionXZ=[x,z]))
    return dict(treeCount=tree_count,anchoredCount=tree_count-len(unresolved),unresolvedIds=unresolved,
        embedDepthM=embed_depth,onlyInstanceYChanged=True,groundSurfaceCounts=dict(by_ground),
        previousDatumAboveGroundRangeM=[round(min(old_gaps),6),round(max(old_gaps),6)] if old_gaps else [],
        instanceYDeltaRangeM=[round(min(delta),6),round(max(delta),6)] if delta else [],
        maximumStructuralRootAboveSoilM=round(max(flare_clearances),6) if flare_clearances else None,
        trunkBelowSoilRangeM=[round(min(root_embed),6),round(max(root_embed),6)] if root_embed else [],
        samples=sampled,
        notes='Soil contact sampled from actual rendered terrain, plaza and path triangles; roots remain below ground. X/Z, rotation, scale, IDs and all canopy source geometry are preserved.')
