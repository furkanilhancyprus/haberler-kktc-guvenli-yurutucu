from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math, random
W,H=1080,1350
im=Image.new("RGB",(W,H)); p=im.load()
for y in range(H):
    t=y/H
    for x in range(W):
        haze=18*math.sin(x/180+y/95)
        if y<700:
            p[x,y]=(int(26+10*t+haze*.18),int(40+10*t+haze*.2),int(57+12*t+haze*.3))
        else:
            p[x,y]=(int(34+18*t),int(9+5*t),int(14+8*t))
d=ImageDraw.Draw(im)
random.seed(17)
for i in range(85):
    x=random.randrange(-200,1200); y=random.randrange(100,690)
    d.line((x,y,x-25,y+85),fill=(99,131,157),width=3)
for i in range(5):
    cx=100+i*220;cy=230+(i%2)*55
    for ox,oy,r in [(-65,5,80),(0,-30,108),(90,8,82)]:
        d.ellipse((cx+ox-r,cy+oy-r,cx+ox+r,cy+oy+r),fill=(88,99,113))
d.polygon([(0,610),(155,390),(315,580),(510,340),(760,625),(900,455),(1080,610),(1080,740),(0,740)],fill=(34,49,57))
d.polygon([(0,690),(190,560),(400,680),(600,545),(780,680),(1080,575),(1080,810),(0,810)],fill=(22,37,40))
d.rectangle((0,0,W,100),fill=(150,12,26))
d.polygon([(0,100),(800,100),(720,124),(0,119)],fill=(190,19,33))
font='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def f(n):return ImageFont.truetype(font,n)
d.text((45,19),'HABERLER KKTC',font=f(59),fill='white',stroke_width=1)
d.rectangle((0,735,1080,1350),fill=(31,8,14))
d.polygon([(0,760),(1080,712),(1080,778),(0,824)],fill=(172,16,33))
d.text((40,800),'KIBRIS’TA HAVA',font=f(91),fill=(255,230,49),stroke_width=1)
d.text((40,913),'DEĞİŞİYOR!',font=f(104),fill='white')
d.text((42,1046),'DAĞLIK BÖLGELERDE',font=f(62),fill='white')
d.text((42,1122),'YAĞIŞ BEKLENİYOR',font=f(67),fill=(255,224,52))
d.rectangle((0,1230,1080,1320),fill=(0,91,211))
d.text((35,1247),'17 KASIM SALI • 23–24°C',font=f(48),fill='white')
d.text((45,675),'TEMSİLÎ GÖRSEL',font=f(28),fill='white')
out=Path('public-media/weather-20261117.jpg');out.parent.mkdir(exist_ok=True)
im.save(out,format='JPEG',quality=85,optimize=True,exif=b'')
print(out, out.stat().st_size)
