from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import random, hashlib
W,H=1080,1350
im=Image.new("RGB",(W,H),(17,13,23))
d=ImageDraw.Draw(im)
for y in range(H):
    t=y/H
    d.line((0,y,W,y),fill=(int(14+35*t),int(17-9*t),int(27-9*t)))
random.seed(20261117)
for i in range(160):
    x=random.randint(30,1050);y=random.randint(160,700)
    r=random.randint(2,7)
    d.ellipse((x-r,y-r,x+r,y+r),fill=(51,110,155))
for i in range(8):
    x=130+i*115
    d.line((x,300,x+30,500),fill=(26,125,188),width=7)
    d.line((x+30,500,x+70,410),fill=(26,125,188),width=7)
d.ellipse((290,170,800,660),outline=(237,56,57),width=24)
d.ellipse((380,260,710,570),outline=(39,163,235),width=16)
d.line((540,340,540,465),fill=(255,221,50),width=32)
d.ellipse((524,495,558,529),fill=(255,221,50))
d.polygon([(0,0),(900,0),(820,112),(0,125)],fill=(173,17,37))
font='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def f(n): return ImageFont.truetype(font,n)
d.text((38,22),'HABERLER KKTC',font=f(61),fill='white')
d.polygon([(0,725),(1080,675),(1080,760),(0,810)],fill=(174,12,35))
d.text((40,800),'ABD MERKEZ',font=f(90),fill='white')
d.text((40,912),'BANKASINDAN',font=f(87),fill=(255,222,54))
d.text((40,1025),'YAPAY ZEKÂ',font=f(91),fill='white')
d.text((40,1137),'UYARISI!',font=f(102),fill=(255,222,54))
d.rectangle((0,1260,1080,1340),fill=(4,95,205))
d.text((40,1270),'FİNANS SİSTEMİ İÇİN RİSK',font=f(47),fill='white')
d.text((42,685),'TEMSİLÎ GÖRSEL',font=f(27),fill='white')
out=Path('public-media/fed-ai-risk-20261117-0025.jpg');out.parent.mkdir(exist_ok=True)
clean=Image.new("RGB",im.size);clean.paste(im)
clean.save(out,'JPEG',quality=92,optimize=True,exif=b'')
with Image.open(out) as chk:
 assert chk.size==(1080,1350) and not chk.getexif()
print(out,hashlib.sha256(out.read_bytes()).hexdigest())
