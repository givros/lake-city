"""Read-only geometric and inventory audit of a finished Lake City export.

Inputs are never changed. The only output is validation_metrics.json (or --output).
This checks measurable source/transfer/layout facts. It does not claim that these
facts prove visual similarity, controller traversal, lighting or frame rate.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def rounded(value, digits=4):
    return round(float(value), digits)


def safe_polygon(points):
    p = Polygon(points)
    return p if p.is_valid else p.buffer(0)


def region_box(pixels, scale=1.5):
    a,b,c,d = pixels
    return box((a-725)*scale, (b-544)*scale, (c-725)*scale, (d-544)*scale)


def transformed_rect(x0,z0,x1,z1,instance):
    c=math.cos(instance.get('rotation',0));s=math.sin(instance.get('rotation',0))
    sx,_,sz=instance.get('scale',[1,1,1]);px,_,pz=instance['position']
    pts=[]
    for x,z in [(x0,z0),(x1,z0),(x1,z1),(x0,z1)]:
        x*=sx;z*=sz
        pts.append((px+c*x+s*z,pz-s*x+c*z))
    return Polygon(pts)


def audit(root, full_geometry=True):
    started=time.perf_counter()
    city_path=root/'viewer/public/assets/city.json'
    binary_path=root/'viewer/public/assets/geometry.bin'
    city=load(city_path)
    spec=load(root/'scene_spec.json')
    source=load(root/'source_scene.json')
    registry=load(root/'asset_registry.json')
    architecture=load(root/'architecture_catalog.json')['prototypes']
    buf=binary_path.read_bytes()
    stage=int(city.get('stats',{}).get('stage',0))
    report={
        'scope':'Measured geometry, transfer, inventory and spatial layout. No visual score or controller result is inferred.',
        'stage':stage,
        'complete_stage':stage>=10,
        'source_files':{
            'city_json':str(city_path),'geometry_bin':str(binary_path),
            'scene_spec':str(root/'scene_spec.json'),'source_scene':str(root/'source_scene.json')},
        'checks':{},'warnings':[],'failures':[]}
    checks=report['checks']
    def fail(msg):report['failures'].append(msg)
    def warn(msg):report['warnings'].append(msg)

    instances=city['instances'];prototypes=city['prototypes']
    counts=Counter(i['prototype'] for i in instances)
    source_counts=Counter(i['prototype'] for i in source['instances'])
    duplicate_ids=[k for k,v in Counter(i['id'] for i in instances).items() if v>1]
    missing_prototypes=sorted(set(counts)-set(prototypes))
    missing_materials=sorted({m['material'] for p in prototypes.values() for m in p['meshes']}-set(city['materials']))
    inventory={
        'instances':len(instances),'prototypes':len(prototypes),'materials':len(city['materials']),
        'by_prototype':dict(sorted(counts.items())),
        'by_region':dict(sorted(Counter(i.get('region','UNCLASSIFIED') for i in instances).items())),
        'source_instances_identical':instances==source['instances'],
        'source_inventory_identical':counts==source_counts,
        'registry_inventory_identical':dict(counts)==registry.get('counts'),
        'duplicate_instance_ids':duplicate_ids,'missing_prototypes':missing_prototypes,
        'missing_materials':missing_materials}
    checks['inventory']=inventory
    if missing_prototypes or missing_materials or duplicate_ids:
        fail('Runtime inventory has missing references or duplicate IDs.')
    if not all(inventory[k] for k in ['source_instances_identical','source_inventory_identical','registry_inventory_identical']):
        fail('Runtime, source and asset-registry instance inventories disagree.')

    # Validate raw buffers and record actual prototype bounds without triangle-pair work.
    local_bounds={};triangles={};buffer_errors=[];normal_errors=[]
    for name,p in prototypes.items():
        lows=[];highs=[];triangle_count=0
        for mi,m in enumerate(p['meshes']):
            count=m['positionCount'];icount=m['indexCount']
            ranges=[(m['positionOffset'],count*4),(m['normalOffset'],count*4),(m['indexOffset'],icount*4)]
            if count%3 or icount%3 or any(off%4 or off<0 or off+length>len(buf) for off,length in ranges):
                buffer_errors.append(f'{name}/{mi}: invalid range/alignment');continue
            pos=np.frombuffer(buf,dtype='<f4',count=count,offset=m['positionOffset']).reshape(-1,3)
            normals=np.frombuffer(buf,dtype='<f4',count=count,offset=m['normalOffset']).reshape(-1,3)
            indices=np.frombuffer(buf,dtype='<u4',count=icount,offset=m['indexOffset'])
            if not np.isfinite(pos).all() or not np.isfinite(normals).all():buffer_errors.append(f'{name}/{mi}: nonfinite value')
            if len(indices) and int(indices.max())>=len(pos):buffer_errors.append(f'{name}/{mi}: invalid index')
            if not np.allclose(np.linalg.norm(normals,axis=1),1,atol=2e-4):normal_errors.append(f'{name}/{mi}')
            if len(pos):lows.append(pos.min(axis=0));highs.append(pos.max(axis=0))
            triangle_count+=icount//3
        if lows:local_bounds[name]=(np.min(lows,axis=0),np.max(highs,axis=0))
        triangles[name]=triangle_count
    unique_triangles=sum(triangles.values())
    total_triangles=sum(triangles.get(i['prototype'],0) for i in instances)
    checks['geometry_buffer']={
        'binary_bytes':len(buf),'binary_sha256':hashlib.sha256(buf).hexdigest(),
        'unique_triangles':unique_triangles,'instanced_triangles':total_triangles,
        'triangle_counts_match_manifest':unique_triangles==city['stats']['uniqueTriangles'] and total_triangles==city['stats']['visibleTriangles'],
        'buffer_errors':buffer_errors,'nonunit_normal_meshes':normal_errors,
        'positions_and_normals_finite':not any('nonfinite' in e for e in buffer_errors)}
    if buffer_errors or normal_errors:fail('Geometry buffer validation failed.')
    if not checks['geometry_buffer']['triangle_counts_match_manifest']:fail('Manifest triangle counts differ from measured geometry.')

    # Reproduce the export hash. Older exporter versions appended water holes after
    # hashing; report that narrower coverage honestly if that is the only match.
    payload=dict(city);declared_hash=payload.get('sourceHash','');payload['sourceHash']=''
    def signature(data):return hashlib.sha256(buf+json.dumps(data,sort_keys=True).encode()).hexdigest()
    complete_hash=signature(payload)
    old_payload=dict(payload);old_payload.pop('waterHolePolygons',None)
    legacy_hash=signature(old_payload)
    full_match=complete_hash==declared_hash;legacy_match=legacy_hash==declared_hash
    checks['build_hash']={
        'declared_source_hash':declared_hash,'recomputed_complete_hash':complete_hash,
        'complete_manifest_hash_matches':full_match,
        'legacy_hash_excluding_water_holes_matches':legacy_match,
        'registry_source_hash_matches':registry.get('sourceHash')==declared_hash,
        'source_scene_sha256':hashlib.sha256((root/'source_scene.json').read_bytes()).hexdigest()}
    if not full_match and legacy_match:warn('Export hash matches geometry and the original payload, but excludes appended waterHolePolygons.')
    elif not full_match:fail('Declared build hash cannot be reproduced from the final export.')
    if registry.get('sourceHash')!=declared_hash:fail('Asset registry references a different build hash.')

    if full_geometry:
        from citylib import primitive
        mismatches=[];matched_meshes=0
        for name,p in prototypes.items():
            source_proto=source['prototypes'].get(name)
            if source_proto is None:mismatches.append({'prototype':name,'reason':'missing source prototype'});continue
            grouped=defaultdict(list)
            for part in source_proto['parts']:grouped[part['material']].append(part)
            for m in p['meshes']:
                parts=grouped.get(m['material'],[])
                arrays=[primitive(part) for part in parts]
                if not arrays:mismatches.append({'prototype':name,'material':m['material'],'reason':'missing source material group'});continue
                positions=np.concatenate([a[0] for a in arrays]);normals=np.concatenate([a[1] for a in arrays])
                target_positions=np.frombuffer(buf,dtype='<f4',count=m['positionCount'],offset=m['positionOffset']).reshape(-1,3)
                target_normals=np.frombuffer(buf,dtype='<f4',count=m['positionCount'],offset=m['normalOffset']).reshape(-1,3)
                target_indices=np.frombuffer(buf,dtype='<u4',count=m['indexCount'],offset=m['indexOffset'])
                same=positions.shape==target_positions.shape and normals.shape==target_normals.shape
                if same:
                    same=(np.array_equal(positions,target_positions) and np.array_equal(normals,target_normals)
                          and np.array_equal(np.arange(len(positions),dtype='<u4'),target_indices))
                if same:matched_meshes+=1
                else:mismatches.append({'prototype':name,'material':m['material'],'reason':'source/runtime vertices, normals or triangle indices differ'})
        checks['source_geometry_transfer']={'mode':'Exact Float32 positions/normals and Uint32 triangle indices per material, regenerated from source parts','matched_meshes':matched_meshes,'mismatches':mismatches,'pass':not mismatches}
        if mismatches:fail('At least one runtime mesh differs from regenerated source geometry.')
    else:
        checks['source_geometry_transfer']={'mode':'Skipped by --quick; raw-buffer and build-hash checks still run','pass':None}

    scale=spec.get('pixelToMetre',1.5)
    park=region_box(spec['park']['pixelBounds'],scale)
    lake=safe_polygon(city['waterPolygons'][0])
    hole_polys=[safe_polygon(p) for p in city.get('waterHolePolygons',[])]
    lake_water=lake.difference(unary_union(hole_polys)) if hole_polys else lake
    water_polys=[lake_water]+[safe_polygon(p) for p in city['waterPolygons'][1:]]
    water=unary_union(water_polys)
    map_area=spec['worldSize'][0]*spec['worldSize'][1]
    checks['major_layout']={
        'lake_water_area_m2':rounded(lake_water.area,2),'lake_percent_of_map':rounded(lake_water.area/map_area*100,2),
        'requested_lake_percent_range':[25,30],
        'lake_water_within_requested_percent_range':25<=lake_water.area/map_area*100<=30,
        'lake_centroid_pixel':[rounded(lake.centroid.x/scale+725,2),rounded(lake.centroid.y/scale+544,2)],
        'lake_west_of_park':lake.centroid.x<park.bounds[0],
        'lake_to_park_minimum_gap_m':rounded(lake.distance(park),2),
        'park_dimensions_m':[rounded(park.bounds[2]-park.bounds[0]),rounded(park.bounds[3]-park.bounds[1])],
        'park_aspect_ratio_long_to_short':rounded((park.bounds[3]-park.bounds[1])/(park.bounds[2]-park.bounds[0])),
        'island_count':len(hole_polys)}
    if not checks['major_layout']['lake_west_of_park']:fail('Lake lies outside its required western relationship to the park.')
    if not checks['major_layout']['lake_water_within_requested_percent_range']:warn('Measured water area differs from the requested 25–30% map range; judge this alongside the primary reference composition.')

    # All building prototypes are known from the architectural catalog, with the
    # optional small park cultural building supplied by the landscape kit.
    building_instances=[i for i in instances if i['prototype'] in architecture or i['prototype']=='park_civic']
    actual_buildings=[]
    for inst in building_instances:
        name=inst['prototype'];lo,hi=local_bounds[name]
        env=transformed_rect(float(lo[0]),float(lo[2]),float(hi[0]),float(hi[2]),inst)
        col=prototypes[name].get('collision')
        collision=transformed_rect(-col[0],-col[1],col[0],col[1],inst) if col else env
        nominal=architecture.get(name,{}).get('footprint_m',[hi[0]-lo[0],hi[2]-lo[2]])
        nominal_poly=transformed_rect(-nominal[0]/2,-nominal[1]/2,nominal[0]/2,nominal[1]/2,inst)
        actual_buildings.append({'instance':inst,'envelope':env,'collision':collision,'nominal':nominal_poly,
                                 'height':float(hi[1]*inst.get('scale',[1,1,1])[1]+inst['position'][1])})
    spec_building_counts=Counter(b['prototype'] for b in spec.get('buildings',[]))
    measured_building_counts=Counter(b['instance']['prototype'] for b in actual_buildings)
    checks['building_records']={'runtime_architecture_instances':len(actual_buildings),'spec_building_records':len(spec.get('buildings',[])),
        'inventory_matches':spec_building_counts==measured_building_counts,
        'spec_by_prototype':dict(spec_building_counts),'runtime_by_prototype':dict(measured_building_counts)}
    if spec_building_counts!=measured_building_counts:fail('Scene specification building records disagree with runtime architecture instances.')

    required=['museum','library','school','sports_hall','rail_station','city_hall','hotel']
    heroes={name:counts.get(name,0) for name in required}
    landmark_ids={l['id'] for l in city.get('landmarks',[])}
    missing_heroes=[name for name,n in heroes.items() if not n]
    missing_landmarks=sorted({'lake','park','downtown','sports','station'}-landmark_ids)
    checks['heroes']={'counts':heroes,'missing':missing_heroes,'missing_navigation_landmarks':missing_landmarks,
        'park_cultural_buildings':[b['instance']['id'] for b in actual_buildings if park.intersects(b['nominal']) and b['instance']['prototype'] in ('museum','library','park_civic','city_hall')],
        'north_sports_halls':[b['instance']['id'] for b in actual_buildings if b['instance']['prototype']=='sports_hall' and b['instance']['position'][2]<(151-544)*scale],
        'southeast_stations':[b['instance']['id'] for b in actual_buildings if b['instance']['prototype']=='rail_station' and b['instance']['position'][0]>park.bounds[2] and b['instance']['position'][2]>(804-544)*scale]}
    if stage>=10 and (missing_heroes or missing_landmarks):fail('Required placed heroes or navigation landmarks are absent: '+', '.join(missing_heroes+missing_landmarks))

    roads=[];sidewalks=[];road_ids=[]
    for r in spec.get('streets',[]):
        if r.get('stage',3)>stage:continue
        if len(r['points'])<2:continue
        ln=LineString(r['points'])
        roads.append(ln.buffer(r['width']/2,cap_style=1,join_style=1));sidewalks.append(ln.buffer(r['width']/2+4.5,cap_style=1,join_style=1));road_ids.append(r['id'])
    road_union=unary_union(roads);sidewalk_union=unary_union(sidewalks)
    road_tree=STRtree(roads)
    def road_names(poly):
        try:return [road_ids[int(i)] for i in road_tree.query(poly,predicate='intersects') if roads[int(i)].intersection(poly).area>.05]
        except TypeError:return [name for name,r in zip(road_ids,roads) if r.intersects(poly) and r.intersection(poly).area>.05]
    road_overlaps=[];sidewalk_overlaps=[];water_overlaps=[];park_intrusions=[]
    allowed_park={'museum','library','city_hall','park_civic'}
    for b in actual_buildings:
        i=b['instance'];poly=b['envelope'];common={'id':i['id'],'prototype':i['prototype'],'region':i.get('region')}
        area=poly.intersection(road_union).area
        if area>.1:road_overlaps.append({**common,'overlap_m2':rounded(area),'roads':road_names(poly)})
        area=poly.intersection(sidewalk_union).area
        if area>.1:sidewalk_overlaps.append({**common,'overlap_m2':rounded(area)})
        area=poly.intersection(water).area
        if area>.1:water_overlaps.append({**common,'overlap_m2':rounded(area)})
        area=poly.intersection(park).area
        if area>.1 and i['prototype'] not in allowed_park:park_intrusions.append({**common,'overlap_m2':rounded(area)})
    checks['protected_space']={
        'method':'Conservative horizontal bounds of every actual mesh vertex, transformed by runtime instance; independent of declared placement footprints.',
        'building_road_overlaps':road_overlaps,'building_sidewalk_overlaps':sidewalk_overlaps,
        'building_water_overlaps':water_overlaps,'noncivic_building_park_overlaps':park_intrusions,
        'road_overlap_count':len(road_overlaps),'sidewalk_overlap_count':len(sidewalk_overlaps),
        'water_overlap_count':len(water_overlaps),'park_intrusion_count':len(park_intrusions)}
    if road_overlaps:fail(f'{len(road_overlaps)} building geometry envelopes intersect carriageways.')
    if sidewalk_overlaps:warn(f'{len(sidewalk_overlaps)} building geometry envelopes intersect road-side pavement; inspect overhead versus ground-level use.')
    if water_overlaps:fail(f'{len(water_overlaps)} buildings intersect water.')
    if park_intrusions:fail(f'{len(park_intrusions)} noncivic buildings intrude into the central park.')

    # Efficient broad phase against horizontal envelopes, with intersection area
    # used to distinguish an intentional touch from an overlapping solid envelope.
    building_polys=[b['envelope'] for b in actual_buildings]
    btree=STRtree(building_polys);overlap_pairs=[]
    for i,poly in enumerate(building_polys):
        try:candidates=[int(j) for j in btree.query(poly,predicate='intersects')]
        except TypeError:candidates=[j for j,p in enumerate(building_polys) if poly.intersects(p)]
        for j in candidates:
            if j<=i:continue
            area=poly.intersection(building_polys[j]).area
            if area>.2:overlap_pairs.append({'a':actual_buildings[i]['instance']['id'],'b':actual_buildings[j]['instance']['id'],'envelope_overlap_m2':rounded(area)})
    checks['building_envelopes']={'overlapping_pairs':overlap_pairs,'count':len(overlap_pairs),'note':'Overhead projections can create conservative envelope false positives; inspect reported pairs at their actual heights.'}
    if overlap_pairs:warn(f'{len(overlap_pairs)} building geometry envelopes overlap one another.')

    density=[]
    nominal_union=unary_union([b['nominal'] for b in actual_buildings])
    for r in spec['regions']:
        rp=region_box(r['pixels'],scale)
        usable=rp.difference(road_union).difference(water).difference(park)
        contained=[b for b in actual_buildings if rp.covers(Point(b['instance']['position'][0],b['instance']['position'][2]))]
        covered=nominal_union.intersection(rp).area
        density.append({'region':r['id'],'area_m2':rounded(rp.area,2),'building_centers':len(contained),
                        'nominal_building_coverage_m2':rounded(covered,2),'gross_coverage_percent':rounded(100*covered/rp.area,2),
                        'net_land_excluding_roads_water_park_m2':rounded(usable.area,2),
                        'net_coverage_percent':rounded(100*nominal_union.intersection(usable).area/usable.area,2) if usable.area>1 else None,
                        'buildings_per_hectare':rounded(len(contained)/(rp.area/10000),2)})
    parcels=[]
    for rec in spec.get('parcels',[]):
        poly=safe_polygon(rec['polygon']);coverage=nominal_union.intersection(poly).area
        parcels.append({'id':rec['id'],'region':rec['region'],'area_m2':rounded(poly.area,2),
                        'building_coverage_percent':rounded(coverage/poly.area*100,2) if poly.area else 0})
    checks['density']={'coverage_definition':'Nominal architectural ground footprints; no roof overhang inflation. Sports and open civic grounds can be intentional exceptions.',
                       'regions':density,'parcels':parcels,
                       'nearly_empty_parcels':[p for p in parcels if p['building_coverage_percent']<3]}
    if stage>=10 and checks['density']['nearly_empty_parcels']:
        warn(f"{len(checks['density']['nearly_empty_parcels'])} declared urban parcels have less than 3% building coverage; review intentional civic/sports spaces separately.")

    loops=[]
    for p in city.get('paths',[]):
        if p['id'] not in ('PATH_LAKE_COMPLETE_LOOP','PATH_LAKE_CYCLE_LOOP'):continue
        line=LineString(p['points']);gap=Point(p['points'][0]).distance(Point(p['points'][-1]))
        loops.append({'id':p['id'],'length_m':rounded(line.length,2),'width_m':p['width'],
                      'declared_closed':p.get('closed',False),'endpoint_gap_m':rounded(gap,6),
                      'simple_ring':line.is_ring,'self_intersection_free':line.is_simple,
                      'water_overlap_area_m2':rounded(line.buffer(p['width']/2).intersection(lake_water).area,4),
                      'full_lake_inside_loop':Polygon(line).covers(lake),
                      'pass':bool(p.get('closed')) and gap<.01 and line.is_ring and Polygon(line).covers(lake)})
    checks['lake_loops']={'loops':loops,'both_present':len(loops)==2,'pass':len(loops)==2 and all(p['pass'] for p in loops)}
    if not checks['lake_loops']['pass']:fail('The pedestrian and cycle loops do not both form complete simple circuits around the lake.')

    # Water barriers are evaluated against actual supported bridge/dock rectangles.
    # This includes the traced lake and central-park pond only: the decorative outer
    # river is not in the runtime waterPolygons and is explicitly out of this check.
    walk_surfaces=unary_union([box(*p['bounds']) for p in city.get('walkSurfaces',[])])
    unsupported_water=water.difference(walk_surfaces)
    road_water=[];path_water=[];path_buildings=[]
    building_solid=unary_union([b['collision'] for b in actual_buildings])
    padded_buildings=building_solid.buffer(spec.get('navigation',{}).get('radius',.32),resolution=4)
    for rid,rpoly in zip(road_ids,roads):
        crossing=rpoly.intersection(unsupported_water)
        if crossing.area>.2:
            road_water.append({'id':rid,'unsupported_carriageway_area_m2':rounded(crossing.area,3),'bounds':list(crossing.bounds)})
    for p in city.get('paths',[]):
        if p.get('stage',3)>stage or not p['id'].startswith('PATH_') or len(p['points'])<2:continue
        line=LineString(p['points'])
        crossing=line.intersection(unsupported_water)
        if crossing.length>.15:
            path_water.append({'id':p['id'],'unsupported_centerline_length_m':rounded(crossing.length,3),'bounds':list(crossing.bounds)})
        # Closed-door approach paths intentionally terminate at the collision edge;
        # their <= radius endpoint contact is allowed, while longer intersections are not.
        crossing=line.intersection(padded_buildings)
        permitted=.45 if p['id'].startswith('PATH_ENTRANCE_') else .15
        if crossing.length>permitted:
            path_buildings.append({'id':p['id'],'blocked_centerline_length_m':rounded(crossing.length,3),'bounds':list(crossing.bounds)})
    checks['route_water_and_building_clearance']={
        'scope':'Declared pedestrian PATH_ centerlines, carriageway footprints, lake and park pond; decorative outer river excluded.',
        'support_surface_count':len(city.get('walkSurfaces',[])),
        'roads_crossing_unsupported_water':road_water,
        'paths_crossing_unsupported_water':path_water,
        'paths_crossing_building_collision':path_buildings,
        'pass':not road_water and not path_water and not path_buildings,
        'limitation':'Geometric clearance only; runtime movement and whole-network connectivity require separate verification.'}
    if road_water:fail(f'{len(road_water)} road footprints cross water outside declared supported surfaces.')
    if path_water:fail(f'{len(path_water)} pedestrian route centerlines cross water outside declared supported surfaces.')
    if path_buildings:fail(f'{len(path_buildings)} pedestrian route centerlines cross building collision.')

    heights=defaultdict(list);tall=[];misplaced=[]
    for b in actual_buildings:
        i=b['instance'];h=b['height'];heights[i.get('region','UNCLASSIFIED')].append(h)
        if h>=45:
            rec={'id':i['id'],'prototype':i['prototype'],'height_m':rounded(h,2),'position':i['position'],'region':i.get('region')}
            tall.append(rec)
            if b['nominal'].centroid.x<=park.bounds[2]:misplaced.append(rec)
    height_summary={reg:{'count':len(hs),'min_m':rounded(min(hs),2),'median_m':rounded(np.median(hs),2),'max_m':rounded(max(hs),2)} for reg,hs in heights.items()}
    checks['skyline']={'regions':height_summary,'tall_threshold_m':45,'tall_building_count':len(tall),
                       'tall_buildings_east_of_park_count':len(tall)-len(misplaced),'misplaced_tall_buildings':misplaced,
                       'pass':bool(tall) and not misplaced if stage>=7 else None}
    if stage>=7 and not tall:fail('No tall buildings form the required eastern downtown skyline.')
    if misplaced:fail(f'{len(misplaced)} tall buildings lie outside the required eastern skyline zone.')

    spawn_issues=[]
    collisions=unary_union([b['collision'] for b in actual_buildings])
    for landmark in city.get('landmarks',[]):
        p=landmark.get('walkPosition')
        if not p:continue
        pt=Point(p[0],p[2]);why=[]
        if water.contains(pt):why.append('water')
        if collisions.contains(pt):why.append('building collision')
        if why:spawn_issues.append({'id':landmark['id'],'position':p,'issues':why})
    checks['landmark_spawn_positions']={'invalid_positions':spawn_issues,'pass':not spawn_issues,
        'limitation':'Position clearance only. This does not establish controller traversal or route connectivity.'}
    if spawn_issues:fail('One or more landmark walking starts lie in water or building collision.')

    if stage<10:warn('Intermediate stage audit: hero, density and final traversal acceptance remain pending.')
    report['elapsed_seconds']=rounded(time.perf_counter()-started,3)
    report['status']='FAIL' if report['failures'] else 'PASS_WITH_WARNINGS' if report['warnings'] else 'PASS'
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--quick',action='store_true',help='Skip exact source-part regeneration; keep buffer and hash validation.')
    args=parser.parse_args()
    result=audit(args.root,not args.quick)
    output=args.output or args.root/'validation_metrics.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'stage':result['stage'],'elapsed_seconds':result['elapsed_seconds'],
                      'failures':result['failures'],'warnings':result['warnings'],'output':str(output)},indent=2))
