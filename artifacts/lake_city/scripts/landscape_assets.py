"""Detailed, deterministic public-realm prototypes for Lake City.

All source parts are editable and use metre-scale, Y-up coordinates.
The module registers kits only; the master layout owns all placement.
"""
import math
import random
import json
from pathlib import Path

TAU = math.tau


def box(parts, name, size, pos, mat, rotation=None):
    part = dict(shape='box', name=name, size=list(size), position=list(pos), material=mat)
    if rotation: part['rotation'] = list(rotation)
    parts.append(part)


def cyl(parts, name, radius, height, pos, mat, segments=12, radius_top=None, rotation=None):
    p = dict(shape='cylinder', name=name, radius=radius, height=height, position=list(pos), material=mat, segments=segments)
    if radius_top is not None: p['radiusTop'] = radius_top
    if rotation: p['rotation'] = list(rotation)
    parts.append(p)


def mesh(parts, name, vertices, faces, mat):
    parts.append(dict(shape='mesh', name=name, vertices=vertices, faces=faces, material=mat))


def tube(parts, name, start, end, radius, mat, sides=8, end_radius=None):
    # Exact arbitrary-axis branch/pole with capped ends; no Euler ambiguity.
    direction = [end[i]-start[i] for i in range(3)]
    length = math.sqrt(sum(v*v for v in direction))
    if length < 1e-8: return
    d = [v/length for v in direction]
    helper = [0,1,0] if abs(d[1]) < .95 else [1,0,0]
    u = [d[1]*helper[2]-d[2]*helper[1],d[2]*helper[0]-d[0]*helper[2],d[0]*helper[1]-d[1]*helper[0]]
    ul = math.sqrt(sum(v*v for v in u)); u=[v/ul for v in u]
    v = [d[1]*u[2]-d[2]*u[1], d[2]*u[0]-d[0]*u[2], d[0]*u[1]-d[1]*u[0]]
    vertices=[]
    for center, r in [(start,radius),(end,radius if end_radius is None else end_radius)]:
        for j in range(sides):
            a=TAU*j/sides
            vertices.append([center[k]+r*(u[k]*math.cos(a)+v[k]*math.sin(a)) for k in range(3)])
    faces=[]
    for j in range(sides):
        k=(j+1)%sides
        faces.extend([[j,k,sides+k],[j,sides+k,sides+j]])
    for j in range(1,sides-1):
        faces.extend([[0,j+1,j],[sides,sides+j,sides+j+1]])
    mesh(parts,name,vertices,faces,mat)


def ring(parts, name, radius, height, y, width, mat, n=48):
    vertices=[]
    for level in [y-height/2,y+height/2]:
        for rad in [radius-width/2,radius+width/2]:
            for i in range(n):
                a=TAU*i/n; vertices.append([math.cos(a)*rad,level,math.sin(a)*rad])
    faces=[]
    for i in range(n):
        j=(i+1)%n
        for a,b in [(0,n),(n,3*n),(3*n,2*n),(2*n,0)]:
            faces.extend([[a+i,a+j,b+j],[a+i,b+j,b+i]])
    mesh(parts,name,vertices,[list(reversed(f)) for f in faces],mat)


def leaf_batch(parts, name, points, mat, rng, leaf_scale=1, narrow=False):
    """Closed folded leaf geometry: four triangles per individually shaped leaf."""
    vertices=[]; faces=[]
    for x,y,z in points:
        a=rng.uniform(0,TAU); tilt=rng.uniform(-.55,.55)
        length=rng.uniform(.46,.82)*leaf_scale
        width=length*(.19 if narrow else .40)
        forward=[math.sin(a)*math.cos(tilt),math.sin(tilt),math.cos(a)*math.cos(tilt)]
        side=[math.cos(a),0,-math.sin(a)]
        local=[(-length*.5,0,0),(length*.5,0,0),(0,width*.5,.025),(0,-width*.5,-.015)]
        base=len(vertices)
        for f,s,h in local:
            vertices.append([x+forward[0]*f+side[0]*s,y+forward[1]*f+h,z+forward[2]*f+side[2]*s])
        faces.extend([[base,base+2,base+1],[base,base+1,base+3],[base,base+3,base+2],[base+1,base+2,base+3]])
    mesh(parts,name,vertices,faces,mat)


def tree_parts(species, seed, height=10, spread=4):
    rng=random.Random(seed); p=[]
    bark='land_birch_bark' if species=='birch' else 'land_bark'
    # Local Y=0 is the soil collar datum. The structural trunk and lateral
    # roots extend below it; only a restrained collar emerges above the soil.
    # Keep the upper stem endpoint and all crown geometry unchanged.
    radius=height*.027;top=height*.74;tip_radius=height*.011
    profile=[(-.52,radius*1.22),(-.22,radius*1.22),(-.06,radius*1.16),
             (.04,radius*1.10),(.22,radius*1.02),
             (.60,radius+(tip_radius-radius)*(.60/top)),(top,tip_radius)]
    trunk_vertices=[];trunk_faces=[];sides=12
    for y,r in profile:
        t=max(0.0,y)/top
        for j in range(sides):
            a=TAU*j/sides
            # Shallow radial variation merges the buried roots into the collar.
            lobe=1+.025*math.cos(4*a+.3)*max(0.0,1-abs(y)/.6)
            trunk_vertices.append([.14*t+math.cos(a)*r*lobe,y,-.06*t+math.sin(a)*r*lobe])
    for ring_index in range(len(profile)-1):
        base=ring_index*sides;upper=base+sides
        for j in range(sides):
            k=(j+1)%sides
            trunk_faces.extend([[base+j,upper+j,upper+k],[base+j,upper+k,base+k]])
    last=(len(profile)-1)*sides
    for j in range(1,sides-1):trunk_faces.extend([[0,j,j+1],[last,last+j+1,last+j]])
    mesh(p,'rooted_trunk',trunk_vertices,trunk_faces,bark)
    for j in range(4):
        a=TAU*j/4+.3
        tube(p,'root_flare_%02d'%j,[math.cos(a)*.48,-.31,math.sin(a)*.48],
             [0,-.035,0],.12,bark,5,.065)
    points=[]
    count=1800 if species!='pine' else 2400
    # Layered branch tips receive individually shaped foliage, leaving natural gaps.
    tips=[]
    for j in range(11):
        a=j*2.399963+seed
        frac=j/10
        if species=='poplar':
            by=height*(.27+.6*frac); reach=spread*(.48+.3*math.sin(frac*math.pi))
        elif species=='pine':
            by=height*(.23+.65*frac); reach=spread*(1-.75*frac)
        else:
            by=height*(.35+.42*frac); reach=spread*(.85-.28*frac)
        start=[.03,by,0]
        end=[math.cos(a)*reach,by+height*.13,math.sin(a)*reach]
        tube(p,'primary_branch_%02d'%j,start,end,height*.010*(1-.35*frac),bark,5,.025)
        for k in [-1,1]:
            aa=a+k*.56; rr=reach*rng.uniform(.83,1.12)
            tip=[math.cos(aa)*rr,end[1]+rng.uniform(.3,1.2),math.sin(aa)*rr]
            tube(p,'branchlet_%02d_%d'%(j,k),[v*.6+s*.4 for v,s in zip(end,start)],tip,.028,bark,4,.012)
            tips.append((tip, .65 if species=='poplar' else .83))
        tips.append((end,.85))
    for i in range(count):
        tip,volume=tips[i%len(tips)]
        phi=rng.uniform(0,TAU); elevation=rng.uniform(-1,1); r=rng.random()**.33*volume
        horizontal=math.sqrt(1-elevation*elevation)
        radial_factor=rng.uniform(.35,1.0) if i%3==0 else 1.0
        points.append([tip[0]*radial_factor+r*horizontal*math.cos(phi),tip[1]+r*elevation,tip[2]*radial_factor+r*horizontal*math.sin(phi)])
    for j in range(3):
        leaf_batch(p,'articulated_%s_foliage_%d'%(species,j),points[j::3],'land_%s_leaf_%d'%(species,j),rng,.90 if species=='birch' else 1.1,narrow=species=='pine')
    if species=='birch':
        for j in range(10):
            cyl(p,'bark_lenticel_%02d'%j,height*.027*(1-j*.035)+.007,.035,[.06,j*height*.06+.55,-.03],'land_bark',9)
    return p


def wheel(parts,name,x,y,z,r=.34,width=.18):
    cyl(parts,name+'_tire',r,width,[x,y,z],'land_rubber',14,rotation=[0,0,math.pi/2])
    cyl(parts,name+'_alloy',r*.57,width+.02,[x,y,z],'land_metal_silver',10,rotation=[0,0,math.pi/2])
    cyl(parts,name+'_hub',r*.20,width+.025,[x,y,z],'land_metal_dark',8,rotation=[0,0,math.pi/2])


def car_parts(kind,paint):
    p=[]; van=kind=='van'; suv=kind=='suv'; length=5.7 if van else 4.7 if suv else 4.45
    width=2.0 if van else 1.86; height=2.35 if van else 1.86 if suv else 1.50
    box(p,'chassis',[width*.88,.20,length*.91],[0,.41,0],'land_metal_dark')
    box(p,'body_sill',[width,.52,length],[0,.70,0],paint)
    # Tapered cabin shell, separate glazed windscreen and rear screen.
    cabin_front=length*.19; cabin_back=-length*.31
    roofwidth=width*.79
    vertices=[[-width*.46,.9,cabin_front+.30],[width*.46,.9,cabin_front+.30],[-width*.46,.9,cabin_back-.10],[width*.46,.9,cabin_back-.10],[-roofwidth/2,height,cabin_front-.20],[roofwidth/2,height,cabin_front-.20],[-roofwidth/2,height,cabin_back+.15],[roofwidth/2,height,cabin_back+.15]]
    mesh(p,'cabin_body',vertices,[[0,1,5],[0,5,4],[2,6,7],[2,7,3],[4,5,7],[4,7,6],[0,4,6],[0,6,2],[1,3,7],[1,7,5]],paint)
    for side in [-1,1]:
        for z0,z1 in [(-length*.28,-.11),(.03,length*.14)]:
            x0=side*(width*.465+.005); x1=side*(roofwidth*.502)
            mesh(p,'side_window',[[x0,1.00,z0],[x0,1.00,z1],[x1,height-.11,z1-.1],[x1,height-.11,z0+.1]],[[0,1,2],[0,2,3]],'land_vehicle_glass')
        box(p,'door_handle',[.045,.048,.19],[side*(width/2+.02),.99,-.22], 'land_metal_silver')
        box(p,'wing_mirror',[.23,.12,.22],[side*(width/2+.10),1.13,length*.15],paint)
    for z0,z1, yy in [(cabin_front+.31,cabin_front-.19,1), (cabin_back-.11,cabin_back+.14,-1)]:
        mesh(p,'windscreen' if yy==1 else 'rear_glazing',[[-width*.405,.97,z0],[width*.405,.97,z0],[roofwidth*.44,height-.09,z1],[-roofwidth*.44,height-.09,z1]],[[0,1,2],[0,2,3]],'land_vehicle_glass')
    if van:
        box(p,'cargo_body',[1.98,1.4,2.9],[0,1.46,-1.14],paint)
        box(p,'cargo_roof',[2.01,.09,3.0],[0,2.22,-1.12],paint)
        for side in [-1,1]: box(p,'cargo_panel_seam',[.012,1.08,.025],[side*1.00,1.54,-.3],'land_metal_silver')
    for x in [-width*.50,width*.50]:
        for z in [-length*.29,length*.29]: wheel(p,'wheel',x,.38,z,.38 if suv or van else .34)
    for end in [-1,1]:
        box(p,'bumper',[width*.98,.18,.12],[0,.47,end*length/2],'land_metal_dark')
        box(p,'license_plate',[.40,.14,.025],[0,.68,end*(length/2+.01)],'land_white')
        for x in [-width*.33,width*.33]: box(p,'headlamp' if end==1 else 'taillamp',[.42,.17,.045],[x,.87,end*(length/2+.015)],'land_lamp_glow' if end==1 else 'land_signal_red')
    box(p,'front_grille',[.70,.23,.05],[0,.84,length/2+.03],'land_metal_dark')
    return p,[width/2+.22,length/2+.05],[width+.44,height,length+.1]


def build_landscape_assets(scene):
    palette={
        'land_bark':'#675744','land_birch_bark':'#c8c8b4',
        'land_oak_leaf_0':'#385837','land_oak_leaf_1':'#577542','land_oak_leaf_2':'#79935a',
        'land_maple_leaf_0':'#3f633b','land_maple_leaf_1':'#638246','land_maple_leaf_2':'#819757',
        'land_birch_leaf_0':'#526b3b','land_birch_leaf_1':'#789550','land_birch_leaf_2':'#96a963',
        'land_poplar_leaf_0':'#395e37','land_poplar_leaf_1':'#5c7b42','land_poplar_leaf_2':'#839953',
        'land_pine_leaf_0':'#304b3d','land_pine_leaf_1':'#426547','land_pine_leaf_2':'#60835a',
        'land_metal_dark':'#303b40','land_metal_silver':'#8e999b','land_wood':'#9b704b','land_wood_light':'#bc9470',
        'land_concrete':'#bcbcb1','land_stone':'#d1cbb5','land_soil':'#544938','land_white':'#e9e5d6',
        'land_rubber':'#273033','land_vehicle_glass':'#425e6b','land_shelter_glass':'#739094','land_lamp_glow':'#f4e6b8',
        'land_signal_red':'#cc4335','land_signal_amber':'#e2ae43','land_signal_green':'#63a475',
        'land_car_blue':'#537a91','land_car_silver':'#aaaeb2','land_car_red':'#9c4840','land_car_white':'#dddcd3',
        'land_water':'#467f91','land_sand':'#cfc093','land_flower_pink':'#d394a5','land_flower_gold':'#e2c477',
        'land_play_blue':'#5b8f9e','land_play_red':'#b5684c','land_sign_green':'#335f57','land_sail':'#eee8cd'
    }
    for key,color in palette.items():
        scene.material(key,color,roughness=.42 if key in ['land_vehicle_glass','land_shelter_glass','land_water'] else .82,metalness=.38 if 'metal' in key else .07 if 'car_' in key else 0)
    catalog={}
    def register(name,parts,dimensions,collision=None,notes=''):
        scene.prototype(name,parts,collision=collision)
        triangles=sum(sum(len(f)-2 for f in part['faces']) if part['shape']=='mesh' else 12 if part['shape']=='box' else part.get('segments',12)*4 for part in parts)
        catalog[name]={'dimensions_m':dimensions,'collision_half_extents':collision,'source_parts':len(parts),'source_triangles':triangles,'notes':notes}
    for name,species,seed,height,spread in [('tree_oak','oak',38,11.8,3.8),('tree_maple','maple',59,10.8,3.3),('tree_birch','birch',14,11.7,2.65),('tree_poplar','poplar',76,14.2,1.6),('tree_pine','pine',93,13.5,3.0),('tree_oak_young','oak',51,7.3,2.4),('tree_maple_young','maple',69,6.7,2.15)]:
        register(name,tree_parts(species,seed,height,spread),[spread*2+1.8,height+1.3,spread*2+1.8],[.32,.32],'Articulated branches and individual folded leaves; collision is trunk only. Soil collar datum Y=0; trunk embeds to Y=-.52 and root flares stay below Y=.022. Anchor to sampled surface minus .06m.')
    rng=random.Random(28)
    p=[]
    for j in range(7):
        a=TAU*j/7
        tube(p,'shrub_branch',[0,0,0],[math.cos(a)*.58,.95,math.sin(a)*.58],.025,'land_bark',5,.008)
    points=[[rng.uniform(-.8,.8),rng.uniform(.28,1.3),rng.uniform(-.72,.72)] for _ in range(100)]
    leaf_batch(p,'shrub_leaf_group',points,'land_oak_leaf_1',rng,.7)
    register('shrub',p,[1.9,1.4,1.7],None)
    p=[]
    box(p,'planter_base',[1.5,.12,.75],[0,.06,0],'land_concrete')
    for z in [-.36,.36]: box(p,'planter_long_wall',[1.5,.65,.085],[0,.42,z],'land_stone')
    for x in [-.71,.71]: box(p,'planter_end_wall',[.085,.65,.65],[x,.42,0],'land_stone')
    box(p,'soil',[1.31,.06,.55],[0,.65,0],'land_soil')
    points=[]
    for i in range(18):
        x=rng.uniform(-.58,.58); z=rng.uniform(-.20,.20); h=rng.uniform(.82,1.10)
        tube(p,'flower_stem',[x,.66,z],[x+.02,h,z],.007,'land_oak_leaf_0',4)
        points.extend([[x,h-.14,z],[x+.06,h-.20,z]])
        for j in range(5):
            a=TAU*j/5
            vv=[[x,h,z],[x+math.cos(a)*.075,h+.027,z+math.sin(a)*.075],[x+math.cos(a+.65)*.10,h+.004,z+math.sin(a+.65)*.10]]
            mesh(p,'petal',vv,[[0,1,2],[0,2,1]],'land_flower_pink' if i%3 else 'land_flower_gold')
    leaf_batch(p,'flower_leaves',points,'land_maple_leaf_1',rng,.23)
    register('flower_planter',p,[1.5,1.15,.75],[.75,.375])
    p=[]
    for i in range(14):
        x=rng.uniform(-.65,.65); z=rng.uniform(-.60,.6); h=rng.uniform(.6,1.5)
        tube(p,'reed_stem',[x,0,z],[x+.06,h,z+.03],.012,'land_birch_leaf_1',4)
        tube(p,'reed_head',[x+.06,h*.86,z+.03],[x+.06,h+.14,z+.03],.032,'land_bark',5)
        for a in [-1,1]:
            mesh(p,'reed_blade',[[x,.12,z],[x+a*.13,h*.61,z+.08],[x+a*.34,h*.76,z+.1],[x+a*.08,h*.54,z]],[[0,1,2],[0,2,3]],'land_birch_leaf_1')
    register('reeds',p,[1.8,1.65,1.5],None)
    # Benches: slats, cast supports, arms and back rails.
    p=[]
    for x in [-.77,.77]:
        for z in [-.21,.21]: tube(p,'bench_leg',[x,0,z],[x,.48,z],.035,'land_metal_dark',7)
        box(p,'seat_support',[.07,.08,.63],[x,.40,0],'land_metal_dark')
        tube(p,'back_support',[x,.3,-.24],[x,.97,-.39],.026,'land_metal_dark',7)
        tube(p,'arm_upright',[x,.45,.18],[x,.68,.18],.025,'land_metal_dark',7)
        tube(p,'arm_rail',[x,.68,.18],[x,.72,-.30],.027,'land_metal_dark',7)
    for j in range(5): box(p,'seat_slat_%d'%j,[1.90,.055,.083],[0,.47,-.19+j*.098],'land_wood')
    for j in range(3): box(p,'back_slat_%d'%j,[1.90,.09,.055],[0,.69+j*.105,-.31-j*.02],'land_wood',[-.16,0,0])
    register('bench',p,[1.9,1.0,.8],[.98,.42])
    p=[]
    cyl(p,'bin_base',.30,.075,[0,.04,0],'land_metal_dark',16)
    for j in range(16):
        a=j*TAU/16
        box(p,'bin_timber_slat',[.073,.76,.052],[math.sin(a)*.285,.48,math.cos(a)*.285],'land_wood',[0,a,0])
    ring(p,'bin_upper_band',.29,.06,.81,.035,'land_metal_dark',16)
    ring(p,'bin_lip',.29,.055,.91,.085,'land_metal_dark',16)
    cyl(p,'dark_bin_opening',.245,.01,[0,.78,0],'land_rubber',16)
    register('trash_bin',p,[.65,.94,.65],[.32,.32])
    p=[]
    cyl(p,'lamp_base',.19,.25,[0,.125,0],'land_metal_dark',10)
    tube(p,'lamp_tapered_post',[0,.22,0],[0,7.4,0],.075,'land_metal_dark',10,.047)
    tube(p,'lamp_arm',[0,7.18,0],[0,7.42,.98],.05,'land_metal_dark',8)
    box(p,'lamp_housing',[.43,.14,1.0],[0,7.43,1.18],'land_metal_dark')
    box(p,'lamp_diffuser',[.34,.025,.80],[0,7.35,1.18],'land_lamp_glow')
    register('street_lamp',p,[.45,7.52,1.85],[.13,.13])
    p=[]
    cyl(p,'signal_base',.15,.16,[0,.08,0],'land_metal_dark',10)
    tube(p,'signal_post',[0,.12,0],[0,3.4,0],.066,'land_metal_dark',10)
    box(p,'signal_box',[.35,1.04,.28],[0,3.11,.08],'land_metal_dark')
    for j,mat in enumerate(['land_signal_green','land_signal_amber','land_signal_red']):
        cyl(p,'signal_lens',.103,.03,[0,2.80+j*.30,.238],mat,12,rotation=[math.pi/2,0,0])
        box(p,'signal_visor',[.30,.045,.22],[0,2.93+j*.30,.29],'land_metal_dark')
    register('traffic_light',p,[.36,3.66,.55],[.14,.14])
    p=[]
    box(p,'shelter_foundation',[4.5,.10,1.8],[0,.05,0],'land_concrete')
    for x in [-2.08,2.08]:
        for z in [-.65,.65]: box(p,'shelter_pillar',[.07,2.45,.07],[x,1.27,z],'land_metal_dark')
    box(p,'shelter_roof',[4.65,.15,1.96],[0,2.54,0],'land_metal_dark')
    box(p,'shelter_roof_edge',[4.66,.045,.04],[0,2.51,.99],'land_metal_silver')
    box(p,'shelter_back_glass',[4.03,1.86,.032],[0,1.4,-.65],'land_shelter_glass')
    box(p,'shelter_side_glass',[.032,1.86,1.16],[-2.08,1.4,-.04],'land_shelter_glass')
    box(p,'shelter_seat',[3.0,.08,.44],[0,.52,-.24],'land_wood')
    for x in [-1.1,1.1]: box(p,'shelter_seat_leg',[.10,.49,.15],[x,.265,-.24],'land_metal_dark')
    box(p,'timetable_frame',[.6,1.0,.055],[1.40,1.51,-.61],'land_metal_dark')
    box(p,'timetable_panel',[.50,.87,.02],[1.40,1.51,-.57],'land_white')
    for j in range(6): box(p,'timetable_rule',[.35,.018,.01],[1.40,1.80-j*.115,-.55],'land_metal_silver')
    register('bus_shelter',p,[4.65,2.62,1.98],[2.32,.45],'Place rear boundary outside the pedestrian clear corridor.')
    p=[]
    for z in [-.66,.66]:
        # Bicycle is aligned along Z; wheel planes are YZ.
        ring_vertices=[]; ring_faces=[]
        for r in [.298,.333]:
            for j in range(20):
                a=j*TAU/20; ring_vertices.append([0,.355+math.sin(a)*r,z+math.cos(a)*r])
        for j in range(20):
            k=(j+1)%20; ring_faces.extend([[j,k,20+k],[j,20+k,20+j]])
        mesh(p,'bicycle_tire',ring_vertices,ring_faces,'land_rubber')
        for j in range(10):
            a=j*TAU/10
            tube(p,'wheel_spoke',[0,.355,z],[0,.355+math.sin(a)*.30,z+math.cos(a)*.30],.005,'land_metal_silver',3)
        tube(p,'wheel_axle',[-.075,.355,z],[.075,.355,z],.023,'land_metal_silver',6)
    anchors=[([0,.355,-.66],[0,.40,-.06]),([0,.355,-.66],[0,.89,-.23]),([0,.40,-.06],[0,.89,-.23]),([0,.89,-.23],[0,.94,.39]),([0,.40,-.06],[0,.94,.39]),([0,.94,.39],[0,.355,.66])]
    for a,b in anchors: tube(p,'bicycle_frame',a,b,.027,'land_play_blue',6)
    tube(p,'seat_post',[0,.78,-.21],[0,1.01,-.24],.022,'land_metal_silver',6)
    box(p,'bicycle_saddle',[.22,.065,.28],[0,1.04,-.26],'land_rubber')
    tube(p,'handlebar_stem',[0,.94,.39],[0,1.12,.43],.019,'land_metal_silver',6)
    tube(p,'handlebar',[-.30,1.12,.43],[.30,1.12,.43],.02,'land_metal_dark',6)
    tube(p,'crank_axis',[-.13,.40,-.06],[.13,.40,-.06],.025,'land_metal_dark',6)
    for x,z in [(-.17,-.18),(.17,.06)]: box(p,'pedal',[.12,.035,.085],[x,.40,z],'land_metal_dark')
    register('bicycle',p,[.66,1.16,2.02],None)
    p=[]
    for z in [-1.10,-.55,0,.55,1.10]:
        tube(p,'rack_leg',[-.36,0,z],[-.36,.68,z],.030,'land_metal_silver',7)
        tube(p,'rack_crossbar',[-.36,.68,z],[.36,.68,z],.030,'land_metal_silver',7)
        tube(p,'rack_leg',[.36,0,z],[.36,.68,z],.030,'land_metal_silver',7)
    register('bike_rack',p,[.78,.72,2.30],[.40,1.18])
    for name,kind,paint in [('car_sedan','sedan','land_car_blue'),('car_suv','suv','land_car_silver'),('delivery_van','van','land_car_white')]:
        parts,col,dim=car_parts(kind,paint); register(name,parts,dim,col)
    p=[]
    cyl(p,'fountain_foundation',4.25,.18,[0,.09,0],'land_stone',48)
    ring(p,'fountain_basin',3.8,.62,.45,.35,'land_stone',48)
    cyl(p,'fountain_water',3.58,.04,[0,.60,0],'land_water',48)
    cyl(p,'fountain_central_column',.55,1.60,[0,1.20,0],'land_stone',16,radius_top=.34)
    cyl(p,'fountain_upper_bowl',1.28,.28,[0,2.08,0],'land_stone',28,radius_top=1.45)
    cyl(p,'fountain_upper_water',1.21,.035,[0,2.23,0],'land_water',28)
    cyl(p,'fountain_finial',.12,.55,[0,2.52,0],'land_stone',10,radius_top=.025)
    for j in range(12):
        a=TAU*j/12
        tube(p,'falling_water',[math.cos(a)*1.26,2.14,math.sin(a)*1.26],[math.cos(a)*1.60,.62,math.sin(a)*1.60],.028,'land_water',5)
    register('fountain',p,[8.5,2.8,8.5],[4.2,4.2])
    p=[]
    cyl(p,'pavilion_slab',4.05,.20,[0,.1,0],'land_stone',12)
    cyl(p,'pavilion_inner_deck',3.65,.12,[0,.25,0],'land_wood_light',12)
    for j in range(8):
        a=TAU*j/8;x=math.cos(a)*3.2;z=math.sin(a)*3.2
        tube(p,'pavilion_column',[x,.3,z],[x,3.75,z],.105,'land_wood',8)
        box(p,'pavilion_post_foot',[.28,.15,.28],[x,.36,z],'land_metal_dark')
        aa=a+TAU/8;xx=math.cos(aa)*3.2;zz=math.sin(aa)*3.2
        tube(p,'pavilion_eave_beam',[x,3.7,z],[xx,3.7,zz],.13,'land_wood',4)
        tube(p,'pavilion_rafter',[x,3.80,z],[0,5.13,0],.10,'land_wood',4)
    cyl(p,'pavilion_hip_roof',4.16,1.52,[0,4.47,0],'land_metal_dark',8,radius_top=.32)
    cyl(p,'pavilion_roof_cap',.38,.27,[0,5.31,0],'land_metal_dark',8,radius_top=.12)
    register('park_pavilion',p,[8.32,5.46,8.32],None,'Open shelter: preserve traversable floor and entries.')
    p=[]
    for x in [-1.75,1.75]:
        for z in [-1.00,1.00]: tube(p,'swing_A_frame',[x,0,z],[x,2.8,0],.06,'land_metal_dark',8)
        tube(p,'swing_cross_brace',[x,1.0,-.64],[x,1.0,.64],.04,'land_metal_dark',7)
    tube(p,'swing_header',[-2.03,2.8,0],[2.03,2.8,0],.075,'land_play_blue',10)
    for x in [-.77,.77]:
        for dx in [-.21,.21]: tube(p,'swing_chain',[x+dx,2.77,0],[x+dx,.52,.06],.012,'land_metal_silver',5)
        box(p,'swing_seat',[.55,.065,.28],[x,.51,.06],'land_rubber')
    register('playground_swing',p,[4.2,2.9,2.15],None)
    p=[]
    for x in [-.55,.55]:
        for z in [-.55,.55]: tube(p,'slide_tower_leg',[x,0,z],[x,2.3,z],.06,'land_play_blue',7)
    box(p,'slide_platform',[1.23,.12,1.23],[0,1.6,0],'land_wood')
    for x in [-.59,.59]:
        tube(p,'slide_handrail',[x,2.26,-.56],[x,2.26,.56],.035,'land_play_blue',6)
        tube(p,'ladder_side',[x,0,-1.28],[x,1.65,-.52],.038,'land_metal_silver',7)
    for j in range(6): tube(p,'ladder_rung',[-.55,.18+j*.26,-1.20+j*.12],[.55,.18+j*.26,-1.20+j*.12],.027,'land_metal_silver',7)
    mesh(p,'slide_bed',[[-.45,1.61,.5],[.45,1.61,.5],[-.45,.20,3.0],[.45,.20,3.0],[-.45,.12,3.60],[.45,.12,3.60]],[[0,1,3],[0,3,2],[2,3,5],[2,5,4]],'land_metal_silver')
    for x in [-.48,.48]:
        tube(p,'slide_raised_edge',[x,1.77,.5],[x,.36,3.0],.063,'land_play_red',7)
        tube(p,'slide_end_edge',[x,.36,3.0],[x,.23,3.60],.063,'land_play_red',7)
    register('playground_slide',p,[1.35,2.35,5.1],None)
    p=[]
    for x in [-.73,.73]:
        for z in [-.57,.57]: tube(p,'table_A_leg',[x,0,z],[x,.73,z*.30],.056,'land_wood',5)
        box(p,'bench_spreader',[.10,.09,1.68],[x,.40,0],'land_wood')
    for j in range(5): box(p,'tabletop_slat',[2.15,.06,.14],[0,.78,-.32+j*.16],'land_wood_light')
    for z in [-.67,.67]:
        for j in [-1,1]: box(p,'picnic_seat_slat',[2.15,.06,.14],[0,.45,z+j*.08],'land_wood')
    register('picnic_table',p,[2.2,.84,1.70],[1.1,.85])
    p=[]
    for x in [-.6,.6]: tube(p,'sign_leg',[x,0,0],[x,1.85,0],.055,'land_wood',7)
    box(p,'sign_frame',[1.58,.89,.13],[0,1.49,.01],'land_wood')
    box(p,'sign_face',[1.44,.74,.024],[0,1.49,.09],'land_sign_green')
    for j in range(4): box(p,'sign_graphic',[.95-j*.13,.035,.012],[-.10,1.71-j*.14,.11],'land_white')
    register('park_sign',p,[1.6,1.95,.22],[.8,.16])
    # Marina kit: planked floating docks, full hulls and rigging.
    p=[]
    box(p,'dock_float',[2.4,.30,7.7],[0,.15,0],'land_rubber')
    for j in range(32): box(p,'dock_board',[2.65,.105,.227],[0,.345,-3.82+j*.246],'land_wood_light')
    for x in [-1.17,1.17]: box(p,'dock_stringer',[.12,.28,7.93],[x,.26,0],'land_wood')
    for x in [-1.15,1.15]:
        for z in [-3.60,3.60]:
            tube(p,'dock_mooring_post',[x,-.65,z],[x,1.1,z],.085,'land_wood',8)
            box(p,'dock_cleat',[.22,.06,.055],[x,.56,z],'land_metal_silver')
    register('dock_module',p,[2.65,1.2,8.0],None,'Deck Y=.40. Add walk surface with master placement.')
    def boat_hull(p,length,width):
        vertices=[[-width*.34,.28,-length*.45],[width*.34,.28,-length*.45],[-width*.50,.38,length*.08],[width*.50,.38,length*.08],[0,.50,length*.52],[-width*.24,-.25,-length*.42],[width*.24,-.25,-length*.42],[0,-.26,length*.37]]
        mesh(p,'boat_hull',vertices,[[0,2,4],[0,4,1],[1,4,3],[0,5,7],[0,7,2],[2,7,4],[4,7,3],[3,7,6],[3,6,1],[1,6,5],[1,5,0],[5,6,7]],'land_white')
        box(p,'boat_transom',[width*.65,.40,.06],[0,.05,-length*.45],'land_white')
    p=[]; boat_hull(p,7.8,2.6)
    box(p,'cockpit_recess',[1.58,.08,2.20],[0,.33,-1.95],'land_wood')
    box(p,'sailboat_cabin',[1.66,.68,2.65],[0,.64,.1],'land_white')
    box(p,'sailboat_cabin_top',[1.78,.09,2.74],[0,1.03,.1],'land_wood_light')
    for x in [-.846,.846]: box(p,'cabin_portlight',[.035,.25,.65],[x,.78,.15],'land_vehicle_glass')
    tube(p,'sailboat_mast',[0,.60,.60],[0,10.0,.60],.07,'land_metal_silver',10,.043)
    tube(p,'sailboat_boom',[0,1.7,.60],[0,1.7,-2.8],.065,'land_metal_silver',8)
    mesh(p,'mainsail',[[.04,1.85,-2.72],[.04,1.85,.52],[.04,9.5,.52],[.22,4.20,-1.03]],[[0,1,3],[1,2,3],[2,0,3],[0,3,1],[1,3,2],[2,3,0]],'land_sail')
    mesh(p,'jib_sail',[[-.04,2.05,.75],[-.04,.93,3.65],[-.04,8.6,.65]],[[0,1,2],[0,2,1]],'land_sail')
    for z in [-3.6,3.6]: tube(p,'mast_stay',[0,.5,z],[0,9.3,.6],.010,'land_metal_silver',4)
    for x in [-1.03,1.03]:
        tube(p,'sailboat_railing',[x,.83,-2.9],[x,.93,1.4],.020,'land_metal_silver',5)
        for z in [-2.9,-1.5,0,1.4]:tube(p,'rail_stanchion',[x,.36,z],[x,.86,z],.018,'land_metal_silver',5)
    register('sailboat',p,[2.7,10.1,8.0],None)
    p=[];boat_hull(p,5.25,2.20)
    box(p,'motorboat_floor',[1.65,.08,3.45],[0,.29,-.30],'land_wood_light')
    box(p,'motorboat_console',[1.60,.53,.55],[0,.60,.85],'land_white')
    box(p,'motorboat_windscreen',[1.65,.50,.055],[0,1.10,.80],'land_vehicle_glass',[-.22,0,0])
    for x in [-.52,.52]:
        box(p,'boat_seat',[.64,.18,.59],[x,.52,-.38],'land_white')
        box(p,'boat_seat_back',[.64,.56,.11],[x,.80,-.61],'land_white')
    box(p,'outboard_engine',[.56,.73,.42],[0,.36,-2.45],'land_metal_dark')
    tube(p,'outboard_shaft',[0,.15,-2.44],[0,-.62,-2.44],.09,'land_metal_dark',8)
    register('motorboat',p,[2.25,1.45,5.5],None)
    # Sports equipment remains true metre scale and independently placeable.
    p=[]
    for x in [-3.66,3.66]:
        tube(p,'goal_front_post',[x,0,0],[x,2.44,0],.055,'land_white',8)
        tube(p,'goal_side_stay',[x,2.44,0],[x,.06,-1.85],.04,'land_white',8)
        tube(p,'goal_base',[x,.055,0],[x,.055,-1.85],.04,'land_white',8)
    tube(p,'goal_crossbar',[-3.66,2.44,0],[3.66,2.44,0],.06,'land_white',8)
    tube(p,'goal_back_base',[-3.66,.055,-1.85],[3.66,.055,-1.85],.04,'land_white',8)
    for i in range(25):
        x=-3.6+i*.3; tube(p,'net_vertical',[x,2.40,-.04],[x,.07,-1.81],.006,'land_white',3)
    for j in range(9):
        yy=.08+j*.285;zz=-1.81+yy/2.4*1.77
        tube(p,'net_horizontal',[-3.65,yy,zz],[3.65,yy,zz],.006,'land_white',3)
    register('soccer_goal',p,[7.45,2.52,1.97],None)
    p=[]
    box(p,'hoop_base',[.75,.16,.75],[0,.08,-1.3],'land_concrete')
    tube(p,'hoop_post',[0,.13,-1.3],[0,3.42,-1.3],.095,'land_metal_dark',10)
    tube(p,'hoop_arm',[0,3.35,-1.3],[0,3.35,-.08],.075,'land_metal_dark',8)
    box(p,'backboard',[1.8,1.05,.095],[0,3.42,0],'land_white')
    for x in [-.30,.30]: box(p,'backboard_target',[.032,.45,.022],[x,3.37,.059],'land_play_red')
    for y in [3.145,3.595]: box(p,'backboard_target',[.60,.032,.022],[0,y,.059],'land_play_red')
    # Ring primitive in XZ plane, translated toward the playing surface.
    before=len(p);ring(p,'basketball_rim',.225,.026,3.05,.023,'land_play_red',24)
    for part in p[before:]:
        for vertex in part['vertices']:vertex[2]+=.34
    for j in range(12):
        a=TAU*j/12
        tube(p,'hoop_net',[math.cos(a)*.216,3.03,.34+math.sin(a)*.216],[math.cos(a+.2)*.14,2.65,.34+math.sin(a+.2)*.14],.007,'land_white',3)
    register('basketball_hoop',p,[1.9,4.0,2.1],None)
    p=[]
    for x in [-6.40,6.40]:cyl(p,'tennis_net_post',.042,1.12,[x,.56,0],'land_metal_dark',8)
    for i in range(65):
        x=-6.40+i*.20; h=.92+.14*(abs(x)/6.4)**2
        tube(p,'tennis_mesh_vertical',[x,.1,0],[x,h,0],.007,'land_metal_dark',3)
    for j in range(6):tube(p,'tennis_mesh_horizontal',[-6.4,.10+j*.155,0],[6.4,.10+j*.155,0],.006,'land_metal_dark',3)
    for j in range(16):
        x=-6.4+j*.8;x2=x+.8
        tube(p,'tennis_white_top_band',[x,.92+.14*(abs(x)/6.4)**2,0],[x2,.92+.14*(abs(x2)/6.4)**2,0],.025,'land_white',5)
    register('tennis_net',p,[12.9,1.15,.10],None)
    # A small bollard and a modular fence improve street-edge legibility.
    p=[]
    cyl(p,'bollard_base',.13,.07,[0,.035,0],'land_metal_dark',10)
    cyl(p,'bollard_post',.075,.85,[0,.48,0],'land_metal_dark',10)
    cyl(p,'bollard_band',.079,.06,[0,.76,0],'land_metal_silver',10)
    register('bollard',p,[.28,.91,.28],[.13,.13])
    p=[]
    for x in [-1.2,1.2]:box(p,'fence_post',[.10,1.15,.10],[x,.575,0],'land_metal_dark')
    for y in [.22,1.04]:box(p,'fence_horizontal',[2.4,.05,.05],[0,y,0],'land_metal_dark')
    for j in range(13):box(p,'fence_picket',[.025,1.0,.025],[-1.14+j*.19,.62,0],'land_metal_dark')
    register('park_fence',p,[2.50,1.16,.11],None)
    return catalog


if __name__ == '__main__':
    class CatalogScene:
        def __init__(self):self.materials={};self.prototypes={}
        def material(self,name,color,**kwargs):self.materials[name]={'color':color,**kwargs}
        def prototype(self,name,parts,collision=None):self.prototypes[name]={'parts':parts,'collision':collision}
    test_scene=CatalogScene()
    catalog=build_landscape_assets(test_scene)
    path=Path(__file__).with_name('landscape_catalog.json')
    path.write_text(json.dumps(catalog,indent=2),encoding='utf-8')
    print(json.dumps({'prototypes':len(catalog),'materials':len(test_scene.materials),'source_parts':sum(len(p['parts']) for p in test_scene.prototypes.values()),'catalog':str(path)}))
