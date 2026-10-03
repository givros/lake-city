## Movement stability and tree grounding

This revision addresses the reported flickering/disappearing building walls and exposed, floating tree roots. The district layout, water outline, routes, building placements and all tree horizontal positions are preserved.

### Causes and corrections

**Disappearing facades.** Water reflections and sun shadows recursively rendered the same BatchedMesh objects while another camera's draw commands were still being prepared. Those nested passes changed the shared indirect instance-ID texture and draw ranges. The baseline audit captured wrong-camera draws and 100 recorded instance-ID overwrite events, including architectural materials. A matched-pose image differed from a diagnostic render containing all source geometry by 330,462 pixels; 305,933 pixels differed by more than 5/255 in at least one color channel.

The viewer now submits the sun-shadow update, the full-resolution reflection captures and the main view in explicit sequence. Each pass finishes command preparation and submission before another pass changes its visibility data. Per-object culling remains enabled for normal exploration. Geometry, native resolution, reflection resolution and shadow resolution are retained.

**Localized facade shimmer.** Window reveal surfaces touched their masonry opening faces at exactly the same depth, and tower corner casings shared a plane with terminal mullions. The source now separates those surfaces by 15 mm. The 1,600 reveal assemblies and 312 corner strips retain their part counts, triangle counts and collision bounds. [Source audit](../comparisons/source_surface_audit.json) and [targeted correction audit](../comparisons/source_surface_fix_validation.json) document the checks.

**Tree soil contact.** Tree placements used one fixed Y datum even though the visible ground includes several elevations. Some bases stood up to 28 cm above forest soil, while their modeled root flares rose approximately 76 cm above the prototype origin. Tree trunks now extend below ground, structural roots are buried, and the instance height is sampled from the actual rendered support triangles with a 6 cm embed. The compact collar replaces the exposed root cones. All canopy and branch geometry is retained.

All **9,391 trees** have supporting ground. Their structural roots finish at least **2.36 cm below soil**; trunk bases extend 0.528–1.074 m below it. A direct comparison with the previous exported placements found zero changes to tree X/Z coordinates, rotation, scale, IDs or prototype assignment. Grounding runs before local clearance and again after relocation. [Grounding measurements](../tree_grounding_validation.json), [prototype and winding checks](../validation/tree_anchoring_report.json), and [matched Blender views](../comparisons/tree_grounding_before_after.png) provide evidence.

### Verification

- The source geometry and spatial audit has no failures. The two pre-existing composition warnings remain unchanged.
- The updated Blender scene was saved, reopened in a fresh process and rendered. Current source views are in [revision_01](../renders/revision_01/); the final top-down reference comparison was refreshed and inspected.
- The moving-camera stability run covers **48 camera positions** across downtown, lakeside, park and residential routes, including shadow-region changes. The audit covered 33,842 batch draws with zero camera or indirect-ID state mismatches. All 16 culling-versus-full-source image pairs and all 48 identical-pose repeat pairs have zero changed pixels. [Stability results](../viewer/stability_validation.json) record the final counts, matched-pose comparisons and repeated-frame results.
- [Runtime validation](../viewer/runtime_validation.json) contains final-source geometry transfer, keyboard/mouse traversal, collision, reflection-plane, lifecycle, production-build and performance results. [Render profile](../viewer/render_profile.json) records the sequential pass ownership.

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
