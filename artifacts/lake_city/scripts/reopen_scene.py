"""Reopen, validate source integrity and render one recorded city-life view."""
import bpy
import json
import sys
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from integrate_city_life import (sha, static_signature, static_visibility,
                                non_vehicle_visibility_signature, validate_capture)

bpy.ops.wm.open_mainfile(filepath=str(ROOT / 'Lake_City.blend'))
scene = bpy.context.scene
data = json.loads((ROOT / 'viewer/public/assets/city.json').read_text())
objects = [ob for ob in scene.objects if ob.type == 'MESH' and 'source_id' in ob]
unique = {ob.data.name: ob.data for ob in objects}
triangles = sum(len(ob.data.polygons) for ob in objects)
assert len(objects) == data['stats']['instances'], (len(objects), data['stats']['instances'])
assert {ob['source_id'] for ob in objects} == {item['id'] for item in data['instances']}
assert triangles == data['stats']['visibleTriangles'], (triangles, data['stats']['visibleTriangles'])
assert scene['source_hash'] == data['sourceHash']
assert all(math.isfinite(value) for ob in objects for value in ob.location)
external = [image.filepath for image in bpy.data.images if image.source == 'FILE' and not image.packed_file]
assert not external, external
report = dict(status='passed', freshProcessReopen=True, sourceHash=data['sourceHash'],
              meshObjects=len(objects), uniqueMeshes=len(unique), sourceTriangles=triangles,
              visibleStaticTriangles=sum(len(ob.data.polygons) for ob in objects if not ob.hide_render),
              materials=len(bpy.data.materials), cameras=[ob.name for ob in scene.objects if ob.type == 'CAMERA'],
              externalImageDependencies=external, renderer=scene.render.engine)

life = bpy.data.collections.get('CITY_LIFE')
if life:
    capture_path = ROOT / 'validation/city_life_samples.json'
    capture = json.loads(capture_path.read_text())
    source_vehicles = validate_capture(capture, data)
    integration = json.loads((ROOT / 'validation/city_life_blender.json').read_text())
    assert integration['passed'] and integration['captureSHA256'] == sha(capture_path)
    scene.frame_set(1)
    current_signature = static_signature()
    assert current_signature == integration['staticBefore'] == integration['staticAfter']
    assert sha(ROOT / 'characters/CharacterBase.blend') == integration['canonicalCharacterSHA256']
    visibility = static_visibility()
    assert all(visibility[key] == (True, True, True) for key in source_vehicles)
    visibility_hash = non_vehicle_visibility_signature(visibility, source_vehicles)
    promotion = integration['vehiclePromotion']
    assert visibility_hash == promotion['nonVehicleVisibilityBefore'] == promotion['nonVehicleVisibilityAfter']
    assert set(promotion['sourceInstanceIds']) == set(source_vehicles)

    actors = [ob for ob in life.objects if ob.get('actor_type')]
    by_runtime_id = {ob['runtime_actor_id']: ob for ob in actors}
    assert len(by_runtime_id) == len(actors) == len(capture['actors'])
    assert set(by_runtime_id) == {actor['id'] for actor in capture['actors']}
    vehicle_actors = [ob for ob in actors if ob['actor_type'] == 'vehicle']
    promoted = [ob for ob in vehicle_actors if ob.get('source_instance_id')]
    assert len(promoted) == len(source_vehicles) == 478
    assert {ob['source_instance_id'] for ob in promoted} == set(source_vehicles)
    assert len(vehicle_actors) == 562
    source_objects = {ob['source_id']: ob for ob in objects}
    for actor in promoted:
        source_id = actor['source_instance_id']
        original = source_objects[source_id]
        bodies = [ob for ob in actor.children if ob.type == 'MESH']
        assert len(bodies) == 1 and bodies[0].data == original.data, source_id
        assert not actor.hide_render and not actor.hide_viewport and not actor.hide_get(), source_id
        assert not bodies[0].hide_render and not bodies[0].hide_viewport and not bodies[0].hide_get(), source_id
        assert bodies[0].get('source_instance_id') == source_id
        scale = source_vehicles[source_id]['scale']
        assert max(abs(actor.scale[i] - scale[j]) for i, j in enumerate((0, 2, 1))) < 1e-6
    assert not [ob for ob in objects if ob['source_id'] in source_vehicles and not ob.hide_render]
    rigs = [ob for ob in life.objects if ob.type == 'ARMATURE']
    assert len(rigs) == 80 and all(len(ob.data.bones) == 49 for ob in rigs)
    assert sum(ob['actor_type'] == 'pedestrian' for ob in actors) == 80
    max_capture_error = 0.0
    for actor in capture['actors']:
        x, y, z = actor['samples'][0]['position']
        max_capture_error = max(max_capture_error, math.dist(by_runtime_id[actor['id']].location, (x, -z, y)))
    assert max_capture_error < .001, max_capture_error
    starts = {ob.name: tuple(ob.location) for ob in actors}
    first = {bone.name: bone.matrix.copy() for bone in rigs[0].pose.bones}
    scene.frame_set(16)
    pose_delta = max(abs(bone.matrix[r][c] - first[bone.name][r][c])
                     for bone in rigs[0].pose.bones for r in range(4) for c in range(4))
    assert pose_delta > 1e-4, pose_delta
    scene.frame_set(min(301, scene.frame_end))
    moving = sum(math.dist(tuple(ob.location), starts[ob.name]) > .05 for ob in actors)
    moving_promoted = sum(math.dist(tuple(ob.location), starts[ob.name]) > .05 for ob in promoted)
    assert moving > len(actors) * .5, (moving, len(actors))
    scene.frame_set(1)
    report['cityLife'] = {'actors': len(actors), 'vehicles': len(vehicle_actors),
                         'promotedSourceVehicles': len(promoted), 'hiddenFixedVehicles': len(source_vehicles),
                         'pedestrians': len(rigs), 'bonesPerRig': 49, 'movingOverTenSeconds': moving,
                         'promotedMovingOverTenSeconds': moving_promoted,
                         'sampledBonePoseDelta': pose_delta, 'maxCapturedRootPositionError': max_capture_error,
                         'allSourceGeometryAndTransformsUnchanged': True, 'nonVehicleVisibilityUnchanged': True,
                         'frameRange': [scene.frame_start, scene.frame_end], 'fps': scene.render.fps,
                         'runtimeCapture': scene['city_life_capture']}
report['visibleTriangles'] = report['visibleStaticTriangles'] + sum(
    len(ob.data.polygons) for ob in (life.objects if life else []) if ob.type == 'MESH' and not ob.hide_render)

# One fresh-process image only. The default preserves the existing top-view path.
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
camera_name = args[args.index('--camera') + 1] if '--camera' in args else 'top'
assert camera_name in bpy.data.objects and bpy.data.objects[camera_name].type == 'CAMERA'
scene.camera = bpy.data.objects[camera_name]
scene.render.resolution_x = 1450
scene.render.resolution_y = 1088
scene.render.filepath = str(ROOT / f'renders/reopened_{camera_name}.png')
bpy.ops.render.render(write_still=True)
report['reopenedRender'] = f'renders/reopened_{camera_name}.png'
(ROOT / 'blender_validation.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report), flush=True)
