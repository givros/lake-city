"""Deterministic, metre-scale modern city architecture.

Geometry parts are the shared source of Blender and runtime meshes. Every public
prototype has Y-up coordinates, its base at Y=0, and its main frontage toward +Z.
All buildings are deliberately non-enterable. Public pavement is layout-owned.
"""
import json
import math
from pathlib import Path


PALETTE = {
    'arch_limestone': ('#cfcabe', .82, 0),
    'arch_stone_light': ('#dedbd1', .82, 0),
    'arch_plaster': ('#e0dcd0', .85, 0),
    'arch_plaster_warm': ('#c8b49c', .87, 0),
    'arch_plaster_sage': ('#a4ac9b', .88, 0),
    'arch_brick_red': ('#946858', .9, 0),
    'arch_brick_buff': ('#b39c7a', .9, 0),
    'arch_brick_dark': ('#746963', .91, 0),
    'arch_siding': ('#bac1be', .84, 0),
    'arch_concrete': ('#a2a39c', .88, 0),
    'arch_foundation': ('#757976', .91, 0),
    'arch_glass': ('#386071', .2, .3),
    'arch_glass_light': ('#71929a', .19, .28),
    'arch_glass_dark': ('#233f4b', .21, .25),
    'arch_frame': ('#c5c6bc', .36, .45),
    'arch_frame_dark': ('#3e4b4e', .39, .55),
    'arch_roof_slate': ('#505961', .81, .08),
    'arch_roof_red': ('#986c54', .87, 0),
    'arch_roof_dark': ('#464e52', .82, 0),
    'arch_roof_membrane': ('#8b918c', .93, 0),
    'arch_copper': ('#66817d', .56, .48),
    'arch_wood': ('#80664e', .83, 0),
    'arch_metal': ('#78858a', .41, .65),
    'arch_black': ('#303b3c', .77, .08),
    'arch_white': ('#e5e3d8', .72, 0),
    'arch_awning_green': ('#62776f', .84, 0),
    'arch_awning_red': ('#a26c58', .83, 0),
    'arch_awning_navy': ('#3d596a', .82, 0),
    'arch_solar': ('#263e55', .25, .4),
}


def box(parts, name, size, pos, mat, rot=None):
    p = {'shape': 'box', 'name': name, 'size': list(size),
         'position': list(pos), 'material': mat}
    if rot:
        p['rotation'] = list(rot)
    parts.append(p)


def cyl(parts, name, radius, height, pos, mat, rot=None, segments=12):
    p = {'shape': 'cylinder', 'name': name, 'radius': radius,
         'height': height, 'segments': segments, 'position': list(pos), 'material': mat}
    if rot:
        p['rotation'] = list(rot)
    parts.append(p)


def mesh(parts, name, verts, faces, mat):
    parts.append({'shape': 'mesh', 'name': name, 'vertices': verts,
                  'faces': faces, 'material': mat})


def frame_point(face, u, y, v):
    ox, oz, tx, tz, nx, nz = face
    return [ox + tx*u + nx*v, y, oz + tz*u + nz*v]


def face_box(parts, name, face, u, y, v, w, h, dep, mat):
    rot = math.atan2(-face[3], face[2])
    box(parts, name, (w, h, dep), frame_point(face, u, y, v), mat, (0, rot, 0))


def faces_for(w, d, cx=0, cz=0):
    # Origin, tangent, outward normal in the XZ plane.
    return [('front', w, (cx, cz+d/2, 1, 0, 0, 1)),
            ('right', d, (cx+w/2, cz, 0, -1, 1, 0)),
            ('rear', w, (cx, cz-d/2, -1, 0, 0, -1)),
            ('left', d, (cx-w/2, cz, 0, 1, -1, 0))]


def aperture(parts, name, face, u, y, w, h, mat='arch_frame', mullion=True,
             glass='arch_glass', door=False):
    """Hollow framed reveal and inset glazing, never a painted wall rectangle."""
    t = .085 if not door else .12
    outer = [(-w/2-t, -h/2-t), (w/2+t, -h/2-t),
             (w/2+t, h/2+t), (-w/2-t, h/2+t)]
    # Line the masonry opening with a real 15 mm reveal thickness. Matching the
    # opening exactly leaves two differently coloured faces on the same plane.
    reveal = .015
    inner = [(-w/2+reveal, -h/2+reveal), (w/2-reveal, -h/2+reveal),
             (w/2-reveal, h/2-reveal), (-w/2+reveal, h/2-reveal)]
    verts = [frame_point(face, u+x, y+z, .06) for x,z in outer]
    verts += [frame_point(face, u+x, y+z, .06) for x,z in inner]
    verts += [frame_point(face, u+x, y+z, -.19) for x,z in inner]
    tris = []
    for k in range(4):
        j = (k+1)%4
        tris.extend([[k,j,4+j], [k,4+j,4+k], [4+k,4+j,8+j], [4+k,8+j,8+k]])
    mesh(parts, name+'/frame-and-reveal', verts, tris, mat)
    v = [frame_point(face,u-w/2,y-h/2,-.2), frame_point(face,u+w/2,y-h/2,-.2),
         frame_point(face,u+w/2,y+h/2,-.2), frame_point(face,u-w/2,y+h/2,-.2)]
    mesh(parts,name+'/inset-glazing',v,[[0,1,2],[0,2,3]],glass)
    if mullion:
        face_box(parts,name+'/mullion',face,u,y,-.12,.065,h,.08,mat)
    if not door:
        face_box(parts,name+'/sill',face,u,y-h/2-.08,.07,w+.27,.14,.32,'arch_stone_light')
    else:
        face_box(parts,name+'/threshold',face,u,y-h/2-.035,.04,w+.2,.07,.32,'arch_foundation')
        face_box(parts,name+'/door-rail',face,u,y-.25,-.11,w,.06,.08,mat)
        face_box(parts,name+'/pull',face,u+.23,y-.17,.07,.055,.5,.095,'arch_metal')


def masonry_volume(parts, prefix, w, d, floors, storey, mat,
                   base=.32, bay=3.8, side_windows=True, cx=0, cz=0,
                   floor_bands=True, balconies=False, entry=True, win_ratio=.52):
    h = floors*storey
    box(parts,prefix+'/foundation',(w+.26,.32,d+.26),(cx,.16,cz),'arch_foundation')
    for k in range(floors+1):
        yy = base+k*storey
        # Keep the structural slab inside the wall thickness; a coplanar full-size
        # slab would create dark fighting strips at every facade floor datum.
        box(parts,prefix+f'/floor-{k}/slab',(w-.58,.15,d-.58),(cx,yy,cz),'arch_concrete')
    for side, span, face in faces_for(w,d,cx,cz):
        # Front/rear walls own the corners. Side walls meet their inner faces,
        # avoiding duplicate coplanar end caps in the visible corner masonry.
        if side in ('left','right'):
            span -= .56
        if not side_windows and side in ('left','right'):
            face_box(parts,prefix+'/'+side+'/party-wall',face,0,base+h/2,-.14,span,h,.28,mat)
            continue
        n = max(2, int((span-.9)/bay))
        step = (span-.9)/n
        ww = min(step-.65, step*win_ratio)
        centers = [-span/2+.45+step*(i+.5) for i in range(n)]
        for floor in range(floors):
            yy = base+floor*storey
            wh = min(1.8,storey-.95)
            sill = .78 if floors <= 2 else .72
            for k,u in enumerate(centers):
                isdoor = entry and side=='front' and floor==0 and k==n//2
                opw = min(1.45,ww) if isdoor else ww
                oph = 2.36 if isdoor else wh
                bot = yy+.04 if isdoor else yy+sill
                top = bot+oph
                left = -span/2 if k==0 else (centers[k-1]+u)/2
                right = span/2 if k==n-1 else (u+centers[k+1])/2
                # Each bay owns its complete piers and the two wall bands.
                for tag, lo, hi in [('left-pier',left,u-opw/2), ('right-pier',u+opw/2,right)]:
                    if hi-lo > .001:
                        face_box(parts,f'{prefix}/{side}/{floor}/{k}/{tag}',face,(lo+hi)/2,yy+storey/2,-.14,hi-lo,storey,.28,mat)
                if bot>yy:
                    face_box(parts,f'{prefix}/{side}/{floor}/{k}/spandrel',face,u,(bot+yy)/2,-.14,opw,bot-yy,.28,mat)
                if yy+storey>top:
                    face_box(parts,f'{prefix}/{side}/{floor}/{k}/lintel',face,u,(yy+storey+top)/2,-.14,opw,yy+storey-top,.28,mat)
                aperture(parts,f'{prefix}/{side}/{floor}/{k}',face,u,bot+oph/2,opw,oph,
                         'arch_frame_dark' if floors>2 else 'arch_frame',
                         mullion=(floor+k)%2==0 or isdoor,door=isdoor)
                if balconies and floor>0 and side in ('front','rear') and k%3==1:
                    face_box(parts,f'{prefix}/{side}/{floor}/{k}/balcony-slab',face,u,yy+.02,.66,ww+.55,.17,1.5,'arch_concrete')
                    face_box(parts,f'{prefix}/{side}/{floor}/{k}/balcony-rail',face,u,yy+.85,1.39,ww+.5,.065,.065,'arch_frame_dark')
                    for j in range(6):
                        face_box(parts,f'{prefix}/{side}/{floor}/{k}/baluster-{j}',face,u-(ww+.38)/2+j*(ww+.38)/5,yy+.43,1.39,.04,.82,.05,'arch_frame_dark')
                    for sg in (-1,1):
                        face_box(parts,f'{prefix}/{side}/{floor}/{k}/balcony-return-{sg}',face,u+sg*(ww+.45)/2,yy+.85,.72,.05,.065,1.33,'arch_frame_dark')
    if floor_bands:
        for floor in range(floors):
            box(parts,f'{prefix}/{floor}/continuous-belt-course',(w+.18,.14,d+.18),
                (cx,base+(floor+1)*storey-.04,cz),'arch_stone_light')
    return base+h


def parapet(parts, prefix, w, d, roof_y, mat='arch_limestone', cx=0, cz=0, height=.8):
    box(parts,prefix+'/roof',(w-.5,.2,d-.5),(cx,roof_y,cz),'arch_roof_membrane')
    for side,span,face in faces_for(w,d,cx,cz):
        if side in ('left','right'):
            span -= .5
        face_box(parts,prefix+'/'+side+'/parapet',face,0,roof_y+height/2,-.10,span,height,.25,mat)
        face_box(parts,prefix+'/'+side+'/coping',face,0,roof_y+height,-.07,span+.08,.1,.36,'arch_stone_light')


def pitched_roof(parts,prefix,w,d,eave,rise,mat,cx=0,cz=0):
    over=.48
    half=w/2+over
    a=math.atan2(rise,half)
    slope=math.hypot(half,rise)
    for sign in (-1,1):
        box(parts,prefix+f'/slope-{sign}',(slope,.22,d+over*2),(cx+sign*half/2,eave+rise/2,cz),mat,(0,0,-sign*a))
    # Real gables close both ends beneath the pitched roof.
    for sign in (-1,1):
        z=cz+sign*d/2
        vs=[[cx-w/2,eave,z],[cx+w/2,eave,z],[cx,eave+rise,z]]
        mesh(parts,prefix+f'/gable-{sign}',vs,[[0,1,2] if sign>0 else [2,1,0]],'arch_plaster')
    box(parts,prefix+'/ridge-cap',(.22,.2,d+1.08),(cx,eave+rise+.05,cz),mat)
    for sign in (-1,1):
        box(parts,prefix+f'/gutter-{sign}',(.15,.16,d+1.02),(cx+sign*(w/2+.5),eave-.02,cz),'arch_metal')
        box(parts,prefix+f'/downpipe-{sign}',(.10,eave-.12,.11),(cx+sign*(w/2+.16),eave/2,cz+d/2-.23),'arch_metal')
    # Restrained roof seams make the slopes readable at pedestrian and aerial scale.
    count=max(5,int(d/.95))
    for i in range(count):
        z=cz-d/2+i*d/(count-1)
        for sign in (-1,1):
            box(parts,prefix+f'/seam-{i}-{sign}',(slope,.035,.028),(cx+sign*half/2,eave+rise/2+.13, z),'arch_roof_dark',(0,0,-sign*a))
    # The chimney intersects the roof surface, with a visible outlet and flashing.
    xx=cx-w*.25
    zz=cz-d*.22
    ry=eave+rise*.5
    box(parts,prefix+'/chimney',(.62,2.05,.75),(xx,ry+.62,zz),'arch_brick_dark')
    box(parts,prefix+'/chimney-cap',(.84,.18,.96),(xx,ry+1.735,zz),'arch_concrete')
    cyl(parts,prefix+'/flue',.14,.32,(xx,ry+1.98,zz),'arch_black',segments=8)


def rooftop_services(parts,prefix,w,d,y,cx=0,cz=0,solar=False):
    box(parts,prefix+'/plant-base',(w*.25,.18,d*.22),(cx-w*.19,y+.18,cz-d*.15),'arch_foundation')
    box(parts,prefix+'/hvac',(w*.22,.8,d*.18),(cx-w*.19,y+.66,cz-d*.15),'arch_metal')
    for j in (-1,1):
        cyl(parts,prefix+f'/hvac-fan-{j}',min(w*.045,.8),.1,(cx-w*.19+j*w*.06,y+1.12,cz-d*.15),'arch_black')
    box(parts,prefix+'/lift-overrun',(w*.16,1.6,d*.18),(cx+w*.25,y+.88,cz-d*.16),'arch_concrete')
    for j in range(3):
        cyl(parts,prefix+f'/vent-{j}',.14,.7,(cx+w*.08+j*.7,y+.45,cz+d*.2),'arch_metal',segments=8)
    if solar:
        for i in range(3):
            box(parts,prefix+f'/solar-{i}',(w*.16,.1,d*.2),(cx-w*.3+i*w*.22,y+.52,cz+d*.2),'arch_solar',(0.2,0,0))


def porch(parts,prefix,w,d,door_x=0,modern=False):
    zz=d/2
    box(parts,prefix+'/landing',(2.5,.16,1.4),(door_x,.14,zz+.69),'arch_concrete')
    box(parts,prefix+'/canopy',(3.0,.15,1.65),(door_x,2.97,zz+.7),'arch_frame_dark' if modern else 'arch_roof_slate')
    for sign in (-1,1):
        box(parts,prefix+f'/column-{sign}',(.12,2.8,.12),(door_x+sign*1.25,1.53,zz+1.36),'arch_wood' if not modern else 'arch_frame_dark')
    face=faces_for(w,d)[0][2]
    face_box(parts,prefix+'/porch-light',face,door_x+1.1,2.05,.16,.19,.28,.15,'arch_metal')


def curtain_volume(parts,prefix,w,d,base,height,glass='arch_glass',accent='arch_limestone',cx=0,cz=0,bay=3.7,storey=3.8):
    """Inset curtain-wall surfaces behind continuous floor bands and mullions."""
    for side,span,face in faces_for(w,d,cx,cz):
        face_box(parts,prefix+'/'+side+'/recessed-glazing',face,0,base+height/2,-.19,span-.25,height,.07,glass)
        n=max(3,round(span/bay))
        for j in range(n+1):
            u=-span/2+j*span/n
            face_box(parts,prefix+'/'+side+f'/mullion-{j}',face,u,base+height/2,.045,.17,height,.27,'arch_frame_dark')
        fs=max(1,round(height/storey))
        for j in range(fs+1):
            yy=base+j*height/fs
            face_box(parts,prefix+'/'+side+f'/floor-band-{j}',face,0,yy,.075,span+.1,.29,.34,accent)
        # Broad structural corner columns lend scale without painting a whole box.
        for sign in (-1,1):
            # Project the corner casing beyond the terminal mullion by 15 mm;
            # the previous coincident exterior planes caused vertical shimmer.
            face_box(parts,prefix+'/'+side+f'/corner-column-{sign}',face,sign*(span/2-.15),base+height/2,.040,.32,height,.31,accent)
    box(parts,prefix+'/roof-deck',(w,.18,d),(cx,base+height,cz),'arch_roof_membrane')
    return base+height


def retail_base(parts,prefix,w,d,height=4.8,mat='arch_limestone'):
    box(parts,prefix+'/plinth',(w+.3,.3,d+.3),(0,.15,0),'arch_foundation')
    for side,span,face in faces_for(w,d):
        n=max(3,int(span/4.4))
        step=span/n
        for j in range(n):
            u=-span/2+(j+.5)*step
            face_box(parts,prefix+'/'+side+f'/shopfront-{j}',face,u,height*.47,-.2,step-.35,height*.79,.08,'arch_glass_dark')
            face_box(parts,prefix+'/'+side+f'/pier-{j}',face,u-step/2+.13,height/2,0,.27,height,.45,mat)
            face_box(parts,prefix+'/'+side+f'/shop-mullion-{j}',face,u,height*.45,.045,.08,height*.77,.15,'arch_frame_dark')
            face_box(parts,prefix+'/'+side+f'/shop-transom-{j}',face,u,height*.72,.045,step-.35,.08,.15,'arch_frame_dark')
        face_box(parts,prefix+'/'+side+'/lintel',face,0,height-.27,.02,span,.55,.45,mat)
        face_box(parts,prefix+'/'+side+'/cornice',face,0,height+.08,.05,span+.4,.23,.6,'arch_stone_light')
    for j in (-1,0,1):
        x=j*w*.25
        box(parts,prefix+f'/front-awning-{j}',(w*.2,.11,1.8),(x,3.12,d/2+.72),'arch_awning_navy')
    box(parts,prefix+'/entrance-frame',(2.9,.18,.5),(0,2.8,d/2+.14),'arch_frame')
    return height+.18


def measure(parts):
    mins=[float('inf')]*3
    maxs=[float('-inf')]*3
    for p in parts:
        if p['shape']=='mesh':
            points=p['vertices']
        else:
            pos=p.get('position',[0,0,0])
            if p['shape']=='box':
                dx,dy,dz=[v/2 for v in p['size']]
            elif p['shape']=='cylinder':
                dx=dz=max(p['radius'],p.get('radiusTop',p['radius']))
                dy=p['height']/2
            else:
                dx=dy=dz=p['radius']
            rx,ry,rz=p.get('rotation',[0,0,0])
            points=[]
            for x in (-dx,dx):
                for y in (-dy,dy):
                    for z in (-dz,dz):
                        yy=y*math.cos(rx)-z*math.sin(rx); zz=y*math.sin(rx)+z*math.cos(rx)
                        xx=x*math.cos(ry)+zz*math.sin(ry); zz=-x*math.sin(ry)+zz*math.cos(ry)
                        x2=xx*math.cos(rz)-yy*math.sin(rz); y2=xx*math.sin(rz)+yy*math.cos(rz)
                        points.append([pos[0]+x2,pos[1]+y2,pos[2]+zz])
        for point in points:
            for k in range(3):
                mins[k]=min(mins[k],point[k]);maxs[k]=max(maxs[k],point[k])
    return {'min':[round(v,3) for v in mins], 'max':[round(v,3) for v in maxs],
            'size':[round(maxs[k]-mins[k],3) for k in range(3)]}


def build_architecture(scene):
    catalog={}
    for name,(col,rough,metal) in PALETTE.items():
        scene.material(name,col,roughness=rough,metalness=metal)
    def register(name,parts,family,w,d,storeys,notes):
        bounds=measure(parts)
        hx=max(abs(bounds['min'][0]),abs(bounds['max'][0]))
        hz=max(abs(bounds['min'][2]),abs(bounds['max'][2]))
        scene.prototype(name,parts,collision=[hx,hz])
        tris=sum(12 if p['shape']=='box' else p.get('segments',12)*4 if p['shape']=='cylinder' else len(p.get('faces',[])) for p in parts)
        catalog[name]={'family':family,'footprint_m':[w,d],'bounds_m':bounds,
                       'collision_half_extents_m':[round(hx,3),round(hz,3)],
                       'storeys':storeys,'primary_frontage':'+Z','enterable':False,
                       'components':len(parts),'source_triangles_estimate':tris,
                       'notes':notes}

    # Quiet lake districts: correlated footprint, material and roof variations.
    house_specs=[(10.4,12.0,3.05,2.15,'arch_plaster','arch_roof_slate'),
                 (11.6,13.4,3.0,2.5,'arch_brick_red','arch_roof_slate'),
                 (12.8,11.5,3.0,2.15,'arch_siding','arch_roof_red'),
                 (13.6,13.4,3.1,0,'arch_plaster','arch_roof_dark'),
                 (10.8,14.3,3.05,2.6,'arch_brick_buff','arch_roof_dark'),
                 (12.0,13.0,3.0,2.3,'arch_plaster_sage','arch_roof_slate'),
                 (14.4,12.6,3.1,0,'arch_plaster_warm','arch_roof_dark'),
                 (11.8,14.7,3.0,2.65,'arch_brick_red','arch_roof_red'),
                 (13.2,12.2,3.0,2.3,'arch_plaster','arch_roof_slate'),
                 (10.8,13.6,3.1,2.3,'arch_siding','arch_roof_dark'),
                 (14.2,13.6,3.0,2.45,'arch_brick_buff','arch_roof_red'),
                 (12.4,14.2,3.05,0,'arch_plaster_sage','arch_roof_dark')]
    for i,(w,d,storey,rise,wall,roof) in enumerate(house_specs,1):
        p=[];name=f'house_{i:02}'
        top=masonry_volume(p,name,w,d,2,storey,wall,bay=3.8,floor_bands=i%3==0)
        n=max(2,int((w-.9)/3.8));step=(w-.9)/n;door=-w/2+.45+step*(n//2+.5)
        porch(p,name+'/porch',w,d,door,modern=not rise)
        if rise:
            pitched_roof(p,name+'/roof',w,d,top,rise,roof)
        else:
            parapet(p,name+'/roof',w,d,top,wall,height=.55)
            # An offset rooftop volume and shaded pergola vary the flat-roof silhouettes.
            box(p,name+'/roof-stair',(w*.3,1.25,d*.35),(w*.18,top+.69,-d*.2),wall)
            for j in range(5):
                box(p,name+f'/pergola-{j}',(.12,.13,d*.34),(-w*.34+j*w*.09,top+.72,d*.19),'arch_wood')
            for xx in (-w*.34,w*.02):
                for zz in (d*.035,d*.345):
                    box(p,name+f'/roof-screen-support-{xx:.2f}-{zz:.2f}',(.11,.61,.11),
                        (xx,top+.35,zz),'arch_wood')
            for zz in (d*.035,d*.345):
                box(p,name+f'/roof-screen-beam-{zz:.2f}',(w*.38,.11,.12),
                    (-w*.16,top+.60,zz),'arch_wood')
            rooftop_services(p,name+'/services',w*.6,d*.6,top,-w*.12,-d*.1,solar=True)
        # Distinct small bay projections, with glazing and a grounded base.
        if i in (2,5,8,11):
            bx=-w*.3
            box(p,name+'/bay/base',(2.5,.55,.72),(bx,.6,d/2+.31),wall)
            box(p,name+'/bay/glazing',(2.2,1.65,.62),(bx,1.7,d/2+.35),'arch_glass')
            box(p,name+'/bay/top',(2.58,.17,.86),(bx,2.61,d/2+.36),roof)
            for sg in (-1,1):
                box(p,name+f'/bay/frame-{sg}',(.12,1.78,.71),(bx+sg*1.12,1.71,d/2+.35),'arch_frame')
        register(name,p,'detached_house',w,d,2,'Panelized openings; inset framed glass; closed front door; complete roof and gutters.')

    for i,(w,d,floors,mat) in enumerate([(8.4,14,3,'arch_brick_red'),(9.6,15.2,3,'arch_brick_buff'),(10.2,14.6,3,'arch_plaster'),(9,16,3,'arch_brick_dark')],1):
        p=[];name=f'townhouse_{i:02}'
        top=masonry_volume(p,name,w,d,floors,3.05,mat,bay=3.25,side_windows=False,balconies=i==3)
        if i in (1,2): pitched_roof(p,name+'/roof',w,d,top,1.45,'arch_roof_slate')
        else: parapet(p,name+'/roof',w,d,top,mat,height=.72)
        box(p,name+'/entry-canopy',(2.7,.16,1.1),(.9,3.04,d/2+.48),'arch_frame_dark')
        register(name,p,'townhouse',w,d,3,'Windowless party walls; coordinated front and rear bay rhythms.')

    apartment_specs=[(25,16,4,'arch_brick_buff'),(30,18,5,'arch_plaster'),(34,18,6,'arch_brick_dark'),
                     (27,20,4,'arch_brick_red'),(38,19,6,'arch_limestone'),(32,22,5,'arch_plaster_sage'),
                     (24,18,7,'arch_brick_buff'),(40,20,5,'arch_plaster_warm')]
    for i,(w,d,floors,mat) in enumerate(apartment_specs,1):
        p=[];name=f'apartment_{i:02}'
        top=masonry_volume(p,name,w,d,floors,3.18,mat,bay=4.7,balconies=i%2==0,win_ratio=.61)
        parapet(p,name+'/roof',w,d,top,mat,height=.92)
        rooftop_services(p,name+'/services',w,d,top,solar=i%3==0)
        box(p,name+'/entry-canopy',(4.7,.22,2.0),(1.8,3.12,d/2+.89),'arch_frame_dark')
        if i in (2,5,8):
            # A set-back penthouse produces a legible residential roofline.
            ph=masonry_volume(p,name+'/penthouse',w*.62,d*.58,1,2.9,'arch_plaster',base=top+.18,bay=4.3,cx=-w*.08,cz=-d*.05,entry=False)
            parapet(p,name+'/penthouse-roof',w*.62,d*.58,ph,'arch_plaster',cx=-w*.08,cz=-d*.05,height=.55)
        register(name,p,'apartment_wing',w,d,floors,'Perimeter-block wing with real reveal openings; complete roof plant and selected balconies.')

    tower_specs=[(28,26,60,'arch_glass','arch_limestone'),(34,30,84,'arch_glass_dark','arch_frame'),
                 (30,28,105,'arch_glass_light','arch_stone_light'),(36,30,72,'arch_glass','arch_limestone'),
                 (27,25,125,'arch_glass_dark','arch_metal'),(40,31,53,'arch_glass_light','arch_limestone'),
                 (32,30,94,'arch_glass','arch_stone_light'),(29,27,67,'arch_glass_dark','arch_limestone'),
                 (36,32,110,'arch_glass_light','arch_frame'),(31,28,46,'arch_glass','arch_plaster')]
    for i,(w,d,height,glass,accent) in enumerate(tower_specs,1):
        p=[];name=f'tower_{i:02}'
        base=retail_base(p,name+'/retail',w,d,5.0,accent)
        # Retail base, distinct podium, vertical shaft and a setback crown.
        pod=curtain_volume(p,name+'/podium',w,d,base,7.2,glass,accent,storey=3.6)
        sw=w*(.72 if i%3 else .83);sd=d*(.75 if i%2 else .8)
        shaft_h=height-pod-6.3
        cx=(-.08 if i%2 else .06)*w;cz=-d*.045
        top=curtain_volume(p,name+'/shaft',sw,sd,pod+.22,shaft_h,glass,accent,cx,cz,bay=3.2,storey=3.7)
        crown=curtain_volume(p,name+'/crown',sw*.78,sd*.75,top+.15,5.0,glass,accent,cx,cz,bay=3.5,storey=5)
        parapet(p,name+'/crown-roof',sw*.78,sd*.75,crown,accent,cx,cz,height=.75)
        rooftop_services(p,name+'/roof-services',sw*.78,sd*.75,crown,cx,cz)
        if i in (3,5,9):
            cyl(p,name+'/spire',.14,6,(cx+sw*.16,crown+3.6,cz),'arch_metal',segments=8)
        if i in (2,7):
            for sg in (-1,1):
                box(p,name+f'/vertical-fin-{sg}',(.38,shaft_h,1.1),(cx+sg*sw*.27,pod+shaft_h/2,cz+sd/2+.22),'arch_white')
        register(name,p,'downtown_tower',w,d,round(height/3.7),'Ground retail; mullioned inset curtain walls; stepped podium and crown; concentrated downtown use.')

    for i,(w,d,height,mat) in enumerate([(30,26,8,'arch_brick_buff'),(38,30,11,'arch_limestone'),(42,32,8.4,'arch_brick_dark'),(28,25,14.6,'arch_plaster')],1):
        p=[];name=f'commercial_{i:02}'
        base=retail_base(p,name+'/retail',w,d,4.7,mat)
        top=curtain_volume(p,name+'/upper',w,d,base,height-base,'arch_glass',mat,bay=4.8,storey=3.5)
        parapet(p,name+'/roof',w,d,top,mat)
        rooftop_services(p,name+'/services',w,d,top,solar=i==3)
        # A clear architectural sign panel; text belongs to the local facade, not UI.
        box(p,name+'/front-sign',(w*.38,.65,.18),(0,4.2,d/2+.2),'arch_awning_green' if i%2 else 'arch_awning_red')
        register(name,p,'commercial',w,d,max(2,round(height/3.5)),'Fine-grained street retail with continuous doors, awnings and roof services.')

    # Museum: a strong central-park cultural termination with a stepped stone portico.
    p=[];w=52;d=30
    top=masonry_volume(p,'museum/wings',w,d,2,4.6,'arch_limestone',bay=6.0,win_ratio=.48)
    parapet(p,'museum/wings-roof',w,d,top,'arch_limestone',height=.8)
    top2=curtain_volume(p,'museum/central-lantern',22,19,top+.15,5.7,'arch_glass_light','arch_stone_light',cz=-1,bay=3.5)
    parapet(p,'museum/lantern-roof',22,19,top2,'arch_stone_light',cz=-1,height=.6)
    for x in (-8,-4,0,4,8):
        box(p,f'museum/portico/column-{x}',(.52,6.1,.52),(x,3.24,d/2+3.25),'arch_stone_light')
    box(p,'museum/portico/beam',(20.5,.55,4.1),(0,6.45,d/2+1.55),'arch_stone_light')
    for j in range(3):
        box(p,f'museum/portico/step-{j}',(22-j*.8,.12,4.8-j*.8),(0,.08+j*.12,d/2+1.4),'arch_limestone')
    rooftop_services(p,'museum/services',20,15,top,-14,-2)
    register('museum',p,'civic_hero',w,d,3,'Park cultural anchor with stone wings, recessed glazed lantern and colonnade.')

    # Library: low, horizontal civic building, sheltered front and reading-room lantern.
    p=[];w=44;d=28
    top=masonry_volume(p,'library',w,d,2,3.8,'arch_brick_buff',bay=5.8,win_ratio=.67)
    parapet(p,'library/roof',w,d,top,'arch_limestone',height=.7)
    curtain_volume(p,'library/reading-room',26,16,top+.2,3.4,'arch_glass_light','arch_frame',cz=-1,storey=3.4)
    box(p,'library/canopy',(32,.4,4),(0,3.35,d/2+1.6),'arch_limestone')
    for x in (-14,-7,7,14):
        box(p,f'library/column-{x}',(.3,3.2,.3),(x,1.72,d/2+3),'arch_frame_dark')
    rooftop_services(p,'library/services',16,12,top,-14,-5)
    register('library',p,'civic_hero',w,d,3,'Reading-room lantern, sheltered civic entrance and masonry wings.')

    # School: linked classroom volumes and a low glazed entrance commons.
    p=[];w=64;d=36
    for sg in (-1,1):
        tt=masonry_volume(p,f'school/wing-{sg}',20,d,2,3.6,'arch_brick_buff',bay=4.7,cx=sg*22,entry=False)
        parapet(p,f'school/wing-{sg}/roof',20,d,tt,'arch_limestone',cx=sg*22,height=.65)
    curtain_volume(p,'school/spine',26,16,.33,7.25,'arch_glass','arch_limestone',cz=-7,bay=4.0)
    curtain_volume(p,'school/commons',26,18,.33,3.8,'arch_glass_light','arch_limestone',cz=9,bay=4.0,storey=3.8)
    box(p,'school/entrance-canopy',(20,.3,3.0),(0,3.25,19.25),'arch_awning_green')
    for x in (-8,8): box(p,f'school/canopy-support-{x}',(.22,3.0,.22),(x,1.7,20.5),'arch_frame_dark')
    register('school',p,'civic_hero',w,d,2,'Two classroom wings with lower glazed entrance commons and a shared circulation spine.')

    # Sports hall: repeating sawtooth northlights over a large credible clear-span volume.
    p=[];w=48;d=32
    box(p,'sports_hall/plinth',(w+.3,.3,d+.3),(0,.15,0),'arch_foundation')
    box(p,'sports_hall/lower-mass',(w,5,d),(0,2.8,0),'arch_brick_dark')
    curtain_volume(p,'sports_hall/clerestory',w,d,5.2,3.3,'arch_glass_light','arch_frame',bay=5.2,storey=3.3)
    for k in range(6):
        xx=-w/2+(k+.5)*w/6
        box(p,f'sports_hall/northlight-{k}',(w/6+.12,.22,d+.7),(xx,9.18,0),'arch_roof_membrane',(0,0,-.15))
        box(p,f'sports_hall/northlight-glass-{k}',(.12,1.2,d),(xx-w/12,8.95,0),'arch_glass')
    retail_base(p,'sports_hall/foyer',20,11,4.7,'arch_limestone')
    # Move the foyer assembly as a group to meet the front of the main hall.
    start=next(i for i,part in enumerate(p) if part['name']=='sports_hall/foyer/plinth')
    for q in p[start:]:
        if 'position' in q:q['position'][2]+=d/2+4
        else:
            for v in q['vertices']:v[2]+=d/2+4
    register('sports_hall',p,'civic_hero',w,d,2,'Clear-span sports hall, sawtooth rooflights and distinct front foyer.')

    # Station: the long platform-side roof and front clock produce a southeastern landmark.
    p=[];w=80;d=30
    top=masonry_volume(p,'rail_station/hall',w,d,2,4.2,'arch_limestone',bay=7,win_ratio=.67)
    parapet(p,'rail_station/roof',w,d,top,'arch_limestone',height=.55)
    curtain_volume(p,'rail_station/lantern',54,17,top+.15,4.1,'arch_glass_light','arch_frame',bay=5.5,storey=4.1)
    box(p,'rail_station/platform-roof',(88,.3,10),(0,5.7,-d/2-4),'arch_roof_slate')
    for x in range(-40,41,10):
        box(p,f'rail_station/platform-post-{x}',(.24,5.45,.24),(x,2.9,-d/2-7.7),'arch_frame_dark')
        box(p,f'rail_station/platform-brace-{x}',(3.2,.14,.17),(x,5.17,-d/2-7.7),'arch_metal',(0,0,.15))
    box(p,'rail_station/entry-canopy',(26,.32,5),(0,4.8,d/2+2),'arch_roof_slate')
    box(p,'rail_station/clock-tower',(7,17,7),(23,8.65,6),'arch_limestone')
    box(p,'rail_station/clock-cap',(8.2,.42,8.2),(23,17.3,6),'arch_stone_light')
    cyl(p,'rail_station/clock-face',1.4,.12,(23,14.3,9.56),'arch_white',(math.pi/2,0,0),segments=24)
    box(p,'rail_station/clock-hour',(.14,.92,.05),(23,14.72,9.66),'arch_frame_dark')
    box(p,'rail_station/clock-minute',(.92,.12,.05),(23.38,14.3,9.67),'arch_frame_dark')
    register('rail_station',p,'civic_hero',w,d,2,'Long glazed concourse, platform canopy and clock tower; trains and rails are layout-owned.')

    p=[];w=42;d=30
    top=masonry_volume(p,'city_hall',w,d,3,3.8,'arch_limestone',bay=5,win_ratio=.55)
    parapet(p,'city_hall/roof',w,d,top,'arch_stone_light')
    curtain_volume(p,'city_hall/lantern',16,15,top+.2,4,'arch_glass_light','arch_frame',cz=-2)
    box(p,'city_hall/entry-canopy',(16,.4,3.8),(0,4.2,d/2+1.5),'arch_limestone')
    for x in (-7,-3.5,3.5,7):box(p,f'city_hall/column-{x}',(.35,3.9,.35),(x,2.24,d/2+2.9),'arch_limestone')
    cyl(p,'city_hall/flagpole',.075,9,(-13,4.65,d/2+3.2),'arch_metal',segments=8)
    box(p,'city_hall/banner',(1.6,1.0,.07),(-12.2,8.9,d/2+3.2),'arch_awning_navy')
    register('city_hall',p,'civic_hero',w,d,4,'Formal stone civic frontage with sheltered colonnade and central roof lantern.')

    p=[];w=34;d=26
    base=retail_base(p,'hotel/lobby',w,d,5.1,'arch_limestone')
    top=masonry_volume(p,'hotel/rooms',w*.9,d*.88,9,3.15,'arch_plaster_warm',base=base,bay=4.6,entry=False,win_ratio=.65)
    parapet(p,'hotel/roof',w*.9,d*.88,top,'arch_stone_light')
    rooftop_services(p,'hotel/services',w*.9,d*.88,top)
    box(p,'hotel/porte-cochere',(13,.33,5.5),(0,4.1,d/2+2.4),'arch_frame_dark')
    for x in (-5.6,5.6):box(p,f'hotel/porte-column-{x}',(.3,3.8,.3),(x,2.19,d/2+4.6),'arch_metal')
    register('hotel',p,'hotel',w,d,10,'Recessed lobby, regular bedroom bays, porte-cochere and rooftop plant.')

    path=Path(__file__).resolve().parent.parent/'architecture_catalog.json'
    path.write_text(json.dumps({'units':'meters','axes':'X east / Y up / Z south',
                                'primary_frontage':'+Z','prototypes':catalog},indent=2),encoding='utf-8')
    return catalog


if __name__=='__main__':
    class AuditScene:
        def __init__(self):self.prototypes={};self.materials={}
        def material(self,name,color,**kw):self.materials[name]=(color,kw)
        def prototype(self,name,parts,collision=None):
            if name in self.prototypes:raise ValueError('Duplicate prototype '+name)
            for p in parts:
                if p['material'] not in self.materials:raise ValueError('Unknown material '+p['material'])
                if p['shape']=='box' and min(p['size'])<=0:raise ValueError('Nonpositive box '+p['name'])
            self.prototypes[name]=(parts,collision)
    audit=AuditScene();catalog=build_architecture(audit)
    print(json.dumps({'prototypes':len(catalog),'materials':len(audit.materials),
                      'components':sum(v['components'] for v in catalog.values()),
                      'max_prototype_triangles':max(v['source_triangles_estimate'] for v in catalog.values()),
                      'bounds_checks':'finite dimensions and positive box dimensions passed'}))
