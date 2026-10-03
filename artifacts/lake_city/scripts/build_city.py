import argparse,json,math,random,sys
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,LineString,Point,box as sbox
from shapely.ops import unary_union
from citylib import *

PARK=(815,168,981,795)
LAKE=[(105,140),(143,114),(181,80),(218,77),(248,92),(262,111),(302,110),(351,125),(382,150),(398,199),(413,231),(443,244),(469,271),(478,303),(466,335),(463,354),(446,377),(449,401),(470,420),(479,464),(490,490),(481,525),(477,560),(484,592),(506,626),(507,665),(495,700),(466,731),(438,748),(418,769),(413,805),(400,832),(363,842),(334,838),(308,843),(280,870),(251,890),(216,896),(192,865),(171,839),(142,822),(127,800),(99,788),(73,761),(64,719),(62,682),(62,641),(72,602),(74,570),(69,535),(80,506),(90,485),(97,460),(91,435),(85,412),(77,394),(72,364),(84,337),(97,316),(105,289),(104,265),(98,244),(97,225),(107,207),(103,182)]
ISLANDS=[[(149,258),(176,259),(186,278),(175,304),(178,325),(186,345),(175,357),(160,345),(152,325),(137,311),(135,289)],[(132,553),(149,554),(157,581),(180,597),(203,600),(221,621),(225,642),(208,664),(191,658),(176,637),(150,623),(140,603),(128,581)],[(304,122),(314,122),(319,132),(314,144),(303,141),(299,131)]]
PX=lambda pts:[[world(x,z)[0],world(x,z)[2]] for x,z in pts]

def build(stage):
 s=Scene(); rng=random.Random(1937)
 palette={'grass':'#66804b','lawn':'#839653','forest_floor':'#455e38','verge':'#71864c','asphalt':'#565d60','sidewalk':'#b9b9af','path':'#cfc4a7','cycle_path':'#a9b1a0','road_white':'#e4e0cf','road_yellow':'#d9bd73','lake_water':'#174e61','pond_water':'#2b6769','shore_sand':'#b7ae85','wet_shore':'#687e66','plaza':'#c9c5b8','sports_turf':'#4d7a41','sports_red':'#a06f58','sports_blue':'#587c86','garden_soil':'#64563f','track_rail':'#73767a','ballast':'#867d6b','station_roof':'#aeb7b7'}
 for k,c in palette.items():s.material(k,c, .26 if 'water' in k else .87, .25 if 'water' in k else 0)
 lake=Polygon(PX(catmull(LAKE,6,True))).buffer(0)
 islands=[Polygon(PX(catmull(p,5,True))).buffer(0) for p in ISLANDS]
 water=lake.difference(unary_union(islands))
 river_line=LineString(PX(catmull([(16,397),(24,434),(8,487),(22,544),(12,620),(3,705),(29,757),(60,805),(111,857),(148,925),(210,965),(247,1019),(277,1088)],7)))
 river_water=river_line.buffer(10)
 park=sbox(*[0,0,1,1]);a=world(PARK[0],PARK[1]);b=world(PARK[2],PARK[3]);park=sbox(a[0],a[2],b[0],b[2])
 s.surface(lake.buffer(4).difference(lake),.015,'shore_sand',2,'REG_LAKE');s.surface(water,.025,'lake_water',2,'REG_LAKE')
 for isl in islands:s.surface(isl,.055,'grass',2,'REG_LAKE')
 s.waterPolygons=[list(lake.exterior.coords),list(river_water.exterior.coords)];s.waterHolePolygons=[list(p.exterior.coords) for p in islands]
 # The complete pedestrian and cycle loop is derived from the traced bank.
 lake_walk=LineString(lake.buffer(11,resolution=8).exterior.coords)
 lake_cycle=LineString(lake.buffer(19,resolution=8).exterior.coords)
 s.surface(lake_walk.buffer(2.7),.075,'path',2,'REG_WATERFRONT');s.paths.append(dict(id='PATH_LAKE_COMPLETE_LOOP',points=list(lake_walk.coords),width=5.4,closed=True,stage=2))
 s.surface(lake_cycle.buffer(1.7),.065,'cycle_path',2,'REG_WATERFRONT');s.paths.append(dict(id='PATH_LAKE_CYCLE_LOOP',points=list(lake_cycle.coords),width=3.4,closed=True,stage=2))
 ring=LineString(lake.buffer(36,resolution=8).exterior.coords)
 # Road hierarchy includes dedicated pavement outside the carriageway.
 road_reservations=[];road_records=[]
 def road(name,points,width=12,st=3,closed=False):
  pts=PX(points);line=LineString(pts+([pts[0]] if closed else []))
  if name.startswith('RD_LOCAL_'):
   dry=line.difference(lake.buffer(36))
   if dry.is_empty:return line
   line=max(dry.geoms,key=lambda p:p.length) if dry.geom_type=='MultiLineString' else dry
   pts=list(line.coords)
  road_reservations.append(line.buffer(width/2+6))
  s.surface(line.buffer(width/2+4.5,join_style=1),.07,'sidewalk',st)
  s.surface(line.buffer(width/2,join_style=1),.095,'asphalt',st)
  # Dashed lane markings sampled from the actual continuous centerline.
  for distance in np.arange(6,line.length-5,13):
   p=line.interpolate(distance);q=line.interpolate(min(distance+5,line.length))
   s.surface(LineString([p,q]).buffer(.11,cap_style=2),.106,'road_white',st)
  road_records.append(dict(id=name,points=pts,width=width,stage=st))
  s.paths.append(dict(id=name+'_sidewalk',points=list(line.parallel_offset(width/2+2.6,'left',join_style=2).coords) if line.parallel_offset(width/2+2.6,'left',join_style=2).geom_type=='LineString' else pts,width=3.2,closed=closed,stage=st))
  return line
 s.surface(ring.buffer(9),.075,'sidewalk',3,'REG_WATERFRONT');s.surface(ring.buffer(5.5),.1,'asphalt',3,'REG_WATERFRONT');road_reservations.append(ring.buffer(13))
 road_records.append(dict(id='RD_LAKESHORE',points=list(ring.coords),width=11,stage=3))
 # Long north-south roads are straight and share the reference's datums.
 for u,width in [(486,11),(597,10),(724,20),(806,13),(997,20),(1090,12),(1207,12),(1339,14)]:
  spans=[(0,144),(790,1088)] if u==486 else ([(0,140),(166,1088)] if u==597 else [(0,1088)])
  for j,(v0,v1) in enumerate(spans):road(f'RD_NS_{u}_{j}',[(u,v0),(u,v1)],width)
 for v,left,width in [(36,480,10),(93,482,9),(151,451,20),(275,501,12),(367,473,11),(452,511,11),(581,504,20),(691,527,10),(804,440,19),(877,416,10),(981,269,20),(1040,450,9)]:
  if 168<v<795:
   road(f'RD_EW_WEST_{v}',[(left,v),(806,v)],width);road(f'RD_EW_EAST_{v}',[(997,v),(1339,v)],width)
  else:road(f'RD_EW_{v}',[(left,v),(997 if v==93 else 1339,v)],width)
 road('RD_LAKE_NORTH_CONNECTOR',[(427,184),(440,164),(451,151)],12)
 road('RD_LAKE_SOUTH_CONNECTOR',[(419,877),(438,845),(440,804)],10)
 road('RD_SOUTH_WATERFRONT_CONNECTOR',[(280,925),(286,955),(302,979),(370,981)],12)
 # West residential edge follows the shoreline boulevard, with clear green separation.
 road('RD_WEST_RESIDENTIAL',[(511,270),(522,367),(527,452),(540,581),(536,692),(493,804)],10)
 for v0,v1 in [(0,151),(804,1088)]:road('RD_CIVIC_AXIS_'+str(v0),[(895,v0),(895,v1)],11)
 # Outer eastern highway and edge transitions, never through the park or shore.
 road('RD_EAST_EXPRESS_N',[(1372,-100),(1372,390),(1376,760),(1376,1188)],10)
 road('RD_EAST_EXPRESS_S',[(1384,-100),(1384,390),(1388,760),(1388,1188)],10)
 for v in [151,581,981]:
  road(f'RD_HIGHWAY_LINK_{v}',[(1339,v),(1420,v)],12)
  for off in [-1,1]:road(f'RD_RAMP_{v}_{off}',[(1342,v),(1358,v+off*20),(1368,v+off*60),(1372,v+off*110)],6)
 # Landmark roundabouts at the same large grid junctions.
 for u in [724,997]:
  for v in [151,581,804,981]:
   x,y,z=world(u,v);circle=Point(x,z)
   s.surface(circle.buffer(17),.112,'asphalt',3);s.surface(circle.buffer(7.3),.13,'verge',3)
   s.surface(circle.buffer(8.3).difference(circle.buffer(7.3)),.14,'sidewalk',3)
 # Rectangular central park, its internal organization deliberately organic.
 s.surface(park.buffer(-4).boundary.buffer(2.6),.137,'path',4,'REG_PARK')
 pondpx=[(865,229),(885,225),(895,250),(928,270),(938,298),(921,320),(918,347),(948,365),(950,392),(930,409),(908,392),(883,391),(855,397),(839,380),(840,358),(859,342),(869,318),(857,295),(856,269)]
 pond=Polygon(PX(catmull(pondpx,8,True))).buffer(0)
 s.surface(pond.buffer(3).difference(pond),.135,'wet_shore',4,'REG_PARK');s.surface(pond,.15,'pond_water',4,'REG_PARK');s.waterPolygons.append(list(pond.exterior.coords))
 terrain_holes=unary_union([lake,pond,river_water])
 for u,v,w,d,mat,y,reg in [(725,544,9000,7500,'forest_floor',-.12,'REG_GREENBELT'),(916,536,900,1070,'grass',0,'REG_CITY'),(267,528,535,1010,'grass',0,'REG_WATERFRONT')]:
  a=world(u-w/2,v-d/2);b=world(u+w/2,v+d/2);s.surface(sbox(a[0],a[2],b[0],b[2]).difference(terrain_holes),y,mat,1,reg)
 s.surface(park.difference(pond),.115,'grass',4,'REG_PARK')
 park_paths=[('west_wander',[(835,192),(844,230),(832,270),(845,312),(833,346),(839,392),(860,421),(848,470),(836,515),(858,556),(842,607),(839,652),(850,703),(845,759)]),('east_wander',[(953,189),(935,218),(952,253),(946,307),(963,342),(945,384),(949,427),(964,470),(948,514),(952,556),(941,603),(958,657),(943,701),(952,755)]),('central_south',[(896,410),(917,434),(919,458),(910,483),(885,525),(898,554),(919,574),(918,607),(897,630),(909,677),(917,721),(925,750),(926,783)]),('north_garden',[(822,201),(857,185),(887,204),(915,182),(972,206)])]
 for name,pts in park_paths:s.path('PATH_PARK_'+name,pts,4.2,'path',4,smooth=True,y=.18,region='REG_PARK')
 for v in [194,275,367,452,581,691,779]:
  if v in [275,367]:
   pts=[(810,v),(834,v-5),(854,v+12)] if v==275 else [(813,v),(846,v-12),(886,v+1),(918,v+5),(978,v)]
  elif v==581:pts=[(810,581),(848,573),(875,572),(897,560),(920,573),(945,587),(988,581)]
  elif v==779:pts=[(810,790),(850,790),(896,790),(945,790),(988,790)]
  else:pts=[(810,v),(845,v-8),(897,v),(945,v+6),(988,v)]
  s.path('PATH_PARK_CROSS_'+str(v),pts,5.5,'path',4,smooth=True,y=.19,region='REG_PARK')
 for u,v,r in [(897,445,15),(897,581,19),(912,371,10),(891,190,9)]:
  x,_,z=world(u,v);s.surface(Point(x,z).buffer(r*1.5),.21,'plaza',4,'REG_PARK')
 # Lawns have soft outlines and protected open centers as seen in the reference.
 lawns=[]
 for u,v,rx,rz in [(899,491,45,57),(902,665,44,47),(858,313,21,22)]:
  pts=[(u+rx*math.cos(t)*(1+.08*math.sin(3*t)),v+rz*math.sin(t)) for t in np.linspace(0,2*math.pi,40,endpoint=False)]
  pol=Polygon(PX(pts));lawns.append(pol);s.surface(pol,.16,'lawn',4,'REG_PARK')
 # Bridge at the pond narrows; its deck connects the east-west park path.
 bridge=sbox(*[world(876,364)[0],world(876,364)[2],world(908,374)[0],world(908,374)[2]])
 s.surface(bridge,.34,'path',4,'REG_PARK');s.walkSurfaces.append(dict(bounds=list(bridge.bounds),height=.34))
 # District material / use records; no painted planning labels in finished scene.
 regions=[dict(id='REG_LAKE',name='Westmere Lake',pixels=[35,72,510,901],intent='Waterfront circuit, two principal wooded islands and a smaller islet'),dict(id='REG_RESIDENTIAL',name='Lakeside Quarter',pixels=[494,165,800,797],intent='Detached and courtyard housing between the water and park'),dict(id='REG_PARK',name='Grand Park',pixels=list(PARK),intent='Long wooded park with pond, lawns and aligned entrances'),dict(id='REG_DOWNTOWN',name='Eastbank Centre',pixels=[1008,166,1329,798],intent='Concentrated tower groups mixed with mid-rise blocks'),dict(id='REG_NORTH',name='Northfields',pixels=[493,0,1329,141],intent='Sports campus, schools and organized housing'),dict(id='REG_SOUTH',name='Southgate',pixels=[455,818,1330,1088],intent='Residential, civic and transport neighborhoods')]
 # Playfield surfaces establish north and south anchors before building placement.
 def field(u,v,w,d,kind,st=5):
  s.rect(u,v,w+6,d+6,'sidewalk',st,y=.12,region='REG_SPORTS');s.rect(u,v,w,d,'sports_turf' if kind=='soccer' else 'sports_blue',st,y=.14,region='REG_SPORTS')
  x,_,z=world(u,v);pw,pd=w*1.5,d*1.5
  outline=sbox(x-pw/2+1,z-pd/2+1,x+pw/2-1,z+pd/2-1)
  s.surface(outline.boundary.buffer(.10),.151,'road_white',st,'REG_SPORTS');s.surface(LineString([(x-pw/2,z),(x+pw/2,z)]).buffer(.1),.152,'road_white',st,'REG_SPORTS')
  if kind=='soccer':
   s.surface(Point(x,z).buffer(min(pw,pd)*.14).boundary.buffer(.1),.152,'road_white',st,'REG_SPORTS')
   for zz in [z-pd/2+pd*.12,z+pd/2-pd*.12]:s.surface(sbox(x-pw*.3,zz-pd*.12,x+pw*.3,zz+pd*.12).boundary.buffer(.1),.152,'road_white',st,'REG_SPORTS')
 field(1118,82,35,63,'soccer')
 x,_,z=world(1118,82);track=LineString([(x,z-25),(x,z+25)]).buffer(32,resolution=24)
 s.surface(track.difference(track.buffer(-8)),.156,'sports_red',5,'REG_SPORTS')
 for inset in [1.5,3,4.5,6]:s.surface(track.buffer(-inset).boundary.buffer(.075),.166,'road_white',5,'REG_SPORTS')
 for u in [1161,1183]:field(u,72,14,27,'tennis')
 field(1172,115,25,14,'basketball');field(848,931,52,44,'soccer');field(664,845,33,23,'basketball')
 sportmask=unary_union([sbox(world(u0,v0)[0],world(u0,v0)[2],world(u1,v1)[0],world(u1,v1)[2]) for u0,v0,u1,v1 in [(1095,43,1198,137),(818,905,878,958),(642,828,686,863)]])
 # Shared district envelopes and parcel grid. Values remain tied to the image.
 cells=[]
 xs=[486,597,724,806,895,997,1090,1207,1339];ys=[0,36,93,151,275,367,452,581,691,804,877,981,1088]
 for ix in range(len(xs)-1):
  for iz in range(len(ys)-1):
   u0,u1=xs[ix],xs[ix+1];v0,v1=ys[iz],ys[iz+1]
   if 806<=u0<997 and 151<=v0<804:continue
   if v0<151 and u0>=1090:continue
   if v0==877 and u0>=1090:continue
   a0=world(u0+10,v0+9);b0=world(u1-10,v1-9);poly=sbox(a0[0],a0[2],b0[0],b0[2])
   if lake.buffer(58).covers(poly):continue
   region='REG_NORTH' if v1<=151 else 'REG_SOUTH' if v0>=804 else 'REG_DOWNTOWN' if u0>=997 else 'REG_RESIDENTIAL'
   cells.append((u0+10,v0+9,u1-10,v1-9,region))
   s.parcels.append(dict(id=f'BLOCK_{ix}_{iz}',polygon=list(poly.exterior.coords),region=region,frontage='rectangular streets on all four sides',setback=4.5))
 # Streets excluded from park and shoreline are authoritative for all later placement.
 roadmask=unary_union(road_reservations);placed=[]
 pedestrian_reservations=unary_union([LineString(PX([((u0+u1)/2,v0-8),((u0+u1)/2,v1+8)])).buffer(2.5) if reg!='REG_DOWNTOWN' else LineString(PX([(u0-7,v0+33),(u1+7,v0+33)])).buffer(2.7) for u0,v0,u1,v1,reg in cells])
 def place(proto,u,v,ry=0,reg='REG_RESIDENTIAL',st=6,scale=1):
  if proto not in s.prototypes:return None
  pr=s.prototypes[proto];col=pr.get('collision');p=world(u,v,.16)
  if col:
   hx,hz=col[0]*scale,col[1]*scale
   if abs(math.sin(ry))>.7:hx,hz=hz,hx
   pol=sbox(p[0]-hx,p[2]-hz,p[0]+hx,p[2]+hz)
   if pol.intersects(roadmask) or pol.intersects(sportmask) or pol.intersects(lake.buffer(42)) or (reg in ['REG_RESIDENTIAL','REG_DOWNTOWN','REG_SOUTH','REG_NORTH','REG_COMMERCIAL'] and pol.intersects(pedestrian_reservations)) or (reg!='REG_PARK' and pol.intersects(park.buffer(4))):return None
   if any(pol.intersects(pp.buffer(1)) for pp in placed):return None
   placed.append(pol);s.buildings.append(dict(id=f'BLD_{len(s.buildings):04d}',prototype=proto,footprint=list(pol.exterior.coords),region=reg,nonEnterable=True,frontageDirection=[math.sin(ry),math.cos(ry)],entrance=[p[0]+math.sin(ry)*hz,p[2]+math.cos(ry)*hz]))
   s.surface(pol.buffer(8 if reg in ['REG_PARK','REG_CIVIC','REG_TRANSPORT'] else 2.3),.132,'plaza' if reg in ['REG_DOWNTOWN','REG_CIVIC','REG_TRANSPORT','REG_COMMERCIAL','REG_PARK'] else 'sidewalk',st,reg)
  return s.at(proto,u,v,y=.16,rotation=ry,scale=[scale]*3,region=reg,stage=st)
 if stage>=6:
  from architecture import build_architecture
  build_architecture(s)
  # Low housing near the lake; terraced streets and mid-rise courts toward the park.
  for ci,(u0,v0,u1,v1,reg) in enumerate(cells):
   cr=random.Random(1900+ci)
   if reg=='REG_DOWNTOWN':continue
   if reg=='REG_SOUTH' and 900<u0<997 and 804<v0<877:
    place('city_hall',946,842,reg='REG_CIVIC');continue
   if 877<v0<981 and 810<u0<880:continue
   if 625<u0<730 and 810<v0<878:continue
   # Preserve a civic campus at the lake approach north of the park.
   if u0<600 and 150<v0<275:
    place('school',548,204,reg='REG_CIVIC');s.rect(548,244,56,23,'plaza',6,y=.14,region='REG_CIVIC');continue
   if 724<u0<807 and v0>452 and v1<582:
    place('library',767,506,reg='REG_CIVIC');continue
   dense=(734<=u0<807) or (reg=='REG_SOUTH' and u0>805) or (450<v0<582) or (v0>=804 and ci%3==0)
   if dense:
    spanx=u1-u0;spany=v1-v0
    for row,v in enumerate(np.arange(v0+12,v1-8,27)):
     for col,u in enumerate(np.arange(u0+14,u1-10,29)):
      family=f'apartment_{1+(ci+row*3+col)%8:02d}'
      place(family,float(u),float(v),ry=math.pi if row%2 else 0,reg=reg)
   else:
    # Paired frontages frame landscaped courtyards; every local lane joins a grid street.
    for row,v in enumerate(np.arange(v0+9,v1-6,22)):
     for col,u in enumerate(np.arange(u0+7,u1-5,14)):
      family=f'house_{cr.randint(1,12):02d}' if u0<610 or cr.random()<.68 else f'townhouse_{cr.randint(1,4):02d}'
      place(family,float(u),float(v),ry=0 if row%2==0 else math.pi,reg=reg)
    # Narrow connecting residential roads double as access to the paired rows.
    for v in np.arange(v0+20,v1-8,44):road(f'RD_LOCAL_{ci}_{int(v)}',[(u0-10,float(v)),(u1+10,float(v))],5.5,st=9)
   # A pedestrian cut-through and pocket green belong to each block.
   s.path(f'PATH_BLOCK_{ci}',[((u0+u1)/2,v0-8),((u0+u1)/2,v1+8)],2.2,'path',9,y=.13)
  # Cultural buildings bracket the long park. Their approaches align with streets.
  place('museum',894,758,reg='REG_PARK',scale=1.4)
  place('sports_hall',1241,80,reg='REG_CIVIC',scale=1.2);place('school',1290,92,reg='REG_CIVIC');place('school',1040,83,reg='REG_CIVIC')
  place('rail_station',1155,947,reg='REG_TRANSPORT',scale=1.3)
  place('commercial_01',1120,901,reg='REG_TRANSPORT');place('commercial_02',1176,902,reg='REG_TRANSPORT')
  place('library',921,1038,reg='REG_CIVIC');place('commercial_03',1024,935,reg='REG_COMMERCIAL')
  # South park / education campus fills the urban structure below Grand Park.
  place('school',866,850,reg='REG_CIVIC');place('apartment_05',945,931,reg='REG_SOUTH')
  for u,v in [(1280,853),(1281,916),(1050,855),(1239,1035),(1040,1037)]:place('commercial_0'+str(1+int(u)%4),u,v,reg='REG_COMMERCIAL')
  # Small retail gateways are grounded in the street network.
  for u,v in [(561,410),(679,744),(773,316),(770,633),(556,837)]:place('commercial_01',u,v,reg='REG_COMMERCIAL')
 if stage>=7:
  place('hotel',1282,520,reg='REG_DOWNTOWN',st=7)
  for ci,(u0,v0,u1,v1,reg) in enumerate(cells):
   if reg!='REG_DOWNTOWN':continue
   cr=random.Random(631+ci);midu=(u0+u1)/2;midv=(v0+v1)/2
   s.rect(midu,midv,u1-u0,v1-v0,'grass',7,y=.12,region=reg)
   for row,v in enumerate(np.arange(v0+17,v1-10,32)):
    for col,u in enumerate(np.arange(u0+16,u1-10,32)):
     # Most towers stay in the two inner avenue strips, centered on the park.
     is_tower=u<1200 and 175<v<783 and cr.random()<(.82 if u<1110 else .66)
     proto=f'tower_{1+(ci*3+row*2+col)%10:02d}' if is_tower else f'apartment_{1+(ci+row+col)%8:02d}'
     place(proto,float(u),float(v),ry=math.pi*(row%2),reg=reg,st=7)
   s.path(f'PATH_DOWNTOWN_COURT_{ci}',[(u0-7,v0+33),(u1+7,v0+33)],3.6,'path',9,y=.145)
 # Geometry-led transport district: parallel tracks curve away at the southeast.
 for i in range(5):
  pts=[(1093,931+i*5),(1220,931+i*5),(1310,915+i*5),(1418,866+i*5),(1540,826+i*5)]
  line=LineString(PX(catmull(pts,10)))
  s.surface(line.buffer(2.1),.14,'ballast',9,'REG_TRANSPORT')
  for side in [-.72,.72]:s.surface(line.parallel_offset(abs(side),'left' if side>0 else 'right').buffer(.065),.19,'track_rail',9,'REG_TRANSPORT')
  for dist in np.arange(0,line.length,2.2):
   p=line.interpolate(dist);q=line.interpolate(min(dist+1,line.length));dx=q.x-p.x;dz=q.y-p.y;ll=math.hypot(dx,dz) or 1
   s.surface(LineString([(p.x-dz/ll*1.3,p.y+dx/ll*1.3),(p.x+dz/ll*1.3,p.y-dx/ll*1.3)]).buffer(.14),.18,'ballast',9,'REG_TRANSPORT')
 # Marina, beaches, viewpoints and lakeside access are complete functional groups.
 s.rect(105,444,8,72,'path',9,y=.22,region='REG_WATERFRONT')
 for v in [420,438,455,471]:
  s.rect(129,v,48,2.8,'path',9,y=.3,region='REG_WATERFRONT')
  a=world(104,v-1.4);b=world(153,v+1.4);s.walkSurfaces.append(dict(bounds=[a[0],a[2],b[0],b[2]],height=.3))
 for j,(u,v) in enumerate([(106,762),(502,690),(181,783),(389,151),(448,384)]):
  x,_,z=world(u,v);q=lake_walk.interpolate(lake_walk.project(Point(x,z)));shore=lake.exterior.interpolate(lake.exterior.project(q));dx=q.x-shore.x;dz=q.y-shore.y;ll=math.hypot(dx,dz) or 1;cx=q.x+dx/ll*8;cz=q.y+dz/ll*8
  s.surface(Point(cx,cz).buffer(7),.14,'plaza',9,'REG_WATERFRONT')
  s.path('PATH_VIEW_'+str(j),[(q.x/1.5+725,q.y/1.5+544),(cx/1.5+725,cz/1.5+544)],3,'path',9,y=.16)
 from fix_connections import build_connections
 connection_report=build_connections(s,pond,lake)
 (ROOT/'connection_validation.json').write_text(json.dumps(connection_report,indent=2),encoding='utf8')
 # Shared decoration prototypes only added after the massing checkpoint.
 treepoints=[]
 if stage>=8:
  from landscape_assets import build_landscape_assets
  build_landscape_assets(s)
  roadmask=unary_union(road_reservations)
  civic_clearances=[Polygon(b['footprint']).buffer(12) for b in s.buildings if b['region'] in ['REG_PARK','REG_CIVIC','REG_TRANSPORT']]
  buildmask=unary_union([unary_union(placed).buffer(1.5)]+civic_clearances) if placed else Polygon()
  pathmask=unary_union([LineString(p['points']).buffer(p['width']/2+1.8) for p in s.paths if not p['id'].startswith('RD_')])
  # Explicit regular avenue planting alternates with irregular woodland.
  def tree(u,v,region='REG_GREENBELT',small=False,check=True):
   xx,_,zz=world(u,v);pt=Point(xx,zz)
   if check and (water.contains(pt) or river_water.buffer(1).contains(pt) or sportmask.buffer(3).contains(pt) or pond.buffer(2).contains(pt) or roadmask.contains(pt) or buildmask.contains(pt) or pathmask.contains(pt)):return
   if any((xx-x)**2+(zz-z)**2<25 for x,z in treepoints):return
   species=rng.choices(['tree_oak','tree_maple','tree_birch','tree_poplar','tree_pine'],[38,30,15,7,10])[0]
   if small:species=rng.choice(['tree_oak_young','tree_maple_young'])
   scale=rng.uniform(.9,1.22) if small else rng.uniform(1.45,1.95) if region in ['REG_GREENBELT','REG_PARK','REG_WATERFRONT','REG_ISLAND'] else rng.uniform(1.05,1.38)
   s.at(species,u,v,y=.16,rotation=rng.random()*6.283,scale=[scale]*3,region=region,stage=8);treepoints.append((xx,zz))
  for u in [713,735,794,815,986,1009,1079,1101,1196,1218,1328]:
   for v in np.arange(15,1080,13):tree(u,float(v),region='REG_STREET_TREES',small=u not in [815,986])
  for v in [139,163,569,593,792,816,969,993]:
   for u in np.arange(482,1334,14):tree(float(u),v,region='REG_STREET_TREES',small=True)
  # Shore green buffer, islands and entire wooded west bank.
  for offset in [6,25,52]:
   ln=LineString(lake.buffer(offset).exterior.coords)
   for d in np.arange(0,ln.length,12 if offset!=25 else 20):
    p=ln.interpolate(d);tree(p.x/1.5+725+rng.uniform(-2,2),p.y/1.5+544+rng.uniform(-2,2),region='REG_WATERFRONT')
  for isl in islands:
   lo=isl.bounds
   for k in range(int(isl.area/50)):
    xx=rng.uniform(lo[0],lo[2]);zz=rng.uniform(lo[1],lo[3])
    if isl.buffer(-2).contains(Point(xx,zz)):tree(xx/1.5+725,zz/1.5+544,region='REG_ISLAND',check=False)
  for i in range(20000):
   u=rng.uniform(-80,1510);v=rng.uniform(-60,1145);xx,_,zz=world(u,v);p=Point(xx,zz)
   isbelt=((u<470 and not lake.buffer(48).contains(p)) or u>1405 or v<5 or v>1075)
   if isbelt:tree(u,v)
  for i in range(3500):
   u=rng.uniform(821,975);v=rng.uniform(174,788);pt=Point(*[world(u,v)[j] for j in [0,2]])
   if not any(l.buffer(5).contains(pt) for l in lawns):tree(u,v,region='REG_PARK')
  for ci,(u0,v0,u1,v1,reg) in enumerate(cells):
   for k in range(max(8,int((u1-u0)*(v1-v0)/120))):tree(rng.uniform(u0,u1),rng.uniform(v0,v1),region=reg,small=reg=='REG_DOWNTOWN')
  # Street furniture stays outside the 3.2m clear sidewalk band.
  for rd in road_records:
   line=LineString(rd['points'])
   for d in np.arange(18,line.length-10,48):
    p=line.interpolate(d);q=line.interpolate(d+1);dx=q.x-p.x;dz=q.y-p.y;ll=math.hypot(dx,dz) or 1
    off=rd['width']/2+1
    x=p.x-dz/ll*off;z=p.y+dx/ll*off
    s.add('street_lamp',[x,.12,z],rotation=math.atan2(dx,dz),region='REG_STREET_PROPS',stage=8)
   # Parked cars belong to outer curb lanes, never random lawns.
   if rd['width']<18 and 'EXPRESS' not in rd['id']:
    for d in np.arange(32,line.length-25,34):
     if rng.random()<.58:
      p=line.interpolate(d);q=line.interpolate(d+1);dx=q.x-p.x;dz=q.y-p.y;ll=math.hypot(dx,dz) or 1;off=rd['width']/2-1.5
      s.add(rng.choice(['car_sedan','car_suv','delivery_van']),[p.x-dz/ll*off,.13,p.y+dx/ll*off],rotation=math.atan2(dx,dz),region='REG_VEHICLES',stage=8)
  for u in [724,806,997,1090,1207,1339]:
   for v in [151,275,367,452,581,691,804,981]:
    if u==806 and 168<v<795:continue
    s.at('traffic_light',u+7,v+6,region='REG_STREET_PROPS',stage=8)
    # Four zebra strips terminate at connected sidewalks.
    for side in [-1,1]:
     for j in range(6):s.rect(u-3+j*1.2,v+side*10,.65,3.6,'road_white',9,y=.117)
  for u,v in [(710,165),(1011,565),(791,814),(610,591),(1080,793),(733,961)]:s.at('bus_shelter',u,v,region='REG_TRANSIT',stage=8)
  for pth in [lake_walk,LineString(PX([(833,195),(837,755)])),LineString(PX([(961,194),(960,755)]))]:
   for dd in np.arange(12,pth.length,64):
    p=pth.interpolate(dd);q=pth.interpolate(dd+1);dx=q.x-p.x;dz=q.y-p.y;ll=math.hypot(dx,dz) or 1
    pos=[p.x-dz/ll*4.3,.14,p.y+dx/ll*4.3];s.add('bench',pos,rotation=math.atan2(-dx,-dz),region='REG_PARK_PROPS',stage=8)
    s.add('trash_bin',[pos[0]+2,.14,pos[2]+1],region='REG_PARK_PROPS',stage=8)
  for u,v in [(897,445),(897,581)]:s.at('fountain',u,v,region='REG_PARK_PROPS',stage=8)
  for u,v in [(843,418),(952,514),(856,688),(402,780),(360,136)]:s.at('park_pavilion',u,v,region='REG_PARK_PROPS',stage=8)
  for u,v in [(949,253),(838,618)]:
   s.rect(u,v,25,23,'shore_sand',8,y=.16,region='REG_PARK');s.at('playground_swing',u-6,v,region='REG_PARK_PROPS',stage=8);s.at('playground_slide',u+7,v+3,region='REG_PARK_PROPS',stage=8)
  for u,v in [(949,616),(842,216),(852,641),(370,137),(471,718)]:
   for j in range(4):s.at('picnic_table',u+(j%2)*6,v+(j//2)*5,region='REG_PARK_PROPS',stage=8)
  for v in [419,438,455,471]:
   for u in [118,132,145]:s.at('motorboat' if int(u)%2 else 'sailboat',u,v+4,y=.10,rotation=math.pi/2,region='REG_MARINA',stage=8)
  for u,v in [(285,257),(358,462),(289,800)]:s.at('sailboat',u,v,y=.05,rotation=.4,region='REG_LAKE',stage=8)
  for u,v in [(1118,54),(1118,110),(848,912),(848,950)]:s.at('soccer_goal',u,v,rotation=math.pi if v in [110,950] else 0,region='REG_SPORTS',stage=8)
  for u in [1161,1183]:s.at('tennis_net',u,72,region='REG_SPORTS',stage=8)
  for u,v in [(1161,115),(1183,115),(650,845),(678,845)]:s.at('basketball_hoop',u,v,rotation=math.pi/2,region='REG_SPORTS',stage=8)
  for u,v in [(825,803),(981,155),(526,699),(1110,954),(1089,152)]:
   s.at('park_sign',u,v,region='REG_WAYFINDING',stage=8);s.at('bike_rack',u+3,v,region='REG_WAYFINDING',stage=8)
   for j in range(3):s.at('bicycle',u+1+j*1.4,v+2,rotation=math.pi/2,region='REG_WAYFINDING',stage=8)
  for u,v in [(879,196),(905,196),(883,737),(912,737),(843,566),(952,557)]:
   for i in range(4):s.at('flower_planter',u+i*3,v,region='REG_PARK_PROPS',stage=8)
 # Secondary lake-to-city connections complete public access at multiple levels.
 for pts in [[(468,159),(484,151)],[(507,371),(524,367),(595,367)],[(520,582),(595,581)],[(523,692),(597,691)],[(415,869),(486,877)],[(298,956),(302,981)]]:s.path('PATH_WATERFRONT_LINK_'+str(pts[0]),pts,4,'path',9,y=.16)
 # Southern river and the outer greenbelt soften the end of the city.
 s.surface(river_water,.045,'pond_water',2,'REG_GREENBELT')
 if stage>=9:
  from dress_neighborhoods import dress_neighborhoods
  dressing_report=dress_neighborhoods(s,roadmask,placed,lake,pond,park)
  (ROOT/'neighborhood_validation.json').write_text(json.dumps(dressing_report,indent=2),encoding='utf8')
  from tree_anchoring import anchor_trees
  initial_anchoring_report=anchor_trees(s)
  from clear_routes import clear_routes
  clear_report=clear_routes(s,lake,pond,placed,roadmask,park)
  (ROOT/'route_clearance_corrections.json').write_text(json.dumps(clear_report,indent=2),encoding='utf8')
 s.landmarks=[dict(id='lake',name='Westmere Lake',position=world(252,483,280),lookAt=world(270,485),walkPosition=[-324.902,1.85,217.816]),dict(id='park',name='Grand Park',position=world(894,528,370),lookAt=world(894,480),walkPosition=world(895,560,1.85)),dict(id='downtown',name='Eastbank Centre',position=world(1208,676,285),lookAt=world(1080,425,45),walkPosition=world(1010,578,1.85)),dict(id='sports',name='Northfields Sports',position=world(1170,180,210),lookAt=world(1160,80),walkPosition=world(1141,138,1.85)),dict(id='station',name='Southgate Station',position=world(1240,1063,210),lookAt=world(1178,943),walkPosition=world(1170,978,1.85))]
 s.cameras=[dict(id='overview',name='City overview',position=[210,1800,1550],target=[0,0,0]),dict(id='top',name='Reference top-down',position=[0,2400,0],target=[0,0,0]),dict(id='lake_approach',name='Lakeside promenade',position=[-324.902,1.85,217.816],target=world(495,638,2)),dict(id='park_lawn',name='Grand Park lawn',position=world(890,531,1.85),target=world(904,454,2)),dict(id='downtown_street',name='Eastbank boulevard',position=world(1010,573,1.85),target=world(1010,356,25)),dict(id='residential',name='Lakeside streets',position=world(605,363,1.85),target=world(684,367,4)),dict(id='sports',name='Northfields campus',position=world(1117,145,26),target=world(1133,80,0)),dict(id='station',name='Southgate arrival',position=world(1150,977,12),target=world(1170,946,6)),dict(id='park_reverse',name='Park southern entrance',position=world(894,790,1.85),target=world(894,767,5))]
 if stage>=8:
  from tree_anchoring import anchor_trees
  anchoring_report=anchor_trees(s)
  if stage>=9:
   anchoring_report['previousDatumAboveGroundRangeM']=initial_anchoring_report['previousDatumAboveGroundRangeM']
   anchoring_report['initialInstanceYDeltaRangeM']=initial_anchoring_report['instanceYDeltaRangeM']
   anchoring_report['clearanceOrder']='Grounded before clearance; resampled after any horizontal relocations.'
  (ROOT/'tree_grounding_validation.json').write_text(json.dumps(anchoring_report,indent=2),encoding='utf8')
  assert not anchoring_report['unresolvedIds'], 'A tree has no rendered ground support'
  assert anchoring_report['maximumStructuralRootAboveSoilM']<0, 'A structural tree root remains above soil'
 s.flush()
 spec=dict(name='Westmere — Lake City',units='metres',reference='references/target_layout.png',referenceSize=[1450,1088],referenceActualSize=[1448,1086],referenceNormalization='Working coordinates use1450x1088 for source1448x1086; extent difference below0.2percent.',worldSize=[2175,1632],axes='X east, Y up, Z south',pixelToMetre=1.5,origin='Reference pixel (725,544)',groundDatum=0,regions=regions,park=dict(pixelBounds=PARK,dimensionsMetres=[249,940.5],gridEquivalent='3-4 short blocks wide and 8-12 short blocks long'),lake=dict(waterAreaM2=round(water.area),waterMapPercent=round(water.area/(2175*1632)*100,2),districtAreaPercent=round(lake.buffer(36).area/(2175*1632)*100,2),shorelinePixels=LAKE,walkLoopLengthM=round(lake_walk.length),cycleLoopLengthM=round(lake_cycle.length),islands=3),streets=road_records,parcels=s.parcels,buildings=s.buildings,navigation=dict(eyeHeight=1.72,radius=.32,bodyHeight=1.78,stepHeight=.45,walkingSpeed=3.9,runningSpeed=11.5,nonEnterableBuildings=True,staticEnvironment=True),explicitRequirements=['Reference governs layout at ten top-down checkpoints','Complete lake loop','Housing between lake and park','Tall skyline concentrated east of park','Northern sports and southeastern station','Local desktop exploration'],inferredChoices=['Reference pixel scale 1.5 metres','Static maintained late-summer daylight','Closed building interiors','2 large wooded islands and one small islet'],acceptance=dict(checkpointCount=10,minimumVisualPasses=3,geometryLossless=True,allDistrictsConnected=True))
 spec['vegetationGrounding']=dict(support='Actual rendered soil, planting, plaza and path triangles',collarEmbedDepthM=.06,structuralRoots='Below soil',placement='Preserve horizontal coordinates, scale and rotation; sample Y after local clearance')
 (ROOT/'scene_spec.json').write_text(json.dumps(spec,indent=2),encoding='utf8')
 (ROOT/'animation_manifest.json').write_text(json.dumps(dict(animatedSystems=[],reason='No animation requested. Architecture, water optical detail, foliage and vehicles are static.'),indent=2),encoding='utf8')
 (ROOT/'region_graph.json').write_text(json.dumps(dict(regions=regions,connections=[['REG_LAKE','REG_RESIDENTIAL','waterfront links'],['REG_RESIDENTIAL','REG_PARK','six aligned entrances'],['REG_PARK','REG_DOWNTOWN','park boulevards'],['REG_NORTH','REG_DOWNTOWN','north-south avenues'],['REG_SOUTH','REG_RESIDENTIAL','south grid'],['REG_SOUTH','REG_DOWNTOWN','Southgate transport boulevard']],paths=s.paths),indent=2),encoding='utf8')
 result=export(s,stage)
 # Add island exclusions without altering the binary or geometric inventory.
 result['waterHolePolygons']=s.waterHolePolygons
 (ROOT/'viewer/public/assets/city.json').write_text(json.dumps(result,separators=(',',':')),encoding='utf8')
 return s,result

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--stage',type=int,default=10);a=ap.parse_args();build(a.stage)



