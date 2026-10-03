"""Compile the delivery report from measured final-scene evidence."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))

def main():
    metrics = read("validation_metrics.json")
    blend = read("blender_validation.json")
    runtime = read("viewer/runtime_validation.json")
    profile = read("viewer/render_profile.json")
    spec = read("scene_spec.json")
    checks = metrics["checks"]
    source_hash = checks["build_hash"]["declared_source_hash"]
    assert blend["sourceHash"] == source_hash
    assert runtime.get("source", {}).get("sourceHash") == source_hash, "Stale runtime validation"
    assert profile["source"]["sourceHash"] == source_hash
    inv = checks["inventory"]
    geometry = checks["geometry_buffer"]
    review_path = ROOT / "comparisons/final_review.json"
    review_note = "[Independent visual review](comparisons/final_review.json)." if review_path.exists() else ""
    checkpoint_rows = [
        (1, "Map boundaries", "Used a 1450:1088 working frame for the 1448 × 1086 reference, with north up and west left. The surrounding greenbelt follows this frame."),
        (2, "Lake", "Traced the western shoreline and principal islands; made two closed offset circuits. Kept the housing corridor east of the water. Numerical water coverage is below the separate 25–30% target."),
        (3, "Main roads", "Aligned the main east–west streets and north–south avenues to image datums. Corrected shore-road approaches that did not meet the grid."),
        (4, "Central park", "Locked the 249 × 940.5 m park envelope, northern pond, southern lawns and cultural building. Added actual supported bridge geometry where paths cross water."),
        (5, "Districts", "Reserved western housing, eastern downtown, northern sports and southeastern transport. Removed a road that cut through the athletics track."),
        (6, "Main buildings", "Replaced whole-block shoreline rejection with individual footprint checks, tightened housing placement and filled missing north/south blocks. Buildings stay out of roads, water and protected park space."),
        (7, "Skyline", "Concentrated all 58 buildings above 45 m east of the park. Reduced empty gaps between tower groups and kept mid-rise transition blocks."),
        (8, "Vegetation", "Increased mature crowns and clustered woodland density; retained open park lawns, circulation and civic sightlines. The result remains more stylized than the image."),
        (9, "Secondary routes", "Clipped residential road spurs at the waterfront boulevard, moved viewpoints onto dry land, completed marina access and added block paths, front walks and gardens."),
        (10, "Final reference review", "Rechecked all nine top-down cells, cleared small furniture intrusions and museum approaches, rerouted fountain paths, removed terrain layers below water, then reopened the final Blender file."),
    ]
    rows = "\n".join(f"| {n:02d} | {name} | {note} | [Image](comparisons/checkpoint_{n:02d}.png) |" for n, name, note in checkpoint_rows)
    runtime_rows = []
    for key, result in runtime.get("checks", {}).items():
        if isinstance(result, dict):
            status = result.get("status", "recorded")
            runtime_rows.append(f"| {key} | {status} |")
    perf_rows = []
    for name, result in runtime.get("performance", {}).items():
        if not isinstance(result, dict):
            continue
        intervals = result.get("frameIntervalMs", {})
        cpu = result.get("cpuCallbackMs", {})
        if intervals.get("p50"):
            median = intervals["p50"]
            perf_rows.append(f"| {name} | {result.get('samples', '—')} | {median:.1f} ms / {1000 / median:.1f} FPS | {intervals.get('p95', 0):.1f} ms | {cpu.get('p50', 0):.1f} ms |")
    loops = checks["lake_loops"]["loops"]
    loop_text = "; ".join(f"{p['length_m']:,.2f} m long, {p['width_m']:.1f} m wide" for p in loops)
    text = f"""# Westmere — Lake City validation

The editable Blender city and local desktop WebGPU viewer are built from the same scene. The reference's large-scale arrangement is reproduced: western lake, housing buffer, long central park, eastern tower district, northern sports campus and southeastern station. Source geometry and spatial checks pass. Visual fidelity is partial: buildings, planting, junctions and surface detail are simpler and more regular than the photographic target. A 9/10 photographic similarity is **not** claimed.

## Delivered environment

- [Editable Blender scene](Lake_City.blend), reopened in a fresh Blender process and rendered successfully.
- Local viewer: <http://127.0.0.1:4173/>. Desktop WebGPU is required.
- [Final reference comparison](comparisons/final_reference_grid.png), [nine-view render sheet](renders/pass_4/contact_sheet.png), [overview](renders/pass_4/overview.png), and [semantic map](semantic_layout.png).
- [Shared specification](scene_spec.json), [region connections](region_graph.json), [asset registry](asset_registry.json), [animation manifest](animation_manifest.json), and reproducible scene scripts.

The map measures **2,175 × 1,632 m** (3.55 km²). The reference is 1448 × 1086 pixels, interpreted on a 1450 × 1088 working canvas (a sub-0.2% normalization). Scale is 1.5 m per working pixel. Runtime axes are X east, Y up, Z south; Blender uses X east, Y north, Z up. The ground surface is flat by design. Buildings have modeled exterior detail and closed interiors. Vehicles, vegetation and water are static; no animation was requested.

There are **{inv['instances']:,} placed instances**, **{inv['prototypes']} reusable prototypes**, **567 buildings**, and **58 towers above 45 m**, all east of the park. Heights range up to 130.83 m. Architectural families include detached houses, townhouses, apartments, shops, towers, schools, library, city hall, museum, sports hall, hotel and station. Public-realm assets include trees, shrubs, street furniture, bus shelters, cars, bicycles, boats, playground equipment and sports facilities. All assets are original procedural geometry; no paid or downloaded asset packs were used.

## Repeated reference checks

The original reference was reopened during construction. Each numbered image pairs it with a real top-down Blender render. Checkpoints 01–09 also have incremental saved Blender files; checkpoint 10 is the final scene. Early checkpoint images document intermediate states, not the final asset inventory.

| Checkpoint | Stage | Findings and corrections | Evidence |
|---|---|---|---|
{rows}

The long park is **249 × 940.5 m**, with a 3.78:1 aspect ratio. Its location and the housing separation from the lake follow the image. The lake has **3 wooded islands** and a marina. The complete pedestrian and cycling circuits are respectively {loop_text}. Both are simple closed rings with zero endpoint gap and no unsupported water overlap.

**Lake area conflict:** the constructed water polygon is {checks['major_layout']['lake_water_area_m2']:,.2f} m², or **16.8% of the full map**, rather than the requested 25–30%. The reference outline and district spacing were prioritized over enlarging the lake into housing. This numeric requirement remains unmet. Shoreland and lake bounding rectangles must not be reported as water area.

{review_note}

## Three render–inspect–refine passes

Each pass contains the actual same nine named camera renders: top, overview, lakeside approach, park lawn, downtown street, residential, sports, station and reverse park entrance.

| Pass | Observed issue | Correction and subsequent evidence |
|---|---|---|
| [1](renders/pass_1/contact_sheet.png) | The museum entrance had crowded planting; the lake camera stood over water; aerial depth precision produced surface interference. | Moved the lake camera onto the loop, cleared the museum forecourt, aligned its approach camera and increased the aerial near clipping distance. |
| [2](renders/pass_2/contact_sheet.png) | Museum access and street views improved, but overlapping sand/ground layers still produced visible triangular patches in the lake from oblique views. | Cut actual lake, pond and river holes into underlying terrain; made shore bands proper rings. Filled the southern block below the playing field and adjusted the overview framing. |
| [3](renders/pass_3/contact_sheet.png) | Water edges were clean, the museum approach was open, station geometry was visible, and main spatial relationships remained stable. | Inspected all nine views and the original reference again; saved, reopened and rendered the final file. Remaining simplification and density differences are documented below. |
| [Final targeted check](renders/pass_4/contact_sheet.png) | A runtime close view exposed a tree intersecting a bus shelter. | Cleared actual tree/shelter overlaps, rerendered the nine cameras, reopened Blender again and reran runtime checks against the final source. |

Representative house, apartment, tower, school and museum assets also have isolated renders under [architecture kit](renders/architecture_kit/). The [landscape kit](renders/landscape_kit.png) records vegetation and public-realm prototypes. Linked mesh instances preserve editability; regeneration uses the same stable semantic IDs and shared definitions.

## Geometry, placement and saved-file verification

[Measured scene audit](validation_metrics.json): **{metrics['status']}**, with {len(metrics['failures'])} failures. The two warnings are the lake-area conflict and two parcels with less than 3% building footprint coverage. Those parcels are a small north planting space and the southern soccer grounds, rather than missing downtown blocks.

- Regenerated and compared every exported mesh attribute and triangle index against source parts: **{checks['source_geometry_transfer']['matched_meshes']} matching mesh parts**, no mismatches.
- **{geometry['unique_triangles']:,} unique triangles; {geometry['instanced_triangles']:,} represented triangles.** Uncompressed geometry occupies {geometry['binary_bytes'] / 1e6:.2f} MB. Positions/normals are finite, indices valid, source/registry inventories match, and duplicate IDs are absent.
- Conservative actual mesh bounds find **zero building overlaps with roads, sidewalks, water or protected park space**, and zero building-envelope collisions.
- Declared pedestrian routes have zero building collisions and zero unsupported lake/pond crossings. Road paths have no unsupported water crossings. Furniture was moved away from reserved routes.
- [Bridge and dock supports](connection_validation.json) include the 188.89 m park bridge, secondary crossing, marina spine, fingers and shore approach. The controller uses matching support geometry.
- [Fresh Blender reopen](blender_validation.json) verifies {blend['meshObjects']:,} mesh objects, {blend['uniqueMeshes']} shared meshes, {blend['visibleTriangles']:,} represented triangles, nine cameras, and no external image dependencies. [Reopened-file render](renders/reopened_top.png) confirms renderability.

Full source identity: `{source_hash}`. Geometry SHA-256: `{geometry['binary_sha256']}`.

## Desktop viewer verification

[Runtime results](viewer/runtime_validation.json) record the actual browser, device, checks, samples and served-file hashes. [Render profile](viewer/render_profile.json) records versions, quality, pass ownership and cache dependencies. These two files refer to the same source identity as Blender.

The final build uses Three.js {profile['versions']['three']} with Vite {profile['versions']['vite']}. Hardware WebGPU was confirmed on a non-fallback NVIDIA Ampere adapter. Test conditions were isolated desktop Chromium at 1600 × 1000, device-pixel-ratio 1. The user's browser was not opened or controlled.

| Runtime check | Result |
|---|---|
{chr(10).join(runtime_rows)}

The walking controller has a 1.72 m eye height, 0.32 m body radius, 1.78 m body height, 0.45 m step height, 3.9 m/s walking and 11.5 m/s fast movement. Runtime traversal and geometry clearance are separate checks; static render evidence alone is not used to claim navigation success. See the runtime file for full-circle lake traversal, bridges/docks, pedestrian-network samples and actual keyboard/mouse results.

Rendering retains all source positions, normals, triangle indices and instance matrices. It uses material batching and per-pass frustum culling, **no LOD, mesh simplification, texture reduction, compression or dynamic resolution**. Lighting uses a procedural sky and sun, 4096² cached static sun shadows, native-resolution camera-correct water reflections and PBR surfaces. Static idle images reuse the completed frame. Camera movement and relevant shadow changes invalidate their dependent work. Blender and WebGPU use different rendering engines; pixel identity is not promised.

| View | Samples | Median frame interval / equivalent FPS | 95th percentile | Median CPU callback |
|---|---|---|---|---|
{chr(10).join(perf_rows)}

These are observed frame intervals on this desktop, not guaranteed frame rates. Full-city aerial movement is substantially slower than street exploration. GPU timestamp timings are unavailable in the test, so CPU callback duration is not presented as GPU execution time. Native physical Escape/Keyboard Lock behavior was not established by headless automation; the tested pause state and fullscreen API transitions are recorded separately.

## Remaining limits

- The photographic reference has denser and more irregular built footprints, richer tree canopies, complex junction geometry and finer material variation. This is a coherent procedural, stylized reconstruction of its layout, not a photoreal replica. The environment-wide 9/10 visual-fidelity target is not established.
- Water coverage is 16.8%, below the requested 25–30%; enlarging it would alter the reference layout. Park paths and pond details approximate the image rather than tracing every internal feature.
- Some large boulevards and highway junctions use simplified ground-level geometry. Surrounding forests, river and suburban continuations soften the boundary, but the world remains finite and mostly flat.
- Buildings are exterior-only. Static parked vehicles and railway infrastructure do not provide traffic, transport simulation or enterable interiors.
- The full-detail plan is expensive to redraw. Walking performance is better, but the measured timings should be considered before using this scene on less powerful hardware. Mobile support was not requested or tested.

Controls: choose **Explore on foot**, use **WASD or ZQSD** and mouse look, hold **Shift** to move faster, and press **Escape** to pause. Use **Aerial**, **City plan**, **Places** and the fullscreen control for inspection.
"""
    revision = ROOT / "validation/revision_01.md"
    if revision.exists():
        text = text.replace("# Westmere — Lake City validation", "# Westmere — Lake City validation\n\nLatest correction: [movement stability and tree grounding](#movement-stability-and-tree-grounding). Current close views are in [revision_01](renders/revision_01/); the four complete review passes below remain historical evidence.", 1)
        text += "\n\n" + revision.read_text(encoding="utf-8").replace("](../", "](")
    life = ROOT / "validation/city_life.md"
    if life.exists():
        text = text.replace("# Westmere — Lake City validation", "# Westmere — Lake City validation\n\nLatest addition: [automatic traffic and walking pedestrians](#automatic-traffic-and-walking-pedestrians).", 1)
        text = text.replace("Vehicles, vegetation and water are static; no animation was requested.", "Automatic road traffic and walking pedestrians animate the city. Every original car is promoted into traffic; vegetation and water geometry remain static.")
        text = text.replace("placed instances**,", "authored source instances**,", 1)
        text = text.replace("mesh objects,", "authored source mesh objects (including hidden fixed vehicle originals),", 1)
        text = text.replace("All assets are original procedural geometry; no paid or downloaded asset packs were used.", "The static city uses original procedural geometry. Pedestrians use the exact locally generated CharacterBase and the skill's private bundled animation package; no paid assets were acquired.")
        text = text.replace("4096² cached static sun shadows", "separate full-resolution 4096² static and moving-object sun shadow maps")
        text = text.replace("Static idle images reuse the completed frame.", "Traffic and pedestrians continue to animate while the camera is stationary.")
        text = text.replace("Static parked vehicles and railway infrastructure do not provide traffic, transport simulation or enterable interiors.", "All car props participate in automatic traffic. Railway infrastructure remains static and buildings have no enterable interiors.")
        text += "\n\n" + life.read_text(encoding="utf-8").replace("](../", "](")
    (ROOT / "validation_report.md").write_text(text, encoding="utf-8")
    print(json.dumps({"report": str(ROOT / "validation_report.md"), "sourceHash": source_hash, "runtimeTimestamp": runtime.get("timestamp")}, indent=2))

if __name__ == "__main__":
    main()
