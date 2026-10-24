import json,sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'backend')]
from app.digital_vision import Token
from app.provisional_terminals import lead_gap_bodies
from app.implicit_terminals import graphic_token,opposing_leads
from app.circuit_vision import bodies
from app.terminal_recovery import perimeter_stubs
b=ROOT/'evidence/closure-20261024/blocker-audit'
for row in json.loads((b/'report.json').read_text()):
 if (row['case'],row['component']['ref']) not in [('S5','R19'),('S4-scan300','R14')]:continue
 name=row['case'];ref=row['component']['ref'];x0,y0,_,_=row['working_bounds']
 g=json.loads((ROOT/'evidence/upgrade-20261024/final-fresh/original'/name/'recognized.json').read_text());ch=g['image_metadata']['character_height'];scale=32/ch
 gray=np.asarray(Image.open(row['crop']).convert('L'));gray=cv2.resize(gray,None,fx=scale,fy=scale);binary=(gray<180).astype('uint8')*255;clean=binary.copy()
 tokens=[Token(**t) for t in json.loads((ROOT/'evidence/upgrade-20261024/final-fresh/original'/name/'ocr-tokens.json').read_text())]
 for t in tokens:
  if graphic_token(t) or t.x1<x0 or t.y1<y0 or t.x0>x0+900 or t.y0>y0+560:continue
  a,c,d,e=[round(v*scale) for v in (t.x0-x0,t.y0-y0,t.x1-x0,t.y1-y0)]
  if any(k.isalnum() for k in t.text):clean[max(0,c-1):e+2,max(0,a-1):d+2]=0
 for label,img in [('raw',binary),('clean',clean)]:
  found=lead_gap_bodies(img)+bodies(img)
  print(name,ref,label,[(body,opposing_leads(binary,body),perimeter_stubs(img,[body['x'],body['y'],body['x']+body['w'],body['y']+body['h']],32,corner_inset=0)) for body in found])
  Image.fromarray(255-img).save(b/f'{name}-{ref}-{label}.png')
