"""Read canonical character metadata without saving the source."""
import bpy, json
from pathlib import Path
import sys
sys.path.insert(0, 'C:/Users/limou/.codex/skills/blender-lowpoly-character/scripts/export')
from export_character_assets import choose_action_slot
rig=bpy.data.objects['CharacterRig']
ad=rig.animation_data_create()
result={'rig_transform': [list(r) for r in rig.matrix_world], 'root_bones': [b.name for b in rig.data.bones if not b.parent], 'actions': {}, 'meshes': {}}
for ob in [x for x in bpy.data.objects if x.type=='MESH' and x.name in ['CharacterBase','Pants','LongSleeveShirt']]:
    pts=[ob.matrix_world@v.co for v in ob.data.vertices]
    result['meshes'][ob.name]={'min':[min(p[k] for p in pts) for k in range(3)],'max':[max(p[k] for p in pts) for k in range(3)],'modifiers':[(m.name,m.type) for m in ob.modifiers]}
for a in bpy.data.actions:
    if not a.get('codex_basic_animation'): continue
    ad.action=a; ad.action_slot=choose_action_slot(a,rig)
    samples=[]
    for f in (int(a.frame_range[0]), int((a.frame_range[0]+a.frame_range[1])/2), int(a.frame_range[1])):
        bpy.context.scene.frame_set(f)
        samples.append({'frame':f,'root_bones':{b.name:{'location':list(b.location),'world':list((rig.matrix_world@b.matrix).translation)} for b in rig.pose.bones if not b.parent}})
    result['actions'][a.name]={'range':list(a.frame_range),'samples':samples}
Path('E:/Dev/lake-city/artifacts/lake_city/characters/runtime_source_inspection.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
