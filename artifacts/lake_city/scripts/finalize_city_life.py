"""Refresh existing environment records from the verified animated revision."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8-sig"))


def write(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    capture = read("validation/city_life_samples.json")
    source = read("viewer/public/assets/city.json")
    network = read("viewer/public/assets/traffic_network.json")
    traffic = read("comparisons/traffic_simulation_report.json")
    promotion = read("viewer/vehicle_promotion_validation.json")
    assert not promotion.get("failure") and not promotion.get("errors")
    assert all(check.get("status") == "passed" for check in promotion["checks"].values())
    character = read("characters/character_final_audit.json")
    blend = read("validation/city_life_blender.json")
    reopened = read("blender_validation.json")
    runtime_character = read("viewer/public/assets/characters/pedestrian.json")
    assert traffic["passed"] and character["passed"] and blend["passed"]
    assert reopened["status"] == "passed" and reopened["cityLife"]["pedestrians"] > 0
    assert hashlib.sha256((ROOT / "validation/city_life_samples.json").read_bytes()).hexdigest() == blend["captureSHA256"], "Blender preview capture is stale"
    assert source["sourceHash"] == network["sourceHash"] == blend["sourceHash"] == reopened["sourceHash"]
    counts = Counter(a["type"] for a in capture["actors"])
    assert reopened["cityLife"]["vehicles"] == counts["vehicle"], "Fresh Blender reopen predates this fleet"
    assert blend["inventory"]["vehicles"] == counts["vehicle"]
    source_vehicles = {i["id"]: i for i in source["instances"] if i["prototype"] in {"car_sedan", "car_suv", "delivery_van"}}
    promoted = [a for a in capture["actors"] if a.get("sourceInstanceId")]
    assert len(promoted) == len(source_vehicles) and {a["sourceInstanceId"] for a in promoted} == set(source_vehicles)
    assert all(a["prototype"] == source_vehicles[a["sourceInstanceId"]]["prototype"] for a in promoted)
    assert blend["inventory"]["promotedSourceVehicles"] == len(promoted)
    assert promotion["checks"]["exactSourceIdentity"]["sourceCars"] == len(promoted)
    assert promotion["captureSHA256"] == blend["captureSHA256"]
    dependencies = ["viewer/public/assets/characters/pedestrian.glb", "viewer/public/assets/traffic_network.json",
                    "viewer/src/traffic.ts", "viewer/src/traffic-signals.ts", "viewer/src/pedestrians.ts", "viewer/src/life.ts", "viewer/src/ground.ts",
                    "viewer/src/scene.ts", "viewer/src/collision.ts", "viewer/src/types.ts", "viewer/src/main.ts"]
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in dependencies}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    animation = {
        "revision": 2, "staticSourceHash": source["sourceHash"], "lifeHash": identity, "dependencies": hashes,
        "animatedSystems": [
            {"id": "CITY_TRAFFIC", "instances": counts["vehicle"], "runtime": "viewer/src/traffic.ts",
             "mode": "continuous deterministic lane simulation", "fixedStepHz": 30, "seed": 1937,
             "network": "viewer/public/assets/traffic_network.json", "laneCount": len(network["lanes"]),
             "junctionCount": len(network["junctions"]), "rules": ["right-hand lanes", "following gaps", "signal phases", "junction reservations", "parked vehicle clearance"],
             "visibleSignalLenses": "viewer/src/traffic-signals.ts", "sourceVehiclesPromoted": len(promoted),
             "promotedSourceIds": sorted(source_vehicles), "fixedVehicles": 0,
             "sourceGeometry": "Exact original prototypes retained; fixed instances replaced one-to-one by moving actors"},
            {"id": "CITY_PEDESTRIANS", "instances": counts["pedestrian"], "runtime": "viewer/src/pedestrians.ts",
             "mode": "safe sidewalk and park routes with passing, pauses and returns", "fixedStepHz": 30,
             "asset": "viewer/public/assets/characters/pedestrian.glb", "source": "characters/CharacterBase.blend",
             "trianglesPerActor": runtime_character["total_triangles"], "bonesPerActor": 49,
             "clips": {name: {"durationSeconds": runtime_character["clips"][name]["duration_seconds"], "loop": True} for name in ("Walk", "Idle")},
             "groundContact": "Actual support triangles with clip-aware foot offset", "palette": "Runtime material variants; canonical meshes and rig unchanged"}
        ],
        "blenderPreview": {"file": "Lake_City.blend", "collection": "CITY_LIFE", "fps": capture["fps"],
                           "durationSeconds": capture["duration"], "routeSampleHz": capture["sampleHz"],
                           "capture": "validation/city_life_samples.json",
                           "scope": "Editable recorded segment of the live simulation; continuous routing executes in the local viewer."},
        "staticSystems": ["architecture", "terrain", "vegetation", "water geometry", "railway"]
    }
    write("animation_manifest.json", animation)
    spec = read("scene_spec.json")
    spec["navigation"]["staticEnvironment"] = False
    spec["cityLife"] = {"manifest": "animation_manifest.json", "vehicles": counts["vehicle"], "sourceVehiclesPromoted": len(promoted), "fixedVehicles": 0, "pedestrians": counts["pedestrian"], "fixedStepHz": 30, "staticLayoutPreserved": True}
    for requirement in ["Automatic road traffic respecting other vehicles and controlled intersections", "Characters from blender-lowpoly-character with the bundled Walk animation", "Every original car participates in live traffic; no permanently fixed car props remain"]:
        if requirement not in spec["explicitRequirements"]:
            spec["explicitRequirements"].append(requirement)
    write("scene_spec.json", spec)
    registry = read("asset_registry.json")
    registry["animatedAssets"] = {"manifest": "animation_manifest.json", "characterSource": "characters/CharacterBase.blend", "runtimeCharacter": "viewer/public/assets/characters/pedestrian.glb", "sourceCharacterSHA256": character["source_sha256"], "lifeHash": identity, "vehicleInstances": counts["vehicle"], "sourceVehiclesPromoted": len(promoted), "fixedVehicleInstances": 0, "pedestrianInstances": counts["pedestrian"], "provenance": "Existing original city vehicle prototypes and exact local blender-lowpoly-character geometry with the skill's private animation package. No paid assets or remote services."}
    write("asset_registry.json", registry)
    final = traffic["final"]
    text = f"""## Automatic traffic and walking pedestrians

The city now contains **{counts['vehicle']} moving vehicles** and **{counts['pedestrian']} walking characters**. All **{len(promoted)} original car props** are represented one-to-one by moving actors using their exact original geometry and prototype. No fixed visible cars remain in the viewer or saved Blender scene. The [vehicle promotion regression](../viewer/vehicle_promotion_validation.json) verifies source identities, absent fixed draw submissions and colliders, actual rendered transforms, and progress for every car. Source placements remain stored for editability, with the fixed copies hidden and excluded from static collision. The western lake, central park, housing and eastern skyline remain in place.

Traffic follows {len(network['lanes'])} directed lanes and {len(network['turns'])} authored-road turns through {len(network['junctions'])} connected junctions. Cars follow other cars, wait for signal phases and reserved junctions, and accelerate again when space opens. Existing signal lenses display the simulation phase. Temporary stops at red lights and in queues are expected; permanently decorative cars are not. A stationary roadside camera records the same promoted source car [before](../renders/vehicle-promotion/promoted-car-a.png) and [one second later](../renders/vehicle-promotion/promoted-car-b.png). The route graph retains conservative curb clearances and excludes narrow streets and unsupported dead ends. It is an ambient traffic system; vehicles are not player-drivable.

Pedestrians use the skill's exact 49-bone CharacterBase, its fixed shirt and trousers, and original **Walk** and **Idle** clips. Colors vary per person, with shared full-detail geometry. Routes use sidewalks, park paths and the lakeside circuit. Ground height comes from actual surface triangles. Pedestrians stay within safe corridors rather than crossing live traffic uncontrolled.

The viewer runs continuously, including with a stationary camera. The editable [Blender city](../Lake_City.blend) also contains a **{capture['duration']}-second route preview at {capture['fps']} FPS**, sampled from the real simulation at {capture['sampleHz']} Hz. Original Walk/Idle clips drive the independent rigs. This recorded timeline is a preview segment; the viewer supplies ongoing junction decisions and routing. [Saved-scene close views](../renders/life_blender/) show the actual animation. Blender blends transition rotations slightly differently from Three.js. The character acceptance [foot audit](../validation/city_life_foot_audit.json), recorded before vehicle promotion with the same character geometry and clips, found a maximum upward sole gap below 1 cm at its two sampled frames; one blended pose penetrated the path by 3.95 cm. There is no systematic floating transform.

Validation: the [traffic simulation audit](../comparisons/traffic_simulation_report.json) covers {traffic['durationSeconds'] / 60:g} simulated minutes, with zero vehicle overlaps and zero off-route samples. It recorded {final['completedTurns']:,} completed turns, {final['redStops']:,} signal stops and {final['restarts']:,} restarts. Frame-rate determinism passed. Every vehicle advanced in each 120-second interval across the full run; the minimum interval distance was {traffic['minimum120SecondProgress']:.2f} m and the longest temporary stop was {final['longestWaitSeconds']:.1f} seconds. [Character validation](../characters/character_final_audit.json), [runtime character transfer](../viewer/public/assets/characters/pedestrian.json), [Blender animation integration](../validation/city_life_blender.json) and the [fresh Blender reopen](../blender_validation.json) record source integrity, real clips and saved-file animation. [Living-city desktop tests](../viewer/life_validation.json) and [current runtime measurements](../viewer/runtime_validation.json) cover actual rendered operation and its performance.

Character files: [canonical Blender](../characters/CharacterBase.blend), [neutral FBX](../characters/CharacterBase.fbx), [neutral GLB](../characters/CharacterBase.glb), [runtime animated GLB](../viewer/public/assets/characters/pedestrian.glb), [Idle](../characters/anim/idle.fbx), [Walk](../characters/anim/walk.fbx), [Run](../characters/anim/run.fbx), [Jump](../characters/anim/jump.fbx). Run and Jump are validated available exports; the city uses Walk and Idle. [Walk pose sheet](../characters/qc_walk.png), [animation matrix validation](../characters/CharacterBase_animation_validation.json), [animation QC](../characters/CharacterBase_animation_qc.json), [export/reimport workflow](../characters/reports/CharacterBase_export_workflow.json).

Animation identity: `{identity}`. Static city identity remains `{source['sourceHash']}`. No geometry reduction, reduced render resolution or remote hosting was introduced.
"""
    text += """
### Character validation files

- Base and outfit: [base build](../characters/CharacterBase_base_report.json), [final audit](../characters/character_final_audit.json), [current outfit validation](../characters/reports/CharacterBase_current_outfit_validation.json), [outfit views](../characters/qc_outfit.png).
- Animation: [package](../characters/animation_package_report.json), [installation](../characters/CharacterBase_animation_install.json), [matrix validation](../characters/CharacterBase_animation_validation.json), [workflow](../characters/CharacterBase_animation_workflow.json), [QC](../characters/CharacterBase_animation_qc.json).
- Pose sheets: [Idle](../characters/qc_idle.png), [Walk](../characters/qc_walk.png), [Run](../characters/qc_run.png), [Jump](../characters/qc_jump.png).
- Final exports: [workflow](../characters/reports/CharacterBase_export_workflow.json), [export report](../characters/reports/CharacterBase_export.json), [FBX reimport](../characters/reports/CharacterBase_fbx_validation.json), [GLB reimport](../characters/reports/CharacterBase_glb_validation.json).
- Animation reimports: [Idle](../characters/reports/anim/idle_fbx_validation.json), [Walk](../characters/reports/anim/walk_fbx_validation.json), [Run](../characters/reports/anim/run_fbx_validation.json), [Jump](../characters/reports/anim/jump_fbx_validation.json).
"""
    (ROOT / "validation/city_life.md").write_text(text, encoding="utf-8")
    print(json.dumps({"lifeHash": identity, "counts": dict(counts), "manifest": "animation_manifest.json"}, indent=2))


if __name__ == "__main__":
    main()
