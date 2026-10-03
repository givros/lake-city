"""Export and reimport the exact canonical actor in a disposable Blender process.

Only export-time state changes are made; the canonical source is never saved.
The bundled Walk and Idle are already cyclic in-place motions.
"""
import bpy, hashlib, json, math, struct, sys
from pathlib import Path
from mathutils import Vector, kdtree

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'CharacterBase.blend'
OUTPUT=Path('E:/Dev/lake-city/artifacts/lake_city/viewer/public/assets/characters/pedestrian.glb')
sys.path.insert(0, 'C:/Users/limou/.codex/skills/blender-lowpoly-character/scripts/export')
from export_character_assets import (discover_character, choose_action_slot,
    prepare_objects_for_export, replace_bone_weights_with_top_four, select_objects)

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def posed_meshes(meshes):
    dg=bpy.context.evaluated_depsgraph_get();result={}
    for ob in meshes:
        ev=ob.evaluated_get(dg);mesh=ev.to_mesh(preserve_all_data_layers=True,depsgraph=dg)
        mesh.calc_loop_triangles()
        pts=[list(ev.matrix_world@v.co) for v in mesh.vertices]
        result[ob.name]={'points':pts,'triangles':len(mesh.loop_triangles)}
        ev.to_mesh_clear()
    return result
def bounds(data):
    points=[p for mesh in data.values() for p in mesh['points']]
    return {'min':[min(p[k] for p in points) for k in range(3)],
            'max':[max(p[k] for p in points) for k in range(3)]}
def gltf_json(path):
    raw=path.read_bytes();length,kind=struct.unpack_from('<II',raw,12)
    assert kind==0x4e4f534a
    return json.loads(raw[20:20+length])

initial_hash=sha(SOURCE)
character,rig,garments,meshes=discover_character()
assert len(rig.data.bones)==49
prepare_objects_for_export(rig,meshes)
weights=replace_bone_weights_with_top_four(meshes,rig)
ad=rig.animation_data_create();ad.action=None
for track in list(ad.nla_tracks): ad.nla_tracks.remove(track)
for bone in rig.pose.bones: bone.matrix_basis.identity()
rig.data.pose_position='REST'
bpy.context.view_layer.update()
neutral=posed_meshes(meshes);neutral_bounds=bounds(neutral)
rig.data.pose_position='POSE'
selected={name:bpy.data.actions[name] for name in ('Idle','Walk')}
for action in list(bpy.data.actions):
    if action.name not in selected: bpy.data.actions.remove(action)
samples={};clip_metrics={}
for name,action in selected.items():
    ad.action=action;ad.action_slot=choose_action_slot(action,rig)
    start,end=(int(v) for v in action.frame_range)
    frames=sorted(set(round(start+(end-start)*i/4) for i in range(5)))
    sample_data={};sole=[];pelvis=[]
    for frame in range(start,end+1):
        bpy.context.scene.frame_set(frame)
        data=posed_meshes(meshes)
        sole.append(min(p[2] for p in data['CharacterBase']['points']))
        pelvis.append(list((rig.matrix_world@rig.pose.bones['pelvis'].matrix).translation))
        if frame in frames: sample_data[frame]=data
    samples[name]=sample_data
    delta=[pelvis[-1][i]-pelvis[0][i] for i in range(3)]
    assert math.hypot(delta[0],delta[1])<1e-5, (name,delta)
    clip_metrics[name]={'source_frame_range':[start,end], 'fps':30,
        'duration_seconds':(end-start)/30, 'loop':True, 'in_place':True,
        'root_endpoint_delta_blender':delta,
        'pelvis_horizontal_range': [max(p[k] for p in pelvis)-min(p[k] for p in pelvis) for k in range(2)],
        'lowest_sole_y_range': [min(sole),max(sole)],
        'recommended_ground_offset_at_scale_1':-sum(sole)/len(sole),
        'sample_frames':frames}

ad.action=None
for bone in rig.pose.bones:bone.matrix_basis.identity()
bpy.context.scene.frame_set(1)
select_objects([rig,*meshes],rig)
OUTPUT.parent.mkdir(parents=True,exist_ok=True)
options=dict(filepath=str(OUTPUT),check_existing=False,export_format='GLB',
    use_selection=True,export_yup=True,export_animations=True,export_skins=True,
    export_all_influences=False,export_influence_nb=4,export_apply=True,
    export_extras=True,export_cameras=False,export_lights=False,
    export_materials='EXPORT',export_texcoords=True,export_normals=True,
    export_morph=False,export_rest_position_armature=True,
    export_current_frame=False,export_armature_object_remove=False,
    export_def_bones=False,export_leaf_bone=False,
    export_draco_mesh_compression_enable=False,export_animation_mode='ACTIONS',
    export_frame_range=False,export_force_sampling=True,export_frame_step=1,
    export_optimize_animation_size=False,export_anim_single_armature=True,
    export_anim_slide_to_zero=True)
assert 'FINISHED' in bpy.ops.export_scene.gltf(**options)
raw=gltf_json(OUTPUT)
assert not {'KHR_draco_mesh_compression','EXT_meshopt_compression'}.intersection(raw.get('extensionsUsed',[]))
assert sorted(a['name'] for a in raw['animations'])==['Idle','Walk']
for animation in raw['animations']:
    starts=[raw['accessors'][s['input']]['min'][0] for s in animation['samplers']]
    ends=[raw['accessors'][s['input']]['max'][0] for s in animation['samplers']]
    assert abs(min(starts))<1e-6
    clip_metrics[animation['name']]['duration_seconds']=max(ends)
    clip_metrics[animation['name']]['start_seconds']=min(starts)
assert all(len(skin['joints'])==49 for skin in raw['skins'])
triangles={mesh['name']:sum(raw['accessors'][p['indices']]['count']//3 for p in mesh['primitives']) for mesh in raw['meshes']}
assert sorted(triangles.values())==sorted([3134,1440,1048]),triangles

# A second import into a cleared in-memory scene checks the actual delivered file.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps=30
bpy.ops.import_scene.gltf(filepath=str(OUTPUT))
import_rig=next(o for o in bpy.data.objects if o.type=='ARMATURE')
assert len(import_rig.data.bones)==49
import_meshes=[bpy.data.objects[name] for name in ('CharacterBase','LongSleeveShirt','Pants')]
reimport={}
for name,snapshots in samples.items():
    action=next(a for a in bpy.data.actions if a.name==name or a.name.endswith('_'+name) or a.name.endswith('|'+name))
    import_rig.animation_data_create().action=action
    import_rig.animation_data.action_slot=choose_action_slot(action,import_rig)
    import_start=float(action.frame_range[0])
    max_delta=0.0;per_sample=[]
    for frame,expected in snapshots.items():
        bpy.context.scene.frame_set(round(import_start+(frame-1)))
        actual=posed_meshes(import_meshes)
        for mesh_name,data in actual.items():
            assert data['triangles']==expected[mesh_name]['triangles']
            tree=kdtree.KDTree(len(expected[mesh_name]['points']))
            for i,point in enumerate(expected[mesh_name]['points']):tree.insert(Vector(point),i)
            tree.balance()
            delta=max(tree.find(Vector(p))[2] for p in data['points'])
            max_delta=max(max_delta,delta)
        per_sample.append({'source_frame':frame,'bounds_blender':bounds(actual)})
    assert max_delta<0.00015,(name,max_delta)
    reimport[name]={'passed':True,'maximum_vertex_deviation':max_delta,'samples':per_sample,'import_frame_range':list(action.frame_range)}

assert sha(SOURCE)==initial_hash
height=neutral_bounds['max'][2]-neutral_bounds['min'][2]
contract={'asset':'/assets/characters/pedestrian.glb','source':str(SOURCE),
    'source_sha256':initial_hash,'asset_sha256':sha(OUTPUT),
    'source_saved':False,'source_unchanged':True,'compressed':False,
    'coordinate_system':'glTF Y-up','forward_axis':'+Z',
    'rotation_y_for_direction':'Math.atan2(direction.x,direction.z)',
    'height_at_scale_1':height,'neutral_foot_y_at_scale_1':neutral_bounds['min'][2],
    'recommended_adult_height':1.75,'recommended_uniform_scale':1.75/height,
    'grounding':'Group.position.y = surfaceY + clip.recommended_ground_offset_at_scale_1 * scale. Preserve vertical animation. Blend offsets during Walk/Idle transitions.',
    'rig':'CharacterRig','bone_count':49,'mesh_names':[o.name for o in import_meshes],
    'mesh_triangles':triangles,'total_triangles':sum(triangles.values()),
    'clips':clip_metrics,'normalized_weights':weights,'reimport_validation':reimport,
    'animation_policy':'Original skill Walk/Idle retained verbatim; clips already have cyclic in-place pelvis motion. Actor route moves an external parent group.',
    'passed':True}
(ROOT/'pedestrian_runtime.json').write_text(json.dumps(contract,indent=2))
OUTPUT.with_suffix('.json').write_text(json.dumps(contract,indent=2))
print('PEDESTRIAN_RUNTIME='+json.dumps({k:v for k,v in contract.items() if k not in ('reimport_validation','normalized_weights')}))
