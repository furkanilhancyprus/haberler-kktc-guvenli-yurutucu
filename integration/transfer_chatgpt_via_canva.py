from urllib.request import urlopen, Request
from io import BytesIO
from PIL import Image, ImageOps
from pathlib import Path
import hashlib
URL="https://media.canva.com/v2/image-resize/format:PNG/height:200/quality:100/uri:ifs%3A%2F%2FM%2F09ce8b12-f70a-4486-949c-249fb6320b0e/watermark:F/width:151?csig=AAAAAAAAAAAAAAAAAAAAACt6j9PW8V-rZxr4fAHYOxzSLOlWisaaCvgkguBApg4C&exp=1794885625&osig=AAAAAAAAAAAAAAAAAAAAAGVY2Pv4r9nj1NFM97wtPrnb5HgQ9wSrP-LRIgP1jEM5&signer=media-rpc&token=AAIAAU0AJDA5Y2U4YjEyLWY3MGEtNDQ4Ni05NDljLTI0OWZiNjMyMGIwZQAAAAABoeeFJKj0eJFDvQZnhc72dtqMT_izT4nA8POylcONlna9sFZSYA&x-canva-quality=thumbnail"
req=Request(URL,headers={"User-Agent":"Mozilla/5.0"})
with urlopen(req,timeout=30) as response: data=response.read()
with Image.open(BytesIO(data)) as source:
    im=ImageOps.fit(source.convert("RGB"),(1080,1350),method=Image.Resampling.LANCZOS)
dest=Path("public-media/chatgpt-original-weather-transfer-test.jpg")
dest.parent.mkdir(parents=True,exist_ok=True)
im.save(dest,"JPEG",quality=92,subsampling=0,optimize=True,exif=b"")
print("Transferred source bytes",len(data),"output bytes",dest.stat().st_size,"SHA256",hashlib.sha256(dest.read_bytes()).hexdigest())
