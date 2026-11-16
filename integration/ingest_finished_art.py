#!/usr/bin/env python3
"""Ingest an already-designed ChatGPT JPEG/PNG, never redraw the artwork.
Usage: python integration/ingest_finished_art.py --input path/to/image.png --slug unique-slug
"""
import argparse, hashlib, json
from pathlib import Path
from PIL import Image, ImageOps

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--slug",required=True)
    args=p.parse_args()
    if not args.slug or not all(c.isalnum() or c in "-_" for c in args.slug):
        p.error("slug must contain only letters, numbers, dash, underscore")
    src=Path(args.input)
    if not src.is_file(): p.error("image file not found: "+str(src))
    with Image.open(src) as image:
        im=ImageOps.exif_transpose(image).convert("RGB")
        if im.width*5 != im.height*4:
            p.error("source must be portrait 4:5, got %sx%s"%(im.width,im.height))
        if im.size != (1080,1350):
            im=im.resize((1080,1350),Image.Resampling.LANCZOS)
        dest=Path("public-media")/(args.slug+".jpg")
        dest.parent.mkdir(parents=True,exist_ok=True)
        # New pixel-only JPEG discards EXIF, GPS, XMP, IPTC and PNG metadata.
        im.save(dest,"JPEG",quality=91,subsampling=0,optimize=True,exif=b"")
    data=dest.read_bytes()
    manifest={"slug":args.slug,"file":str(dest),"sha256":hashlib.sha256(data).hexdigest(),"width":1080,"height":1350,"bytes":len(data),"mediaUrl":"https://raw.githubusercontent.com/furkanilhancyprus/haberler-kktc-guvenli-yurutucu/main/"+str(dest)}
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
