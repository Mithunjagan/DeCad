"""Encode unretouched browser tour frames as a looping GIF for GitHub Markdown.

Serve tools/readme_tour.html from the repository root. Capture its 28 states,
advancing with Right Arrow after each screenshot, into frame-00.jpg ... frame-27.jpg.
Only the image encoding and palette are changed; the frames remain browser captures.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SCENES=['welcome','workspace','source-comparison','review-connections','bom','workspace-light','workspace-nebula']

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=ROOT/'docs/media/studio-tour.gif')
    parser.add_argument('--colors',type=int,choices=(96,128,256),default=96)
    args=parser.parse_args()
    paths=[args.frames/f'frame-{i:02d}.jpg' for i in range(28)]
    frames=[]
    for p in paths:
        with Image.open(p) as im:
            assert im.size==(1280,720),(p,im.size)
            frames.append(im.convert('RGB').quantize(colors=args.colors,dither=Image.Dither.NONE))
    durations=[2300 if i%4==0 else 110 for i in range(28)]
    args.out.parent.mkdir(parents=True,exist_ok=True)
    frames[0].save(args.out,save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=1,optimize=True)
    with Image.open(args.out) as animation:
        assert animation.n_frames==28 and animation.info['loop']==0
        measured=0
        for index in range(animation.n_frames):
            animation.seek(index);measured+=animation.info['duration']
        assert measured==sum(durations)
    manifest={'source':'Actual UI screenshots composed in tools/readme_tour.html and captured in the browser',
              'format':'GIF','width':1280,'height':720,'frames':28,'duration_ms':sum(durations),'loop':'infinite','palette_colors':args.colors,
              'source_screenshots':{f'docs/screenshots/{stem}.jpg':hashlib.sha256((ROOT/f'docs/screenshots/{stem}.jpg').read_bytes()).hexdigest() for stem in SCENES},
              'gif_sha256':hashlib.sha256(args.out.read_bytes()).hexdigest(),'bytes':args.out.stat().st_size}
    args.out.with_suffix('.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Validated 28 frames, {measured/1000:.2f} seconds, {args.out.stat().st_size/1024/1024:.2f} MiB: {args.out}')

if __name__=='__main__':
    main()
