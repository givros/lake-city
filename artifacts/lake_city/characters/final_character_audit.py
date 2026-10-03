"""Summarize current, inspected character deliverables and canonical safeguards."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent
source=root/'CharacterBase.blend'
digest=hashlib.sha256(source.read_bytes()).hexdigest()
required=['animation_package_report.json','CharacterBase_animation_install.json',
 'CharacterBase_animation_validation.json','CharacterBase_animation_workflow.json',
 'CharacterBase_animation_qc.json','CharacterBase_animation_component_guard.json',
 'reports/CharacterBase_current_outfit_validation.json',
 'reports/CharacterBase_export.json','reports/CharacterBase_export_workflow.json',
 'reports/CharacterBase_fbx_validation.json','reports/CharacterBase_glb_validation.json',
 'reports/anim/idle_fbx_validation.json','reports/anim/walk_fbx_validation.json',
 'reports/anim/run_fbx_validation.json','reports/anim/jump_fbx_validation.json',
 'pedestrian_runtime.json']
checks=[]
for name in required:
    path=root/name;data=json.loads(path.read_text())
    assert data['passed'] is True,name
    checks.append({'report':name,'passed':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
validation=json.loads((root/'CharacterBase_animation_validation.json').read_text())
assert validation['bones']==49 and validation['saved_in_neutral_t_pose'] and validation['active_action'] is None
assert validation['basis_matrix_max_delta']<=1e-5
assert validation['evaluated_pose_matrix_max_delta']<=5e-5
assert validation['rest_matrix_max_delta']<=2e-5
base=json.loads((root/'CharacterBase_base_report.json').read_text())
expected=dict(vertices=1596,edges=3169,faces=1588,loops=6310,triangles=3134,uv_layers=1,vertex_groups=47,bones=49,constraints=7)
for key,value in expected.items():assert base['rebuilt_metrics'][key]==value,(key,value)
outfit=json.loads((root/'reports/CharacterBase_current_outfit_validation.json').read_text())
assert outfit['file_sha256'].lower()==digest
assert (outfit['pants_vertices'],outfit['pants_faces'],outfit['shirt_vertices'],outfit['shirt_faces'])==(261,224,358,320)
exports=json.loads((root/'reports/CharacterBase_export_workflow.json').read_text())
assert exports['source_blend_sha256_before']==exports['source_blend_sha256_after']==digest
assert exports['all_reimports_passed'] and len(exports['validation_reports'])==6
assert list(root.rglob('*.blend'))==[source]
qc_images=sorted((root/'CharacterBase_animation_qc').rglob('*.png'))+sorted((root/'CharacterBase_qc').glob('*.png'))
assert len(qc_images)==28
result={'passed':True,'canonical_source':str(source),'source_sha256':digest,
 'canonical_count':1,'source_metrics':expected,'qc_images_inspected':len(qc_images),
 'visual_findings':'All five poses for each of Idle, Walk, Run, Jump and all eight outfit views inspected. Limbs, torso, head and right foot remain articulated; shirt and pants retain the expected fixed form and waist layering. No severe mesh explosion, inverted head, detached garments or foot inversion visible.',
 'qc_images':[str(p.relative_to(root)) for p in qc_images],
 'runtime_glb':'../viewer/public/assets/characters/pedestrian.glb',
 'runtime_contract':'../viewer/public/assets/characters/pedestrian.json',
 'runtime_export_policy':'Uncompressed read-only derivative with original Walk and Idle sampled to start at time zero. No source action, geometry, material or rig edits.',
 'checks':checks}
(root/'character_final_audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('checks','qc_images')},indent=2))
