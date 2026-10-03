"""Import the complete source aircraft as editable parts, preserving Lake City."""
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
CITY = HERE.parent / 'Lake_City.blend'
REPORT = HERE / 'blender_aircraft_validation.json'
COLLECTION = 'CITY_AIRCRAFT'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(names=None):
    """Hash old object transforms, mesh buffers, materials and animation links."""
    names = sorted(names if names is not None else (ob.name for ob in bpy.data.objects))
    digest = hashlib.sha256()
    meshes = {}
    materials = {}
    for name in names:
        ob = bpy.data.objects[name]
        record = dict(name=name, type=ob.type, parent=ob.parent.name if ob.parent else None,
                      data=ob.data.name if ob.data else None, matrix=[list(row) for row in ob.matrix_basis],
                      visible=[ob.hide_viewport, ob.hide_render, ob.hide_get()],
                      collections=sorted(collection.name for collection in ob.users_collection),
                      action=ob.animation_data.action.name if ob.animation_data and ob.animation_data.action else None)
        if ob.type == 'MESH':
            record['materials'] = [slot.material.name if slot.material else None for slot in ob.material_slots]
            meshes[ob.data.name] = ob.data
            for slot in ob.material_slots:
                if slot.material:
                    materials[slot.material.name] = slot.material
        digest.update(json.dumps(record, sort_keys=True).encode())
    for name, mesh in sorted(meshes.items()):
        digest.update(name.encode())
        for data, prop, length, dtype in ((mesh.vertices, 'co', len(mesh.vertices) * 3, '<f4'),
                                          (mesh.loops, 'vertex_index', len(mesh.loops), '<i4'),
                                          (mesh.polygons, 'material_index', len(mesh.polygons), '<i4')):
            values = np.empty(length, dtype=dtype)
            data.foreach_get(prop, values)
            digest.update(values.tobytes())
        for uv in mesh.uv_layers:
            values = np.empty(len(uv.data) * 2, dtype='<f4')
            uv.data.foreach_get('uv', values)
            digest.update(uv.name.encode())
            digest.update(values.tobytes())
    for name, material in sorted(materials.items()):
        record = dict(name=name, diffuse=list(material.diffuse_color), metallic=material.metallic, roughness=material.roughness)
        if material.node_tree:
            record['nodes'] = []
            for node in material.node_tree.nodes:
                sockets = []
                for socket in node.inputs:
                    if hasattr(socket, 'default_value'):
                        value = socket.default_value
                        if isinstance(value, (str, bool, float, int)):
                            encoded = value
                        else:
                            try:
                                encoded = list(value)
                            except TypeError:
                                encoded = getattr(value, 'name', None)
                        sockets.append([socket.identifier, encoded])
                record['nodes'].append([node.name, node.bl_idname, sockets, node.image.name if hasattr(node, 'image') and node.image else None])
            record['links'] = [[link.from_node.name, link.from_socket.identifier, link.to_node.name, link.to_socket.identifier] for link in material.node_tree.links]
        digest.update(json.dumps(record, sort_keys=True).encode())
    return dict(sha256=digest.hexdigest(), objects=len(names), uniqueMeshes=len(meshes), materials=len(materials))


def aircraft_inventory(collection):
    meshes = [ob for ob in collection.all_objects if ob.type == 'MESH']
    triangles = sum(sum(len(poly.vertices) - 2 for poly in ob.data.polygons) for ob in meshes)
    assert len(meshes) == 39, len(meshes)
    assert triangles == 37119, triangles
    return dict(objects=len(collection.all_objects), meshes=len(meshes), triangles=triangles,
                materials=sorted({slot.material.name for ob in meshes for slot in ob.material_slots if slot.material}))


if '--verify' in sys.argv:
    data = json.loads(REPORT.read_text())
    bpy.ops.wm.open_mainfile(filepath=str(CITY))
    current = snapshot(data['protectedObjectNames'])
    assert current == data['before'] == data['after'], (current, data['before'], data['after'])
    collection = bpy.data.collections[COLLECTION]
    root = bpy.data.objects['AIRCRAFT_Cropper_Seven']
    expected_position = Vector((-560, -250, 240))
    assert (root.location - expected_position).length < 1e-6, list(root.location)
    rotation = root.matrix_basis.to_quaternion()
    forward = rotation @ Vector((0, -1, 0))
    up = rotation @ Vector((0, 0, 1))
    assert (forward - Vector((1, 0, 0))).length < 1e-6, list(forward)
    assert (up - Vector((0, 0, 1))).length < 1e-6, list(up)
    assert bpy.context.scene.camera.name == data['protectedScene']['camera']
    assert bpy.context.scene.frame_current == data['protectedScene']['frame']
    data['freshProcessReopen'] = True
    data['reopened'] = current
    data['cityAircraft'] = aircraft_inventory(collection)
    data['cityBlendSHA256'] = sha(CITY)
    data['blenderEuler'] = list(root.matrix_basis.to_euler())
    data['blenderForward'] = list(forward)
    data['blenderUp'] = list(up)
    REPORT.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({key: value for key, value in data.items() if key != 'protectedObjectNames'}), flush=True)
else:
    assert not REPORT.exists(), 'Aircraft already integrated; use --verify or deliberately revise the existing asset.'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(HERE / 'Cropper_Seven.glb'), merge_vertices=False)
    collection = bpy.data.collections.new(COLLECTION)
    bpy.context.scene.collection.children.link(collection)
    objects = list(bpy.context.scene.objects)
    roots = [ob for ob in objects if ob.parent is None]
    assert len(roots) == 1, [ob.name for ob in roots]
    root = roots[0]
    root.name = 'AIRCRAFT_Cropper_Seven'
    for ob in objects:
        for old in list(ob.users_collection):
            old.objects.unlink(ob)
        collection.objects.link(ob)
        if ob.get('runtimeVisibleAboveRpm'):
            ob.hide_render = True
            ob.hide_viewport = True
    for old in list(bpy.data.collections):
        if old != collection and not old.objects and not old.children:
            bpy.data.collections.remove(old)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1
    root['source_project'] = 'plane-3d-astra'
    root['source_geometry_sha256'] = json.loads((HERE / 'aircraft_provenance.json').read_text())['sourceGeometry']['sha256']
    standalone = aircraft_inventory(collection)
    neutral_matrix = root.matrix_basis.copy()
    bpy.context.scene['aircraft_forward'] = 'Blender -Y (runtime +Z); up +Z (runtime +Y)'
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE / 'Cropper_Seven.blend'))

    backup = HERE.parent / 'viewer/node_modules/.cache/lake-city-aircraft/Lake_City.before-aircraft.blend'
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(CITY, backup)
    bpy.ops.wm.open_mainfile(filepath=str(CITY))
    assert COLLECTION not in bpy.data.collections, 'City already contains an aircraft collection'
    names = sorted(ob.name for ob in bpy.data.objects)
    before = snapshot(names)
    scene = bpy.context.scene
    protected_scene = dict(camera=scene.camera.name, frame=scene.frame_current, sourceHash=scene.get('source_hash'))
    with bpy.data.libraries.load(str(HERE / 'Cropper_Seven.blend'), link=False) as (source, target):
        target.collections = [COLLECTION]
    scene.collection.children.link(target.collections[0])
    root = bpy.data.objects['AIRCRAFT_Cropper_Seven']
    # Runtime Y-up uses [x, y, z] -> Blender [x, -z, y]. Heading +pi/2
    # therefore rotates the aircraft's Blender -Y forward axis toward +X.
    root.matrix_basis = Matrix.Translation((-560, -250, 240)) @ Matrix.Rotation(math.pi / 2, 4, 'Z') @ neutral_matrix
    root['runtime_spawn'] = [-560.0, 240.0, 250.0]
    root['runtime_yaw'] = math.pi / 2
    after = snapshot(names)
    assert before == after, (before, after)
    assert scene.camera.name == protected_scene['camera'] and scene.frame_current == protected_scene['frame']
    bpy.ops.wm.save_as_mainfile(filepath=str(CITY))
    report = dict(passed=True, freshProcessReopen=False, standalone=standalone, before=before, after=after,
                  protectedObjectNames=names, protectedScene=protected_scene,
                  runtimeSpawn=[-560, 240, 250], runtimeYaw=math.pi / 2,
                  blenderSpawn=list(root.location), blenderEuler=list(root.matrix_basis.to_euler()),
                  standaloneBlendSHA256=sha(HERE / 'Cropper_Seven.blend'),
                  glbSHA256=sha(HERE / 'Cropper_Seven.glb'), cityAircraft=aircraft_inventory(target.collections[0]))
    REPORT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'protectedObjectNames'}), flush=True)
