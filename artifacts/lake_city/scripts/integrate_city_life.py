"""Add an editable, sampled city-life preview without modifying the static city.

The live viewer owns continuous routing. This Blender timeline is a recorded
segment of those same routes, using linked vehicle meshes and the validated
animated character export. Original fixed cars retain their source geometry
and transforms but are hidden; each has exactly one animated representative.
The canonical character file is never modified.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BLEND = ROOT / "Lake_City.blend"
SAMPLES = ROOT / "validation/city_life_samples.json"
REPORT = ROOT / "validation/city_life_blender.json"
VEHICLE_PROTOTYPES = {"car_sedan", "car_suv", "delivery_van"}
EXPECTED_SOURCE_VEHICLES = 478
EXPECTED_ADDITIONAL_VEHICLES = 84
EXPECTED_PEDESTRIANS = 80


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def static_signature():
    objects = sorted((o for o in bpy.context.scene.objects if "source_id" in o), key=lambda o: o["source_id"])
    digest = hashlib.sha256()
    meshes = {}
    for ob in objects:
        # Hidden objects are omitted from the dependency graph on fresh reopen,
        # so their unevaluated matrix_world can be identity. Every source object
        # is authored as an unparented, unanimated instance; its matrix_basis is
        # the same exact transform without requiring a visibility mutation.
        assert ob.parent is None and ob.animation_data is None and not ob.constraints, ob.name
        digest.update(ob["source_id"].encode())
        digest.update(np.array(ob.matrix_basis, dtype="<f4").tobytes())
        meshes[ob.data.name] = ob.data
    for name, mesh in sorted(meshes.items()):
        vertices = np.empty(len(mesh.vertices) * 3, dtype="<f4")
        mesh.vertices.foreach_get("co", vertices)
        loops = np.empty(len(mesh.loops), dtype="<i4")
        mesh.loops.foreach_get("vertex_index", loops)
        digest.update(name.encode())
        digest.update(vertices.tobytes())
        digest.update(loops.tobytes())
    return {"hash": digest.hexdigest(), "objects": len(objects), "uniqueMeshes": len(meshes)}


def validate_capture(capture, city):
    """Reject stale or partial captures before opening or modifying the city."""
    assert capture["sourceHash"] == city["sourceHash"]
    originals = {item["id"]: item for item in city["instances"]
                 if item["prototype"] in VEHICLE_PROTOTYPES}
    assert len(originals) == EXPECTED_SOURCE_VEHICLES, len(originals)
    actors = capture["actors"]
    assert len({actor["id"] for actor in actors}) == len(actors)
    assert all(actor["type"] in {"vehicle", "pedestrian"} for actor in actors)
    vehicles = [actor for actor in actors if actor["type"] == "vehicle"]
    promoted = [actor for actor in vehicles if actor.get("sourceInstanceId")]
    source_ids = [actor["sourceInstanceId"] for actor in promoted]
    assert len(source_ids) == len(set(source_ids)), "Duplicate source vehicle promotion"
    assert set(source_ids) == set(originals), {
        "missingSourceVehicles": sorted(set(originals) - set(source_ids)),
        "unexpectedSourceVehicles": sorted(set(source_ids) - set(originals)),
    }
    assert len(vehicles) == EXPECTED_SOURCE_VEHICLES + EXPECTED_ADDITIONAL_VEHICLES, len(vehicles)
    assert sum(actor["type"] == "pedestrian" for actor in actors) == EXPECTED_PEDESTRIANS
    for actor in promoted:
        original = originals[actor["sourceInstanceId"]]
        assert actor["prototype"] == original["prototype"], actor["id"]
        if "scale" in actor:
            value = actor["scale"]
            actual = [value] * 3 if isinstance(value, (int, float)) else list(value)
            assert actual == original["scale"], (actor["id"], actual, original["scale"])
    for actor in actors:
        assert actor["samples"], actor["id"]
        assert all(len(record["position"]) == 3 and all(math.isfinite(v) for v in record["position"])
                   and math.isfinite(record["rotation"]) for record in actor["samples"]), actor["id"]
    return originals


def static_visibility():
    return {ob["source_id"]: (bool(ob.hide_render), bool(ob.hide_viewport), bool(ob.hide_get()))
            for ob in bpy.context.scene.objects if "source_id" in ob}


def non_vehicle_visibility_signature(visibility, vehicle_ids):
    values = {key: value for key, value in visibility.items() if key not in vehicle_ids}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def linear_keys(action):
    if not action:
        return
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points:
                        key.interpolation = "LINEAR"


def route_keys(ob, records, fps):
    previous = None
    for record in records:
        frame = 1 + record["time"] * fps
        x, y, z = record["position"]
        angle = record["rotation"]
        if previous is not None:
            angle = previous + (angle - previous + math.pi) % (math.tau) - math.pi
        previous = angle
        ob.location = (x, -z, y)
        ob.rotation_euler = (0, 0, angle)
        ob.keyframe_insert("location", frame=frame, group="Route")
        ob.keyframe_insert("rotation_euler", frame=frame, group="Route")
    linear_keys(ob.animation_data.action)


def clone_character(template, collection, name, parent):
    mapping = {}
    for source in template:
        ob = source.copy()
        ob.name = name + "__" + source.name
        if source.type == "ARMATURE":
            ob.data = source.data.copy()
        ob.animation_data_clear()
        ob.hide_render = False
        ob.hide_viewport = False
        ob["city_life"] = True
        collection.objects.link(ob)
        mapping[source] = ob
    for source, ob in mapping.items():
        ob.parent = mapping.get(source.parent, parent)
        for modifier in ob.modifiers:
            if modifier.type == "ARMATURE" and modifier.object in mapping:
                modifier.object = mapping[modifier.object]
        for constraint in ob.constraints:
            if hasattr(constraint, "target") and constraint.target in mapping:
                constraint.target = mapping[constraint.target]
    return list(mapping.values())


def apply_palette(objects, colors, cache):
    for ob in objects:
        if ob.type != "MESH":
            continue
        for slot in ob.material_slots:
            if not slot.material:
                continue
            source = slot.material
            color = colors.get(source.name.split(".")[0])
            if not color:
                continue
            key = (source.name, color)
            if key not in cache:
                material = source.copy()
                material.name = "Life_" + source.name + "_" + color.lstrip("#")
                rgb = [int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
                linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
                material.diffuse_color = (*linear, 1)
                if material.use_nodes:
                    material.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (*linear, 1)
                cache[key] = material
            slot.link = "OBJECT"
            slot.material = cache[key]


def animate_rig(rig, clips, records, fps, end_frame):
    rig.animation_data_create()
    for clip in ("Idle", "Walk"):
        action = clips[clip]
        track = rig.animation_data.nla_tracks.new()
        track.name = clip
        strip = track.strips.new(clip, 1, action)
        slots = [slot for slot in action.slots if slot.target_id_type == "OBJECT"]
        matching = [slot for slot in slots if "Rig" in slot.identifier or "Armature" in slot.identifier]
        if matching or slots:
            strip.action_slot = (matching or slots)[0]
        strip.action_frame_start = action.frame_range[0]
        strip.action_frame_end = action.frame_range[1]
        strip.frame_end = end_frame
        strip.extrapolation = "NOTHING"
        strip.blend_type = "REPLACE"
        strip.use_animated_time = True
        strip.use_animated_time_cyclic = True
        strip.use_animated_influence = True
        duration = max((action.frame_range[1] - action.frame_range[0]) / fps, 0.001)
        unwrapped = None
        previous = None
        for record in records:
            frame = 1 + record["time"] * fps
            current = float(record.get("walkTime" if clip == "Walk" else "idleTime", record["time"]))
            if unwrapped is None:
                unwrapped = current
            else:
                delta = current - previous
                if delta < -duration * 0.5:
                    delta += duration
                unwrapped += delta
            previous = current
            strip.strip_time = action.frame_range[0] + unwrapped * fps
            # REPLACE tracks are stacked, not normalized like AnimationMixer.
            # Full Idle underneath weighted Walk gives the same two-pose blend
            # without an extra contribution from the unanimated rest pose.
            strip.influence = 1.0 if clip == "Idle" else float(record.get("walkWeight", 1))
            strip.keyframe_insert("strip_time", frame=frame)
            strip.keyframe_insert("influence", frame=frame)
        for curve in strip.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"


def main():
    capture = json.loads(SAMPLES.read_text())
    city = json.loads((ROOT / "viewer/public/assets/city.json").read_text())
    source_vehicles = validate_capture(capture, city)
    asset = ROOT / "viewer/public/assets/characters/pedestrian.glb"
    canonical = ROOT / "characters/CharacterBase.blend"
    canonical_before = sha(canonical)
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    scene.frame_set(1)
    before = static_signature()
    visibility_before = static_visibility()
    source_objects = {ob["source_id"]: ob for ob in scene.objects if "source_id" in ob}
    assert set(source_vehicles).issubset(source_objects)
    for ob in list(scene.objects):
        if ob.get("city_life"):
            bpy.data.objects.remove(ob, do_unlink=True)
    old = bpy.data.collections.get("CITY_LIFE")
    if old:
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new("CITY_LIFE")
    scene.collection.children.link(collection)
    scene.render.fps = capture["fps"]
    existing = set(bpy.data.objects)
    existing_actions = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(asset))
    imported = [ob for ob in bpy.data.objects if ob not in existing]
    imported_rigs = [ob for ob in imported if ob.type == "ARMATURE"]
    assert len(imported_rigs) == 1
    imported_rig = imported_rigs[0]
    # The glTF importer also creates a hidden Icosphere custom bone shape.
    # It is an editor helper, not a fourth character mesh to clone and unhide.
    template = [imported_rig] + [ob for ob in imported if ob.type == "MESH" and
                any(mod.type == "ARMATURE" and mod.object == imported_rig for mod in ob.modifiers)]
    assert len(template) == 4, [ob.name for ob in template]
    for bone in imported_rig.pose.bones:
        bone.custom_shape = None
    for ob in imported:
        if ob not in template:
            bpy.data.objects.remove(ob, do_unlink=True)
    actions = [a for a in bpy.data.actions if a not in existing_actions]
    clips = {}
    for name in ("Idle", "Walk"):
        matches = [a for a in actions if a.name.split(".")[0] == name or a.name.startswith(name + "_")]
        assert len(matches) == 1, (name, [a.name for a in actions])
        clips[name] = matches[0]
        clips[name].use_fake_user = True
    fps = capture["fps"]
    scene.render.fps = fps
    scene.frame_start = 1
    scene.frame_end = 1 + round(capture["duration"] * fps)
    inventory = {"vehicles": 0, "pedestrians": 0, "rigs": 0, "promotedSourceVehicles": 0}
    palette_cache = {}
    for actor in capture["actors"]:
        # Promoted actor IDs equal retained source IDs; use an explicit display
        # prefix rather than Blender's automatic .001 name collision suffix.
        actor_name = "CityLife__" + actor["id"] if actor.get("sourceInstanceId") else actor["id"]
        ob = bpy.data.objects.new(actor_name, None)
        ob.empty_display_type = "PLAIN_AXES"
        ob.empty_display_size = 0.3
        ob["city_life"] = True
        ob["actor_type"] = actor["type"]
        ob["runtime_actor_id"] = actor["id"]
        collection.objects.link(ob)
        route_keys(ob, actor["samples"], fps)
        if actor["type"] == "vehicle":
            source_id = actor.get("sourceInstanceId")
            if source_id:
                original = source_objects[source_id]
                mesh = original.data
                assert mesh == bpy.data.meshes[actor["prototype"] + "_EditableMesh"]
                original.hide_render = True
                original.hide_viewport = True
                original.hide_set(True)
                ob["source_instance_id"] = source_id
                inventory["promotedSourceVehicles"] += 1
            else:
                mesh = bpy.data.meshes[actor["prototype"] + "_EditableMesh"]
            scale = actor.get("scale", source_vehicles[source_id]["scale"] if source_id else 1)
            ob.scale = (scale, scale, scale) if isinstance(scale, (int, float)) else (scale[0], scale[2], scale[1])
            ob["runtime_vehicle_prototype"] = actor["prototype"]
            body = bpy.data.objects.new(actor_name + "__body", mesh)
            body["city_life"] = True
            if source_id:
                body["source_instance_id"] = source_id
            body.parent = ob
            collection.objects.link(body)
            inventory["vehicles"] += 1
        else:
            s = actor.get("scale", 1)
            ob.scale = (s, s, s) if isinstance(s, (int, float)) else (s[0], s[2], s[1])
            children = clone_character(template, collection, actor["id"], ob)
            apply_palette(children, actor.get("materialColors", {}), palette_cache)
            rigs = [child for child in children if child.type == "ARMATURE"]
            assert len(rigs) == 1
            rig = rigs[0]
            assert len(rig.data.bones) == 49
            animate_rig(rig, clips, actor["samples"], fps, scene.frame_end)
            inventory["pedestrians"] += 1
            inventory["rigs"] += 1
    for ob in template:
        bpy.data.objects.remove(ob, do_unlink=True)
    scene.frame_set(1)
    scene["city_life_capture"] = str(SAMPLES.relative_to(ROOT)).replace("\\", "/")
    scene["city_life_duration_seconds"] = capture["duration"]
    scene["city_life_note"] = "Editable route preview sampled from the continuous local simulation. Walk and Idle use the validated character export."
    after = static_signature()
    assert before == after, (before, after)
    visibility_after = static_visibility()
    assert visibility_before.keys() == visibility_after.keys()
    changed_visibility = [key for key in visibility_before if visibility_before[key] != visibility_after[key]]
    assert set(changed_visibility).issubset(source_vehicles), changed_visibility
    assert all(visibility_after[key] == (True, True, True) for key in source_vehicles)
    assert inventory == {"vehicles": 562, "pedestrians": 80, "rigs": 80, "promotedSourceVehicles": 478}, inventory
    assert sha(canonical) == canonical_before
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    report = {"passed": True, "inventory": inventory, "staticBefore": before, "staticAfter": after,
              "vehiclePromotion": {"expectedCount": EXPECTED_SOURCE_VEHICLES,
                                   "sourceInstanceIds": sorted(source_vehicles),
                                   "hiddenOriginals": len(source_vehicles),
                                   "animatedRepresentatives": inventory["promotedSourceVehicles"],
                                   "changedSourceVisibilityIds": sorted(changed_visibility),
                                   "nonVehicleVisibilityBefore": non_vehicle_visibility_signature(visibility_before, source_vehicles),
                                   "nonVehicleVisibilityAfter": non_vehicle_visibility_signature(visibility_after, source_vehicles),
                                   "nonVehicleVisibilityUnchanged": True,
                                   "allSourceGeometryAndTransformsUnchanged": before == after},
              "sourceHash": scene["source_hash"], "captureSHA256": sha(SAMPLES), "characterGLBSHA256": sha(asset),
              "canonicalCharacterSHA256": canonical_before, "canonicalCharacterUnchanged": True,
              "fps": fps, "durationSeconds": capture["duration"], "sampleHz": capture["sampleHz"],
              "frameRange": [scene.frame_start, scene.frame_end], "clips": {n: list(a.frame_range) for n, a in clips.items()},
              "scope": "Recorded route segment; continuous routing and signals run in the viewer."}
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
