"""Compose reproducible visual evidence from existing renders and reference.

This utility only resizes/composes actual images and draws analytical labels or
layout overlays. It does not generate scene imagery or modify the reference.
Run again after rendering additional construction checkpoints or review passes.
"""
from pathlib import Path
import argparse
import json
import shutil
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
STAGES = {
    1: 'Map boundaries', 2: 'Lake and complete waterfront loop',
    3: 'Main road grid', 4: 'Grand Park structure', 5: 'District boundaries',
    6: 'Main buildings', 7: 'Downtown skyline', 8: 'Vegetation and public realm',
    9: 'Secondary roads and pedestrian paths', 10: 'Final composition review',
}
CAMERAS = [
    ('top', 'Reference-aligned top-down'), ('overview', 'City overview'),
    ('lake_approach', 'Lakeside promenade'), ('park_lawn', 'Grand Park lawn'),
    ('downtown_street', 'Eastbank boulevard'), ('residential', 'Lakeside streets'),
    ('sports', 'Northfields campus'), ('station', 'Southgate arrival'),
    ('park_reverse', 'Park southern entrance'),
]
REGION_COLORS = {
    'REG_LAKE': '#3883a1', 'REG_RESIDENTIAL': '#d1ad78', 'REG_PARK': '#74a873',
    'REG_DOWNTOWN': '#ad8194', 'REG_NORTH': '#b6b17a', 'REG_SOUTH': '#9dabbc',
}
BG = '#172229'
FG = '#edf2f2'
MUTED = '#a7bdc3'


def font(size=22, bold=False):
    paths = [Path('C:/Windows/Fonts') / ('segoeuib.ttf' if bold else 'segoeui.ttf'),
             Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    for p in paths:
        if p.exists(): return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


def fit(image, width, height, fill='#24343a'):
    src = image.convert('RGB')
    scale = min(width/src.width, height/src.height)
    size = (max(1, round(src.width*scale)), max(1, round(src.height*scale)))
    resized = src.resize(size, Image.Resampling.LANCZOS)
    out = Image.new('RGB', (width, height), fill)
    out.paste(resized, ((width-size[0])//2, (height-size[1])//2))
    return out


def grid_overlay(image):
    image = image.convert('RGBA')
    overlay = Image.new('RGBA', image.size)
    d = ImageDraw.Draw(overlay)
    w,h=image.size
    for i in (1,2):
        d.line([(round(w*i/3),0),(round(w*i/3),h)], fill=(255,240,166,190), width=2)
        d.line([(0,round(h*i/3)),(w,round(h*i/3))], fill=(255,240,166,190), width=2)
    for row in range(3):
        for col in range(3):
            x=round(w*col/3)+10;y=round(h*row/3)+9
            d.rounded_rectangle((x-3,y-2,x+42,y+27),4,fill=(15,27,34,210))
            d.text((x+3,y),f'{"ABC"[col]}{row+1}',font=font(19,True),fill=(255,243,192,255))
    return Image.alpha_composite(image,overlay).convert('RGB')


def comparison(reference, actual_path, out_path, title, grid=False):
    panel_w=1160;panel_h=870;gap=20;margin=24;header=106;footer=55
    ref=fit(reference,panel_w,panel_h)
    with Image.open(actual_path) as actual: render=fit(actual,panel_w,panel_h)
    if grid:ref=grid_overlay(ref);render=grid_overlay(render)
    result=Image.new('RGB',(margin*2+panel_w*2+gap,header+panel_h+footer),BG)
    d=ImageDraw.Draw(result)
    d.text((margin,15),title,font=font(28,True),fill=FG)
    d.text((margin,62),'USER REFERENCE - target layout',font=font(22,True),fill=MUTED)
    d.text((margin+panel_w+gap,62),'BLENDER RENDER - constructed environment',font=font(22,True),fill=MUTED)
    result.paste(ref,(margin,header));result.paste(render,(margin+panel_w+gap,header))
    d.text((margin,header+panel_h+14),f'West is left. North is up.  |  Actual image: {actual_path.relative_to(ROOT).as_posix()}',font=font(18),fill=MUTED)
    out_path.parent.mkdir(parents=True,exist_ok=True);result.save(out_path)
    return out_path


def semantic_map(spec,city):
    w,h=spec.get('referenceSize',[1450,1088]);margin=30;header=75;legend=315
    image=Image.new('RGB',(w+legend+margin*3,h+header+margin),BG)
    drawing=ImageDraw.Draw(image)
    drawing.text((margin,20),'WESTMERE / SEMANTIC LAYOUT',font=font(29,True),fill=FG)
    layer=Image.new('RGB',(w,h),'#52775e');d=ImageDraw.Draw(layer)
    # Region envelopes and shoreline consume the current shared specification.
    for region in spec.get('regions',[]):
        if region['id']=='REG_LAKE':continue
        if 'pixels' in region:d.rectangle(region['pixels'],fill=REGION_COLORS.get(region['id'],'#999999'),outline='#35484c',width=2)
    shoreline=spec.get('lake',{}).get('shorelinePixels',[])
    if shoreline:d.polygon([tuple(p) for p in shoreline],fill=REGION_COLORS['REG_LAKE'],outline='#c4dad3')
    scale=spec.get('pixelToMetre',1.5)
    def pix(p):return (p[0]/scale+w/2,p[1]/scale+h/2)
    for hole in city.get('waterHolePolygons',[]):
        d.polygon([pix(p) for p in hole],fill='#52775e',outline='#c4dad3')
    for street in spec.get('streets',[]):
        points=[pix(p) for p in street.get('points',[])]
        if len(points)>1:d.line(points,fill='#d6d6c9',width=max(2,round(street.get('width',6)/scale)),joint='curve')
    for path in city.get('paths',[]):
        if path.get('id','').startswith('RD_'):continue
        points=[pix(p) for p in path.get('points',[])]
        if len(points)>1:d.line(points,fill='#f1e8c5',width=max(1,round(path.get('width',2)/scale)),joint='curve')
    for building in spec.get('buildings',[]):
        if building.get('footprint'):d.polygon([pix(p) for p in building['footprint']],fill='#626975',outline='#424d58')
    for region in spec.get('regions',[]):
        if not region.get('pixels'):continue
        x0,y0,x1,y1=region['pixels'];label=region['id'].replace('REG_','')
        tx=(x0+x1)/2;ty=(y0+y1)/2
        textfont=font(19,True);bb=d.textbbox((0,0),label,font=textfont);tw=bb[2]-bb[0]
        d.rounded_rectangle((tx-tw/2-9,ty-17,tx+tw/2+9,ty+17),5,fill='#24373d')
        d.text((tx-tw/2,ty-13),label,font=textfont,fill=FG)
    d.rectangle((0,0,w-1,h-1),outline='#d7e2dc',width=3)
    image.paste(layer,(margin,header))
    lx=w+margin*2;ly=header+15
    drawing.text((lx,ly),'REGION KEY',font=font(23,True),fill=FG);ly+=53
    for region in spec.get('regions',[]):
        drawing.rectangle((lx,ly+3,lx+22,ly+25),fill=REGION_COLORS.get(region['id'],'#999999'))
        drawing.text((lx+34,ly),region['id'],font=font(17,True),fill=FG)
        drawing.text((lx+34,ly+27),region['name'],font=font(17),fill=MUTED);ly+=84
    for color,label in [('#d6d6c9','Road corridors'),('#f1e8c5','Pedestrian / cycle routes'),('#626975','Building footprints'),('#52775e','Woodland / greenbelt')]:
        drawing.rectangle((lx,ly+3,lx+22,ly+23),fill=color)
        drawing.text((lx+34,ly),label,font=font(17),fill=MUTED);ly+=42
    ly+=18
    for text in ['Shared scene_spec.json coordinates.','Analytical diagram, not a render.','Grid: X east / Z south.','Reference origin: centre.']:
        drawing.text((lx,ly),text,font=font(16),fill=MUTED);ly+=28
    target=ROOT/'semantic_layout.png';image.save(target);return target


def contact_sheet(pass_num):
    directory=ROOT/'renders'/f'pass_{pass_num}'
    paths=[directory/f'{camera}.png' for camera,_ in CAMERAS]
    available=sum(path.exists() for path in paths)
    if not available:return None
    tw,th=640,445;margin,gap,header=22,16,87
    result=Image.new('RGB',(margin*2+tw*3+gap*2,header+th*3+gap*2+margin),BG);d=ImageDraw.Draw(result)
    d.text((margin,15),f'WESTMERE / BLENDER REVIEW PASS {pass_num}',font=font(28,True),fill=FG)
    d.text((margin,53),f'{available}/9 actual camera renders present. Missing views are labelled; no imagery is substituted.',font=font(17),fill=MUTED)
    for i,((camera,label),path) in enumerate(zip(CAMERAS,paths)):
        x=margin+(i%3)*(tw+gap);y=header+(i//3)*(th+gap)
        if path.exists():
            with Image.open(path) as img: result.paste(fit(img,tw,th-44),(x,y+44))
        else:
            d.rectangle((x,y+44,x+tw,y+th),fill='#25343b')
            d.text((x+22,y+190),'NOT RENDERED YET',font=font(23,True),fill=MUTED)
        d.text((x+5,y+10),f'{i+1:02d}  {label}',font=font(20,True),fill=FG)
    output=directory/'contact_sheet.png';result.save(output)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',type=int,choices=range(1,11),help='Refresh only one checkpoint comparison; other analytical outputs still refresh.')
    args=parser.parse_args()
    reference=Image.open(ROOT/'references'/'target_layout.png').convert('RGB')
    made=[];missing=[]
    for stage in ([args.stage] if args.stage else range(1,11)):
        actual=ROOT/'renders'/f'stage_{stage:02d}_top.png'
        if actual.exists():made.append(comparison(reference,actual,ROOT/'comparisons'/f'checkpoint_{stage:02d}.png',f'CHECKPOINT {stage:02d} / {STAGES[stage]}'))
        else:missing.append(stage)
    final_candidates=[ROOT/'renders'/'revision_01'/'top.png',ROOT/'renders'/'pass_4'/'top.png',ROOT/'renders'/'pass_3'/'top.png',ROOT/'renders'/'pass_2'/'top.png',ROOT/'renders'/'pass_1'/'top.png',ROOT/'renders'/'stage_10_top.png']
    final=next((p for p in final_candidates if p.exists()),None)
    if final:made.append(comparison(reference,final,ROOT/'comparisons'/'final_reference_grid.png','FINAL COMPOSITION / matching 3 x 3 inspection cells',grid=True))
    spec_path=ROOT/'scene_spec.json';city_path=ROOT/'viewer'/'public'/'assets'/'city.json'
    if spec_path.exists():
        spec=json.loads(spec_path.read_text(encoding='utf-8-sig'));city=json.loads(city_path.read_text(encoding='utf-8-sig')) if city_path.exists() else {}
        made.append(semantic_map(spec,city))
    for pass_num in range(1,5):
        sheet=contact_sheet(pass_num)
        if sheet:made.append(sheet)
    kit=Path('C:/Users/limou/AppData/Local/Temp/lake_city_landscape_preview.png')
    if kit.exists():
        target=ROOT/'renders'/'landscape_kit.png';target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(kit,target);made.append(target)
    print(json.dumps({'created':[p.relative_to(ROOT).as_posix() for p in made],'awaiting_checkpoint_renders':missing},indent=2))


if __name__=='__main__':main()
