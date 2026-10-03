"""Build editable linked Blender assemblies from the exact runtime buffers."""
import bpy,json,sys,math,os,time
from pathlib import Path
import numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
stage=int(args[0]) if args else 10
mode=args[1] if len(args)>1 else 'checkpoint'
data=json.loads((ROOT/'viewer/public/assets/city.json').read_text())
raw=(ROOT/'viewer/public/assets/geometry.bin').read_bytes()
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
for m in list(bpy.data.meshes):bpy.data.meshes.remove(m)
materials={}
def linear(c):return c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4
for name,desc in data['materials'].items():
 mat=bpy.data.materials.new(name);color=desc['color'].lstrip('#');rgb=[linear(int(color[i:i+2],16)/255) for i in [0,2,4]]
 mat.diffuse_color=(*rgb,1);mat.use_nodes=True;p=mat.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*rgb,1);p.inputs['Roughness'].default_value=desc['roughness'];p.inputs['Metallic'].default_value=desc['metalness']
 if 'glass' in name: p.inputs['Roughness'].default_value=.27;p.inputs['Metallic'].default_value=.28
 if any(v in name for v in ['grass','asphalt','stone','plaster','path','sidewalk','brick','concrete','water']):
  nodes=mat.node_tree.nodes;links=mat.node_tree.links;noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=2 if 'water' in name else 18;noise.inputs['Detail'].default_value=2
  coord=nodes.new('ShaderNodeTexCoord');links.new(coord.outputs['Object'],noise.inputs['Vector']);bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.16 if 'water' in name else .12;bump.inputs['Distance'].default_value=.012;links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],p.inputs['Normal'])
 materials[name]=mat
prototypes={}
for name,pr in data['prototypes'].items():
 vs=[];fs=[];mi=[];offset=0;matnames=[]
 for j,m in enumerate(pr['meshes']):
  positions=np.frombuffer(raw,dtype='<f4',count=m['positionCount'],offset=m['positionOffset']).reshape(-1,3).copy()
  positions=positions[:,[0,2,1]];positions[:,1]*=-1
  indices=np.frombuffer(raw,dtype='<u4',count=m['indexCount'],offset=m['indexOffset']).reshape(-1,3).astype(np.int64)+offset
  vs.extend(positions.tolist());fs.extend(indices.tolist());mi.extend([j]*len(indices));offset+=len(positions);matnames.append(m['material'])
 mesh=bpy.data.meshes.new(name+'_EditableMesh');mesh.from_pydata(vs,[],fs);mesh.update()
 for n in matnames:mesh.materials.append(materials[n])
 mesh.polygons.foreach_set('material_index',mi)
 prototypes[name]=mesh
collections={}
for i,inst in enumerate(data['instances']):
 region=inst['region']
 if region not in collections:
  coll=bpy.data.collections.new(region);bpy.context.scene.collection.children.link(coll);collections[region]=coll
 obj=bpy.data.objects.new(inst['id'],prototypes[inst['prototype']]);collections[region].objects.link(obj)
 x,y,z=inst['position'];obj.location=(x,-z,y);sx,sy,sz=inst['scale'];obj.scale=(sx,sz,sy);obj.rotation_euler=(0,0,inst['rotation']);obj['prototype_id']=inst['prototype'];obj['region_id']=region;obj['source_id']=inst['id']
 if i%5000==0:print('Imported',i,'instances',flush=True)
scene=bpy.context.scene
scene['source_hash']=data['sourceHash'];scene['reference_layout']='references/target_layout.png';scene['world_axes']='Blender X east, Y north, Z up. Runtime X east Y up Z south.'
world=bpy.data.worlds.new('Daylight Sky') if not scene.world else scene.world;scene.world=world;world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.52,.67,.86,1);world.node_tree.nodes['Background'].inputs[1].default_value=.55
sun_data=bpy.data.lights.new('Late Summer Sun','SUN');sun_data.energy=3.0;sun_data.angle=math.radians(8);sun=bpy.data.objects.new('Late Summer Sun',sun_data);scene.collection.objects.link(sun);sun.rotation_euler=(math.radians(27),math.radians(-22),math.radians(-28))
cams={}
def camera(name,pos,target,ortho=False):
 cd=bpy.data.cameras.new(name);ob=bpy.data.objects.new(name,cd);scene.collection.objects.link(ob);ob.location=(pos[0],-pos[2],pos[1]);tar=Vector((target[0],-target[2],target[1]));ob.rotation_euler=(tar-ob.location).to_track_quat('-Z','Y').to_euler();cd.clip_end=10000;cd.clip_start=10 if pos[1]>100 else .1
 if ortho:cd.type='ORTHO';cd.ortho_scale=2175;ob.rotation_euler=(0,0,0)
 else:cd.lens=36 if name=='overview' else 26
 cams[name]=ob;return ob
for c in data['cameras']:camera(c['id'],c['position'],c['target'],c['id']=='top')
scene.camera=cams['top'];scene.render.resolution_x=1450;scene.render.resolution_y=1088;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=0
scene.render.engine='BLENDER_EEVEE';scene.render.image_settings.color_mode='RGB'
if hasattr(scene,'eevee'):scene.eevee.taa_render_samples=32
# Preserve a pleasant default editor view without driving the desktop UI.
for area in bpy.context.screen.areas:
 if area.type=='VIEW_3D':area.spaces.active.region_3d.view_distance=1900;area.spaces.active.region_3d.view_location=(0,0,0)
path=ROOT/('Lake_City.blend' if stage>=10 else f'checkpoints/stage_{stage:02d}.blend')
bpy.ops.wm.save_as_mainfile(filepath=str(path),compress=False)
if mode=='checkpoint':
 scene.render.filepath=str(ROOT/f'renders/stage_{stage:02d}_top.png');bpy.ops.render.render(write_still=True)
elif mode.startswith('pass') or mode.startswith('revision_'):
 renderdir=ROOT/'renders'/mode;renderdir.mkdir(exist_ok=True)
 for name,cam in cams.items():
  if mode.startswith('revision_') and len(args)>2 and name not in args[2:]:continue
  scene.camera=cam;scene.render.resolution_x=1450 if name=='top' else 1100;scene.render.resolution_y=1088 if name=='top' else 760;scene.render.filepath=str(renderdir/f'{name}.png');bpy.ops.render.render(write_still=True)
print('BUILD_COMPLETE',path,flush=True)
