"""Lossless deterministic scene assembly shared by Blender and the desktop viewer."""
import json, math, hashlib, struct
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np
from shapely.geometry import Polygon, LineString
from shapely.ops import triangulate

ROOT=Path(__file__).resolve().parents[1]
SCALE=1.5
def world(u,v,y=0): return [(u-725)*SCALE,y,(v-544)*SCALE]
def box(w,h,d,x=0,y=0,z=0,material='stone',**kw):
    return dict(shape='box',size=[w,h,d],position=[x,y,z],material=material,**kw)
def catmull(points,steps=6,closed=False):
    p=np.asarray(points,float); out=[]; n=len(p)
    for i in range(n if closed else n-1):
        p0=p[(i-1)%n] if closed or i else p[0]; p1=p[i];p2=p[(i+1)%n];p3=p[(i+2)%n] if closed or i+2<n else p[-1]
        for t in np.linspace(0,1,steps,endpoint=False):
            out.append((.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t)).tolist())
    if not closed:out.append(p[-1].tolist())
    return out
def polygon_part(poly,y,mat):
    verts=[];faces=[]
    if poly.is_empty:return None
    polys=list(poly.geoms) if poly.geom_type=='MultiPolygon' else [poly]
    for pg in polys:
        for t in triangulate(pg):
            if not pg.covers(t.representative_point()):continue
            pts=list(t.exterior.coords)[:3]; start=len(verts)
            verts.extend([[x,y,z] for x,z in pts]);faces.append([start,start+2,start+1])
    return dict(shape='mesh',vertices=verts,faces=faces,material=mat)
class Scene:
    def __init__(self):
        self.materials={}; self.prototypes={}; self.instances=[];self.paths=[];self.waterPolygons=[];self.walkSurfaces=[];self.landmarks=[];self.cameras=[];self.surface_parts=defaultdict(list);self.parcels=[];self.buildings=[]
    def material(self,name,color,roughness=.8,metalness=0):
        self.materials[name]=dict(color=color,roughness=roughness,metalness=metalness)
    def prototype(self,name,parts,collision=None):
        self.prototypes[name]=dict(parts=parts,collision=collision)
    def add(self,prototype,position,rotation=0,scale=None,region='REG_PUBLIC',stage=1,id=None):
        obj=dict(id=id or f'{region}_{prototype}_{len(self.instances):05d}',prototype=prototype,position=position,rotation=rotation,scale=scale or [1,1,1],region=region,stage=stage)
        self.instances.append(obj);return obj
    def at(self,proto,u,v,y=0,**kw):return self.add(proto,world(u,v,y),**kw)
    def surface(self,poly,y,mat,stage,region='REG_PUBLIC'):
        part=polygon_part(poly,y,mat)
        if part and part['faces']:self.surface_parts[(stage,region)].append(part)
    def rect(self,u,v,w,d,mat,stage,y=.02,region='REG_PUBLIC'):
        a=world(u-w/2,v-d/2);b=world(u+w/2,v+d/2)
        self.surface(Polygon([(a[0],a[2]),(b[0],a[2]),(b[0],b[2]),(a[0],b[2])]),y,mat,stage,region)
    def path(self,name,points,width,mat,stage=9,closed=False,y=.07,smooth=False,region='REG_PUBLIC'):
        ps=catmull(points,8,closed) if smooth else points
        pts=[[world(u,v)[0],world(u,v)[2]] for u,v in ps]
        if closed:pts.append(pts[0])
        line=LineString(pts)
        self.surface(line.buffer(width/2,join_style=1,cap_style=1),y,mat,stage,region)
        self.paths.append(dict(id=name,points=pts,width=width,closed=closed,stage=stage))
        return line
    def flush(self):
        for (stage,region),parts in self.surface_parts.items():
            name=f'surfaces_{stage}_{region}';self.prototype(name,parts);self.add(name,[0,0,0],region=region,stage=stage)
        self.surface_parts.clear()

def _rotation(r):
    x,y,z=r;cx,sx=math.cos(x),math.sin(x);cy,sy=math.cos(y),math.sin(y);cz,sz=math.cos(z),math.sin(z)
    return np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
def primitive(part):
    shape=part['shape'];v=[];f=[]
    if shape=='box':
        w,h,d=np.array(part['size'])/2
        v=[[-w,-h,-d],[w,-h,-d],[w,h,-d],[-w,h,-d],[-w,-h,d],[w,-h,d],[w,h,d],[-w,h,d]]
        for a,b,c,d0 in [(0,3,2,1),(4,5,6,7),(0,4,7,3),(1,2,6,5),(3,7,6,2),(0,1,5,4)]:f.extend([[a,b,c],[a,c,d0]])
    elif shape=='cylinder':
        n=part.get('segments',12);r=part['radius'];rt=part.get('radiusTop',r);h=part['height']/2
        for yy,rr in [(-h,r),(h,rt)]:v.extend([[math.cos(a*2*math.pi/n)*rr,yy,math.sin(a*2*math.pi/n)*rr] for a in range(n)])
        v.extend([[0,-h,0],[0,h,0]])
        for i in range(n):
            j=(i+1)%n;f.extend([[i,n+i,n+j],[i,n+j,j],[2*n,i,j],[2*n+1,n+j,n+i]])
    elif shape=='sphere':
        n=part.get('segments',10);rings=part.get('rings',6);r=part['radius']
        for j in range(rings+1):
            ph=math.pi*j/rings
            v.extend([[r*math.sin(ph)*math.cos(i*2*math.pi/n),r*math.cos(ph),r*math.sin(ph)*math.sin(i*2*math.pi/n)] for i in range(n)])
        for j in range(rings):
            for i in range(n):
                a=j*n+i;b=j*n+(i+1)%n;c=(j+1)*n+(i+1)%n;d=(j+1)*n+i
                if j:f.append([a,b,c])
                if j<rings-1:f.append([a,c,d])
    elif shape=='mesh':
        v=part['vertices'];f=part['faces']
    else:raise ValueError(shape)
    v=np.asarray(v,dtype=float);v*=np.asarray(part.get('scale',[1,1,1]));v=v@_rotation(part.get('rotation',[0,0,0])).T+part.get('position',[0,0,0])
    tris=[]
    for face in f:
        for i in range(1,len(face)-1):tris.append([face[0],face[i],face[i+1]])
    p=v[np.asarray(tris)].reshape(-1,3);t=p.reshape(-1,3,3);nr=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);length=np.linalg.norm(nr,axis=1);valid=length>1e-9
    p=t[valid].reshape(-1,3);nr=nr[valid]/length[valid,None];normals=np.repeat(nr,3,axis=0)
    return p.astype('<f4'),normals.astype('<f4')

def export(scene,stage=10):
    scene.flush(); used={i['prototype'] for i in scene.instances if i['stage']<=stage}; buf=bytearray(); protos={};unique=0
    for name in sorted(used):
        pr=scene.prototypes[name];grouped=defaultdict(list)
        for part in pr['parts']:grouped[part['material']].append(part)
        meshes=[]
        for mat,parts in grouped.items():
            arrays=[primitive(p) for p in parts];positions=np.concatenate([a[0] for a in arrays]);normals=np.concatenate([a[1] for a in arrays]);indices=np.arange(len(positions),dtype='<u4')
            assert np.isfinite(positions).all() and np.isfinite(normals).all()
            assert mat in scene.materials,f'Unknown material {mat}'
            po=len(buf);buf.extend(positions.tobytes());no=len(buf);buf.extend(normals.tobytes());io=len(buf);buf.extend(indices.tobytes())
            meshes.append(dict(material=mat,positionOffset=po,positionCount=positions.size,normalOffset=no,indexOffset=io,indexCount=len(indices)));unique+=len(indices)//3
        protos[name]=dict(meshes=meshes,collision=pr['collision'])
    instances=[i for i in scene.instances if i['stage']<=stage]
    triangles=sum(sum(m['indexCount']//3 for m in protos[i['prototype']]['meshes']) for i in instances)
    data=dict(materials=scene.materials,prototypes=protos,instances=instances,bounds=dict(min=[-1087.5,-816],max=[1087.5,816]),waterPolygons=scene.waterPolygons,paths=scene.paths,walkSurfaces=scene.walkSurfaces,landmarks=scene.landmarks,cameras=scene.cameras,stats=dict(instances=len(instances),prototypes=len(protos),uniqueTriangles=unique,visibleTriangles=triangles,stage=stage),sourceHash='')
    data['waterHolePolygons']=getattr(scene,'waterHolePolygons',[])
    signature=hashlib.sha256(buf+json.dumps(data,sort_keys=True).encode()).hexdigest();data['sourceHash']=signature
    path=ROOT/'viewer/public/assets';path.mkdir(parents=True,exist_ok=True);(path/'geometry.bin').write_bytes(buf);(path/'city.json').write_text(json.dumps(data,separators=(',',':')),encoding='utf8')
    (ROOT/'source_scene.json').write_text(json.dumps(dict(materials=scene.materials,prototypes={k:scene.prototypes[k] for k in used},instances=instances),separators=(',',':')),encoding='utf8')
    (ROOT/'asset_registry.json').write_text(json.dumps(dict(sourceHash=signature,provenance='Original procedural geometry authored for this city; user supplied layout reference.',counts=Counter(i['prototype'] for i in instances),editable_components={k:[p.get('name',p['shape']) for p in scene.prototypes[k]['parts']] for k in used}),indent=2),encoding='utf8')
    print(json.dumps(data['stats'])+f' | binary {len(buf)/1e6:.2f} MB | '+signature[:12],flush=True)
    return data
