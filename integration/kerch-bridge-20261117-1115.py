from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
import random,math
W,H=1080,1350
im=Image.new('RGB',(W,H));p=im.load()
random.seed(1711)
for y in range(H):
 for x in range(W):
  n=12*math.sin(x/100+y/70)+8*math.sin(x/33-y/43)
  if y<730:p[x,y]=(int(30+n*.4),int(34+n*.4),int(42+n*.5))
  else:p[x,y]=(int(45+22*y/H+n*.2),int(7+n*.15),int(14+n*.1))
d=ImageDraw.Draw(im)
# Conceptual map/bridge silhouette; not an actual image of the strike
for i in range(8):
 x=i*160-60;d.line((x,540,x+240,540),fill=(100,106,110),width=24)
 d.rectangle((x+80,540,x+115,705),fill=(75,79,82))
for x in range(50,1060,18):
 yy=540-190*math.sqrt(max(0,1-((x-550)/510)**2))
 d.ellipse((x-7,yy-7,x+7,yy+7),fill=(135,141,148))
d.rectangle((0,0,1080,128),fill=(172,5,18))
f='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def font(n):return ImageFont.truetype(f,n)
d.text((35,22),'HABERLER KKTC',font=font(68),fill='white')
d.polygon([(0,700),(1080,650),(1080,750),(0,820)],fill=(185,13,28))
d.text((38,825),'KERÇ KÖPRÜSÜ',font=font(94),fill='white')
d.text((38,945),'VURULDU!',font=font(155),fill=(255,223,28))
d.rectangle((0,1170,1080,1280),fill=(0,99,220))
d.text((35,1192),'HASARIN BOYUTU TARTIŞMALI',font=font(43),fill='white')
d.text((35,658),'TEMSİLÎ GÖRSEL',font=font(29),fill='white')
out=Path('public-media/kerch-bridge-20261117-1115.jpg');out.parent.mkdir(exist_ok=True)
im.save(out,format='JPEG',quality=94,subsampling=0,exif=b'')
print(out,out.stat().st_size)
