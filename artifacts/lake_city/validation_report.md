# Westmere — Lake City validation

Latest addition: [automatic traffic and walking pedestrians](#automatic-traffic-and-walking-pedestrians).

Latest correction: [movement stability and tree grounding](#movement-stability-and-tree-grounding). Current close views are in [revision_01](renders/revision_01/); the four complete review passes below remain historical evidence.

The editable Blender city and local desktop WebGPU viewer are built from the same scene. The reference's large-scale arrangement is reproduced: western lake, housing buffer, long central park, eastern tower district, northern sports campus and southeastern station. Source geometry and spatial checks pass. Visual fidelity is partial: buildings, planting, junctions and surface detail are simpler and more regular than the photographic target. A 9/10 photographic similarity is **not** claimed.

## Delivered environment

- [Editable Blender scene](Lake_City.blend), reopened in a fresh Blender process and rendered successfully.
- Local viewer: <http://127.0.0.1:4173/>. Desktop WebGPU is required.
- [Final reference comparison](comparisons/final_reference_grid.png), [nine-view render sheet](renders/pass_4/contact_sheet.png), [overview](renders/pass_4/overview.png), and [semantic map](semantic_layout.png).
- [Shared specification](scene_spec.json), [region connections](region_graph.json), [asset registry](asset_registry.json), [animation manifest](animation_manifest.json), and reproducible scene scripts.

The map measures **2,175 × 1,632 m** (3.55 km²). The reference is 1448 × 1086 pixels, interpreted on a 1450 × 1088 working canvas (a sub-0.2% normalization). Scale is 1.5 m per working pixel. Runtime axes are X east, Y up, Z south; Blender uses X east, Y north, Z up. The ground surface is flat by design. Buildings have modeled exterior detail and closed interiors. Automatic road traffic and walking pedestrians animate the city. Every original car is promoted into traffic; vegetation and water geometry remain static.

There are **12,488 authored source instances**, **111 reusable prototypes**, **567 buildings**, and **58 towers above 45 m**, all east of the park. Heights range up to 130.83 m. Architectural families include detached houses, townhouses, apartments, shops, towers, schools, library, city hall, museum, sports hall, hotel and station. Public-realm assets include trees, shrubs, street furniture, bus shelters, cars, bicycles, boats, playground equipment and sports facilities. The static city uses original procedural geometry. Pedestrians use the exact locally generated CharacterBase and the skill's private bundled animation package; no paid assets were acquired.

## Repeated reference checks

The original reference was reopened during construction. Each numbered image pairs it with a real top-down Blender render. Checkpoints 01–09 also have incremental saved Blender files; checkpoint 10 is the final scene. Early checkpoint images document intermediate states, not the final asset inventory.

| Checkpoint | Stage | Findings and corrections | Evidence |
|---|---|---|---|
| 01 | Map boundaries | Used a 1450:1088 working frame for the 1448 × 1086 reference, with north up and west left. The surrounding greenbelt follows this frame. | [Image](comparisons/checkpoint_01.png) |
| 02 | Lake | Traced the western shoreline and principal islands; made two closed offset circuits. Kept the housing corridor east of the water. Numerical water coverage is below the separate 25–30% target. | [Image](comparisons/checkpoint_02.png) |
| 03 | Main roads | Aligned the main east–west streets and north–south avenues to image datums. Corrected shore-road approaches that did not meet the grid. | [Image](comparisons/checkpoint_03.png) |
| 04 | Central park | Locked the 249 × 940.5 m park envelope, northern pond, southern lawns and cultural building. Added actual supported bridge geometry where paths cross water. | [Image](comparisons/checkpoint_04.png) |
| 05 | Districts | Reserved western housing, eastern downtown, northern sports and southeastern transport. Removed a road that cut through the athletics track. | [Image](comparisons/checkpoint_05.png) |
| 06 | Main buildings | Replaced whole-block shoreline rejection with individual footprint checks, tightened housing placement and filled missing north/south blocks. Buildings stay out of roads, water and protected park space. | [Image](comparisons/checkpoint_06.png) |
| 07 | Skyline | Concentrated all 58 buildings above 45 m east of the park. Reduced empty gaps between tower groups and kept mid-rise transition blocks. | [Image](comparisons/checkpoint_07.png) |
| 08 | Vegetation | Increased mature crowns and clustered woodland density; retained open park lawns, circulation and civic sightlines. The result remains more stylized than the image. | [Image](comparisons/checkpoint_08.png) |
| 09 | Secondary routes | Clipped residential road spurs at the waterfront boulevard, moved viewpoints onto dry land, completed marina access and added block paths, front walks and gardens. | [Image](comparisons/checkpoint_09.png) |
| 10 | Final reference review | Rechecked all nine top-down cells, cleared small furniture intrusions and museum approaches, rerouted fountain paths, removed terrain layers below water, then reopened the final Blender file. | [Image](comparisons/checkpoint_10.png) |

The long park is **249 × 940.5 m**, with a 3.78:1 aspect ratio. Its location and the housing separation from the lake follow the image. The lake has **3 wooded islands** and a marina. The complete pedestrian and cycling circuits are respectively 3,329.51 m long, 5.4 m wide; 3,379.27 m long, 3.4 m wide. Both are simple closed rings with zero endpoint gap and no unsupported water overlap.

**Lake area conflict:** the constructed water polygon is 596,169.37 m², or **16.8% of the full map**, rather than the requested 25–30%. The reference outline and district spacing were prioritized over enlarging the lake into housing. This numeric requirement remains unmet. Shoreland and lake bounding rectangles must not be reported as water area.

[Independent visual review](comparisons/final_review.json).

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

[Measured scene audit](validation_metrics.json): **PASS_WITH_WARNINGS**, with 0 failures. The two warnings are the lake-area conflict and two parcels with less than 3% building footprint coverage. Those parcels are a small north planting space and the southern soccer grounds, rather than missing downtown blocks.

- Regenerated and compared every exported mesh attribute and triangle index against source parts: **698 matching mesh parts**, no mismatches.
- **531,206 unique triangles; 80,292,494 represented triangles.** Uncompressed geometry occupies 44.62 MB. Positions/normals are finite, indices valid, source/registry inventories match, and duplicate IDs are absent.
- Conservative actual mesh bounds find **zero building overlaps with roads, sidewalks, water or protected park space**, and zero building-envelope collisions.
- Declared pedestrian routes have zero building collisions and zero unsupported lake/pond crossings. Road paths have no unsupported water crossings. Furniture was moved away from reserved routes.
- [Bridge and dock supports](connection_validation.json) include the 188.89 m park bridge, secondary crossing, marina spine, fingers and shore approach. The controller uses matching support geometry.
- [Fresh Blender reopen](blender_validation.json) verifies 12,488 authored source mesh objects (including hidden fixed vehicle originals), 111 shared meshes, 80,802,518 represented triangles, nine cameras, and no external image dependencies. [Reopened-file render](renders/reopened_top.png) confirms renderability.

Full source identity: `317c413494035f83921d0d627a28744b85608b9c33aee65591fb7b0fffb9d7f5`. Geometry SHA-256: `f2d646142e821bc4b828099865063a78ebb42972eec9fc6e09c2b83cd84d74e8`.

## Desktop viewer verification

[Runtime results](viewer/runtime_validation.json) record the actual browser, device, checks, samples and served-file hashes. [Render profile](viewer/render_profile.json) records versions, quality, pass ownership and cache dependencies. These two files refer to the same source identity as Blender.

The final build uses Three.js 0.186.1 with Vite 8.3.2. Hardware WebGPU was confirmed on a non-fallback NVIDIA Ampere adapter. Test conditions were isolated desktop Chromium at 1600 × 1000, device-pixel-ratio 1. The user's browser was not opened or controlled.

| Runtime check | Result |
|---|---|
| localHTTP | passed |
| fleetPopulation | passed |
| exactSourceIdentity | passed |
| noFixedVehicleCopies | passed |
| sourceTransfer | passed |
| sourceAnimationCapture | passed |
| everyVehicleProgresses | passed |
| renderedActorMatrices | passed |
| stationaryCameraVehicleMotion | passed |
| noFixedVehicleDrawSubmissions | passed |
| movingVehiclePasses | passed |
| sequentialPassStability | passed |
| uncompressedTransport | passed |
| noRuntimeErrors | passed |
| frozenPixelStability | passed |
| visibleMotionPixels | passed |
| vehicleMeshIdentity | passed |
| nativeResolution | passed |
| hardwareWebGPU | passed |
| servedBuildIdentity | passed |

The walking controller has a 1.72 m eye height, 0.32 m body radius, 1.78 m body height, 0.45 m step height, 3.9 m/s walking and 11.5 m/s fast movement. Runtime traversal and geometry clearance are separate checks; static render evidence alone is not used to claim navigation success. See the runtime file for full-circle lake traversal, bridges/docks, pedestrian-network samples and actual keyboard/mouse results.

Rendering retains all source positions, normals, triangle indices and instance matrices. It uses material batching and per-pass frustum culling, **no LOD, mesh simplification, texture reduction, compression or dynamic resolution**. Lighting uses a procedural sky and sun, separate full-resolution 4096² static and moving-object sun shadow maps, native-resolution camera-correct water reflections and PBR surfaces. Traffic and pedestrians continue to animate while the camera is stationary. Camera movement and relevant shadow changes invalidate their dependent work. Blender and WebGPU use different rendering engines; pixel identity is not promised.

| View | Samples | Median frame interval / equivalent FPS | 95th percentile | Median CPU callback |
|---|---|---|---|---|
| plan | 45 | 166.7 ms / 6.0 FPS | 216.4 ms | 169.2 ms |
| walking | 62 | 50.0 ms / 20.0 FPS | 66.6 ms | 51.4 ms |

These are observed frame intervals on this desktop, not guaranteed frame rates. Full-city aerial movement is substantially slower than street exploration. GPU timestamp timings are unavailable in the test, so CPU callback duration is not presented as GPU execution time. Native physical Escape/Keyboard Lock behavior was not established by headless automation; the tested pause state and fullscreen API transitions are recorded separately.

## Remaining limits

- The photographic reference has denser and more irregular built footprints, richer tree canopies, complex junction geometry and finer material variation. This is a coherent procedural, stylized reconstruction of its layout, not a photoreal replica. The environment-wide 9/10 visual-fidelity target is not established.
- Water coverage is 16.8%, below the requested 25–30%; enlarging it would alter the reference layout. Park paths and pond details approximate the image rather than tracing every internal feature.
- Some large boulevards and highway junctions use simplified ground-level geometry. Surrounding forests, river and suburban continuations soften the boundary, but the world remains finite and mostly flat.
- Buildings are exterior-only. All car props participate in automatic traffic. Railway infrastructure remains static and buildings have no enterable interiors.
- The full-detail plan is expensive to redraw. Walking performance is better, but the measured timings should be considered before using this scene on less powerful hardware. Mobile support was not requested or tested.

Controls: choose **Explore on foot**, use **WASD or ZQSD** and mouse look, hold **Shift** to move faster, and press **Escape** to pause. Use **Aerial**, **City plan**, **Places** and the fullscreen control for inspection.


## Movement stability and tree grounding

This revision addresses the reported flickering/disappearing building walls and exposed, floating tree roots. The district layout, water outline, routes, building placements and all tree horizontal positions are preserved.

### Causes and corrections

**Disappearing facades.** Water reflections and sun shadows recursively rendered the same BatchedMesh objects while another camera's draw commands were still being prepared. Those nested passes changed the shared indirect instance-ID texture and draw ranges. The baseline audit captured wrong-camera draws and 100 recorded instance-ID overwrite events, including architectural materials. A matched-pose image differed from a diagnostic render containing all source geometry by 330,462 pixels; 305,933 pixels differed by more than 5/255 in at least one color channel.

The viewer now submits the sun-shadow update, the full-resolution reflection captures and the main view in explicit sequence. Each pass finishes command preparation and submission before another pass changes its visibility data. Per-object culling remains enabled for normal exploration. Geometry, native resolution, reflection resolution and shadow resolution are retained.

**Localized facade shimmer.** Window reveal surfaces touched their masonry opening faces at exactly the same depth, and tower corner casings shared a plane with terminal mullions. The source now separates those surfaces by 15 mm. The 1,600 reveal assemblies and 312 corner strips retain their part counts, triangle counts and collision bounds. [Source audit](comparisons/source_surface_audit.json) and [targeted correction audit](comparisons/source_surface_fix_validation.json) document the checks.

**Tree soil contact.** Tree placements used one fixed Y datum even though the visible ground includes several elevations. Some bases stood up to 28 cm above forest soil, while their modeled root flares rose approximately 76 cm above the prototype origin. Tree trunks now extend below ground, structural roots are buried, and the instance height is sampled from the actual rendered support triangles with a 6 cm embed. The compact collar replaces the exposed root cones. All canopy and branch geometry is retained.

All **9,391 trees** have supporting ground. Their structural roots finish at least **2.36 cm below soil**; trunk bases extend 0.528–1.074 m below it. A direct comparison with the previous exported placements found zero changes to tree X/Z coordinates, rotation, scale, IDs or prototype assignment. Grounding runs before local clearance and again after relocation. [Grounding measurements](tree_grounding_validation.json), [prototype and winding checks](validation/tree_anchoring_report.json), and [matched Blender views](comparisons/tree_grounding_before_after.png) provide evidence.

### Verification

- The source geometry and spatial audit has no failures. The two pre-existing composition warnings remain unchanged.
- The updated Blender scene was saved, reopened in a fresh process and rendered. Current source views are in [revision_01](renders/revision_01/); the final top-down reference comparison was refreshed and inspected.
- The moving-camera stability run covers **48 camera positions** across downtown, lakeside, park and residential routes, including shadow-region changes. The audit covered 33,842 batch draws with zero camera or indirect-ID state mismatches. All 16 culling-versus-full-source image pairs and all 48 identical-pose repeat pairs have zero changed pixels. [Stability results](viewer/stability_validation.json) record the final counts, matched-pose comparisons and repeated-frame results.
- [Runtime validation](viewer/runtime_validation.json) contains final-source geometry transfer, keyboard/mouse traversal, collision, reflection-plane, lifecycle, production-build and performance results. [Render profile](viewer/render_profile.json) records the sequential pass ownership.

The culling-disabled render is a diagnostic reference only; the delivered viewer retains culling and the full-detail source. The tests establish correction of the reproduced pass-state corruption and local coplanar facade defects. They do not claim that every distant thin leaf or window edge is mathematically alias-free while moving.

### Reference ledger

| Reference | Read | Applied checks |
|---|---|---|
| givros-environment-builder/SKILL.md | Yes | Limited revision, source/runtime parity, saved-file reopen, local delivery |
| givros-environment-builder/references/renderer-validation.md | Yes | Matched cameras, temporal rendering, pass ownership, geometry preservation |
| threejs-debug-profiler/references/debug-profile-checklists.md | Yes | Reproduction, current production build, root-cause isolation, regression testing |
| threejs-debug-profiler/references/checklists/scene-debugging.md | Yes | Camera, materials, winding, render loop, geometry, input and actual pixels |
| threejs-debug-profiler/references/checklists/performance-profile.md | Yes | Hardware/viewport conditions, frame intervals, render passes, unchanged quality |

No reference was skipped and no reference-loading failure occurred. The existing local address remains <http://127.0.0.1:4173/>. Reloading the open page loads the corrected build.


## Automatic traffic and walking pedestrians

The city now contains **562 moving vehicles** and **80 walking characters**. All **478 original car props** are represented one-to-one by moving actors using their exact original geometry and prototype. No fixed visible cars remain in the viewer or saved Blender scene. The [vehicle promotion regression](viewer/vehicle_promotion_validation.json) verifies source identities, absent fixed draw submissions and colliders, actual rendered transforms, and progress for every car. Source placements remain stored for editability, with the fixed copies hidden and excluded from static collision. The western lake, central park, housing and eastern skyline remain in place.

Traffic follows 254 directed lanes and 567 authored-road turns through 83 connected junctions. Cars follow other cars, wait for signal phases and reserved junctions, and accelerate again when space opens. Existing signal lenses display the simulation phase. Temporary stops at red lights and in queues are expected; permanently decorative cars are not. A stationary roadside camera records the same promoted source car [before](renders/vehicle-promotion/promoted-car-a.png) and [one second later](renders/vehicle-promotion/promoted-car-b.png). The route graph retains conservative curb clearances and excludes narrow streets and unsupported dead ends. It is an ambient traffic system; vehicles are not player-drivable.

Pedestrians use the skill's exact 49-bone CharacterBase, its fixed shirt and trousers, and original **Walk** and **Idle** clips. Colors vary per person, with shared full-detail geometry. Routes use sidewalks, park paths and the lakeside circuit. Ground height comes from actual surface triangles. Pedestrians stay within safe corridors rather than crossing live traffic uncontrolled.

The viewer runs continuously, including with a stationary camera. The editable [Blender city](Lake_City.blend) also contains a **20-second route preview at 30 FPS**, sampled from the real simulation at 10 Hz. Original Walk/Idle clips drive the independent rigs. This recorded timeline is a preview segment; the viewer supplies ongoing junction decisions and routing. [Saved-scene close views](renders/life_blender/) show the actual animation. Blender blends transition rotations slightly differently from Three.js. The character acceptance [foot audit](validation/city_life_foot_audit.json), recorded before vehicle promotion with the same character geometry and clips, found a maximum upward sole gap below 1 cm at its two sampled frames; one blended pose penetrated the path by 3.95 cm. There is no systematic floating transform.

Validation: the [traffic simulation audit](comparisons/traffic_simulation_report.json) covers 30 simulated minutes, with zero vehicle overlaps and zero off-route samples. It recorded 13,719 completed turns, 6,374 signal stops and 26,562 restarts. Frame-rate determinism passed. Every vehicle advanced in each 120-second interval across the full run; the minimum interval distance was 14.76 m and the longest temporary stop was 73.4 seconds. [Character validation](characters/character_final_audit.json), [runtime character transfer](viewer/public/assets/characters/pedestrian.json), [Blender animation integration](validation/city_life_blender.json) and the [fresh Blender reopen](blender_validation.json) record source integrity, real clips and saved-file animation. [Living-city desktop tests](viewer/life_validation.json) and [current runtime measurements](viewer/runtime_validation.json) cover actual rendered operation and its performance.

Character files: [canonical Blender](characters/CharacterBase.blend), [neutral FBX](characters/CharacterBase.fbx), [neutral GLB](characters/CharacterBase.glb), [runtime animated GLB](viewer/public/assets/characters/pedestrian.glb), [Idle](characters/anim/idle.fbx), [Walk](characters/anim/walk.fbx), [Run](characters/anim/run.fbx), [Jump](characters/anim/jump.fbx). Run and Jump are validated available exports; the city uses Walk and Idle. [Walk pose sheet](characters/qc_walk.png), [animation matrix validation](characters/CharacterBase_animation_validation.json), [animation QC](characters/CharacterBase_animation_qc.json), [export/reimport workflow](characters/reports/CharacterBase_export_workflow.json).

Animation identity: `8a1c542ce72a959bd638f354a14bfaa050c1579495bcb2800ea2362fc830341c`. Static city identity remains `317c413494035f83921d0d627a28744b85608b9c33aee65591fb7b0fffb9d7f5`. No geometry reduction, reduced render resolution or remote hosting was introduced.

### Character validation files

- Base and outfit: [base build](characters/CharacterBase_base_report.json), [final audit](characters/character_final_audit.json), [current outfit validation](characters/reports/CharacterBase_current_outfit_validation.json), [outfit views](characters/qc_outfit.png).
- Animation: [package](characters/animation_package_report.json), [installation](characters/CharacterBase_animation_install.json), [matrix validation](characters/CharacterBase_animation_validation.json), [workflow](characters/CharacterBase_animation_workflow.json), [QC](characters/CharacterBase_animation_qc.json).
- Pose sheets: [Idle](characters/qc_idle.png), [Walk](characters/qc_walk.png), [Run](characters/qc_run.png), [Jump](characters/qc_jump.png).
- Final exports: [workflow](characters/reports/CharacterBase_export_workflow.json), [export report](characters/reports/CharacterBase_export.json), [FBX reimport](characters/reports/CharacterBase_fbx_validation.json), [GLB reimport](characters/reports/CharacterBase_glb_validation.json).
- Animation reimports: [Idle](characters/reports/anim/idle_fbx_validation.json), [Walk](characters/reports/anim/walk_fbx_validation.json), [Run](characters/reports/anim/run_fbx_validation.json), [Jump](characters/reports/anim/jump_fbx_validation.json).
