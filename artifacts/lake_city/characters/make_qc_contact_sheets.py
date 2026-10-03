"""Arrange real Blender QC renders without changing their contents."""
from PIL import Image,ImageDraw
from pathlib import Path
root=Path(__file__).resolve().parent
def sheet(paths,path,columns,tile=350):
    canvas=Image.new('RGB',(columns*tile,((len(paths)+columns-1)//columns)*(tile+26)),(26,30,37))
    draw=ImageDraw.Draw(canvas)
    for i,p in enumerate(paths):
        im=Image.open(p).convert('RGB');im.thumbnail((tile,tile))
        x=(i%columns)*tile;y=(i//columns)*(tile+26)
        canvas.paste(im,(x+(tile-im.width)//2,y+(tile-im.height)//2))
        draw.text((x+8,y+tile+5),p.stem,fill='white')
    canvas.save(path)
for action in ['idle','walk','run','jump']:
    sheet(sorted((root/'CharacterBase_animation_qc'/action).glob('*.png')),root/f'qc_{action}.png',5)
sheet(sorted((root/'CharacterBase_qc').glob('*.png')),root/'qc_outfit.png',4)
