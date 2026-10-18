"""CPU symbol geometry + OCR association + raster wire topology for clean schematics.
Unsupported/ambiguous diagrams remain explicit review proposals, never accepted designs.
"""
import csv,io,re,shutil,subprocess,tempfile
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from .vision_local import prepare
from .ingestion import Circuit,Component,Net,Node
from .engine import OperationError

def words(tsv):
 result=[]
 for row in csv.DictReader(io.StringIO(tsv),delimiter='\t'):
  if row.get('level')=='5' and row.get('text','').strip():
   result.append({'text':row['text'].strip(),'conf':float(row['conf']),'x':int(row['left']),'y':int(row['top']),'w':int(row['width']),'h':int(row['height'])})
 return result

def bodies(binary):
 found=[]
 # Closed circle/rectangle bodies. Wires outside the body do not change its inner contour.
 contours,_=cv2.findContours(binary,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
 for c in contours[:5000]:
  x,y,w,h=cv2.boundingRect(c);area=cv2.contourArea(c)
  if min(w,h)<16 or max(w,h)>240 or area<150:continue
  ratio=max(w,h)/min(w,h);approx=cv2.approxPolyDP(c,.025*cv2.arcLength(c,True),True)
  if ratio>1.8 and len(approx)==4 and area/(w*h)>.65:kind='R'
  elif min(w,h)>=40 and ratio<1.25 and len(approx)>=7 and .55<area/(w*h)<.85:kind='V'
  else:continue
  box=(x,y,w,h)
  if not any(f['kind']==kind and abs((f['x']+f['w']/2)-(x+w/2))+abs((f['y']+f['h']/2)-(y+h/2))<15 and abs(f['w']-w)<max(15,w*.2) and abs(f['h']-h)<max(15,h*.2) for f in found):found.append(dict(kind=kind,x=x,y=y,w=w,h=h,closed=True))
 lines=cv2.HoughLinesP(binary,1,np.pi/180,threshold=10,minLineLength=10,maxLineGap=3)
 lines=[] if lines is None else [tuple(map(int,l[0])) for l in lines[:1000]]
 # US zig-zag resistors: clusters of alternating diagonal strokes.
 diagonals=[l for l in lines if 0.15<abs(l[2]-l[0])/max(1,abs(l[3]-l[1]))<6.5 and max(abs(l[2]-l[0]),abs(l[3]-l[1]))<95]
 groups=[]
 for line in diagonals[:400]:
  points=[line[:2],line[2:]];near=[]
  for i,g in enumerate(groups):
   if any(np.linalg.norm(np.array(a)-b)<25 for a in points for b in g['points']):near.append(i)
  group={'lines':[line],'points':points}
  for i in reversed(near):old=groups.pop(i);group['lines']+=old['lines'];group['points']+=old['points']
  groups.append(group)
 # Join collinear zig-zag fragments separated by Hough sampling gaps.
 changed=True
 while changed:
  changed=False
  for i,a in enumerate(groups):
   aa=np.array(a['points']);lo=aa.min(axis=0);hi=aa.max(axis=0)
   for j in range(i+1,len(groups)):
    bb=np.array(groups[j]['points']);bl=bb.min(axis=0);bh=bb.max(axis=0)
    overlap=np.minimum(hi,bh)-np.maximum(lo,bl);sizes=np.minimum(hi-lo,bh-bl)
    if (overlap[0]>.6*sizes[0] and overlap[1]>-30) or (overlap[1]>.6*sizes[1] and overlap[0]>-30):
     old=groups.pop(j);a['lines']+=old['lines'];a['points']+=old['points'];changed=True;break
   if changed:break
 for g in groups:
  if len(g['lines'])<4:continue
  a=np.array(g['points']);x,y=a.min(axis=0);w,h=a.max(axis=0)-a.min(axis=0)+1
  if min(w,h)<12 or max(w,h)>240 or max(w,h)/min(w,h)<1.5:continue
  if not any(abs(f['x']-x)+abs(f['y']-y)<15 for f in found):found.append(dict(kind='R',x=int(x),y=int(y),w=int(w),h=int(h)))
 # Capacitor plates: short aligned parallel strokes, opposite pin axis.
 axes=[l for l in lines if min(abs(l[2]-l[0]),abs(l[3]-l[1]))<3 and 18<=max(abs(l[2]-l[0]),abs(l[3]-l[1]))<=110]
 for i,a in enumerate(axes[:400]):
  horizontal=abs(a[2]-a[0])>abs(a[3]-a[1]);ac=(np.array(a[:2])+a[2:])/2
  for b in axes[i+1:400]:
   if horizontal!=(abs(b[2]-b[0])>abs(b[3]-b[1])):continue
   bc=(np.array(b[:2])+b[2:])/2;delta=abs(ac-bc);normal=1 if horizontal else 0
   if not 7<=delta[normal]<=70 or delta[1-normal]>5:continue
   if abs(max(abs(a[2]-a[0]),abs(a[3]-a[1]))-max(abs(b[2]-b[0]),abs(b[3]-b[1])))>6:continue
   coords=np.array([a[:2],a[2:],b[:2],b[2:]]);x,y=coords.min(axis=0);w,h=coords.max(axis=0)-coords.min(axis=0)+1
   if any(abs(f['x']-x)+abs(f['y']-y)<15 for f in found):continue
   found.append(dict(kind='C',x=int(x),y=int(y),w=int(w),h=int(h),vertical=horizontal))
 return found

def extract(path):
 if not shutil.which('tesseract'):raise OperationError('CPU circuit recognition requires Tesseract.')
 cv2.setNumThreads(1);image=prepare(path)
 scale=min(3,1400/max(image.size))
 if scale>1:image=image.resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'image.png';image.save(p)
  r=subprocess.run(['tesseract',str(p),'stdout','--psm','11','tsv'],capture_output=True,text=True,timeout=30)
  if r.returncode:raise OperationError('Circuit OCR failed.')
 return recover(image,words(r.stdout))

def recover(image,ocr):
 gray=np.array(image.convert('L'));binary=(gray<150).astype('uint8')*255
 cleaned=binary.copy();warnings=[]
 for word in ocr:
  if re.search('[A-Za-z0-9]',word['text']):
   x,y,w,h=[word[k] for k in ['x','y','w','h']];cleaned[max(0,y-2):y+h+2,max(0,x-2):x+w+2]=0
 if any(re.fullmatch(r'[UDQML]\d+',w['text']) for w in ocr):raise OperationError('CPU circuit recognition does not support these device symbols yet. Choose the configured vision server or import reviewed JSON.')
 symbols=bodies(cleaned);components=[];assigned=[];used=set()
 refs=[]
 for word in ocr:
  text=word['text'];normalized=re.sub(r'(?<=[RCV])[lI]$','1',text)
  if re.fullmatch(r'[RCV]\d+',normalized) and word['conf']>=30:
   if normalized!=text:warnings.append(f'OCR normalized {text} to {normalized}; confirm the reference.')
   refs.append((normalized,word))
 for ref,word in refs:
  possible=[(i,b) for i,b in enumerate(symbols) if i not in used and b['kind']==ref[0]]
  if not possible:raise OperationError(f'Cannot locate supported symbol geometry for {ref}; use vision or reviewed JSON.')
  i,b=min(possible,key=lambda pair:np.hypot(pair[1]['x']+pair[1]['w']/2-word['x']-word['w']/2,pair[1]['y']+pair[1]['h']/2-word['y']-word['h']/2))
  if np.hypot(b['x']-word['x'],b['y']-word['y'])>300:raise OperationError('Symbol/reference association is ambiguous.')
  values=[v for v in ocr if v is not word and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[fpnumkKMG])?(?:[FHVΩ]|ohms?)?',v['text']) and abs(v['y']-word['y'])<word['h']*3 and abs(v['x']-word['x'])<220]
  if not values:raise OperationError(f'No readable value for {ref}.')
  val=min(values,key=lambda v:np.hypot(v['x']-word['x'],v['y']-word['y']))['text']
  components.append(Component(ref=ref,value=val,library={'R':'Device:R','C':'Device:C','V':'Simulation_SPICE:VDC'}[ref[0]]));assigned.append((ref,b));used.add(i)
 if not components:raise OperationError('No supported R/C/V symbols and reference/value pairs found. Use the vision server for other symbols.')
 if any(b.get('closed') and b['kind'] in ['R','V'] and i not in used for i,b in enumerate(symbols)):raise OperationError('A component symbol has no reliable reference/value association; choose vision or reviewed JSON.')
 if len({c.ref for c in components})!=len(components):raise OperationError('Duplicate references in image.')
 # Keep long straight wires through label areas; remove bodies so pins cannot short through symbols.
 wire=cleaned|cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((70,1),np.uint8))|cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((1,70),np.uint8))
 pins=[]
 for ref,b in assigned:
  x,y,w,h=[b[k] for k in ['x','y','w','h']];vertical=b.get('vertical',h>w)
  if b['kind']=='V':
   # This supported source convention is vertical positive above negative.
   vertical=True;warnings.append(f'{ref}: confirm positive terminal is the upper pin.')
  wire[max(0,y-3):y+h+3,max(0,x-3):x+w+3]=0
  points=[(x+w//2,y-5),(x+w//2,y+h+5)] if vertical else [(x-5,y+h//2),(x+w+5,y+h//2)]
  pins.extend((ref,str(i+1),point) for i,point in enumerate(points))
 # Four-way crossings without a visible junction dot are ambiguous, not automatic shorts.
 horizontal=cv2.morphologyEx(wire,cv2.MORPH_OPEN,np.ones((1,60),np.uint8))
 vertical=cv2.morphologyEx(wire,cv2.MORPH_OPEN,np.ones((60,1),np.uint8))
 nc,_,_,centers=cv2.connectedComponentsWithStats(horizontal&vertical,8)
 for cx,cy in centers[1:1000]:
  x,y=round(cx),round(cy)
  if x<35 or y<35 or x+35>=wire.shape[1] or y+35>=wire.shape[0]:continue
  rays=[wire[y-3:y+4,x-30:x-20],wire[y-3:y+4,x+20:x+30],wire[y-30:y-20,x-3:x+4],wire[y+20:y+30,x-3:x+4]]
  if not all(np.count_nonzero(ray)>10 for ray in rays):continue
  thickness=max(1,round(max(np.count_nonzero(ray)/10 for ray in rays)))
  radius=min(15,thickness*2+1);patch=wire[y-radius:y+radius+1,x-radius:x+radius+1]
  if np.count_nonzero(patch)/patch.size<.65:raise OperationError('Unmarked four-way wire crossing is ambiguous. Add/confirm a junction dot or use reviewed JSON.')
 count,labels,stats,_=cv2.connectedComponentsWithStats(wire,8)
 nets={}
 for ref,pin,(x,y) in pins:
  region=labels[max(0,y-8):y+9,max(0,x-8):x+9];ids=[int(i) for i in np.unique(region) if i and stats[i,cv2.CC_STAT_AREA]>25]
  if len(ids)!=1:raise OperationError(f'Ambiguous or missing wire at {ref} pin {pin}; review the image.')
  nets.setdefault(ids[0],[]).append(Node(ref=ref,pin=pin))
 if any(len({n.pin for n in nodes if n.ref==ref})>1 for nodes in nets.values() for ref in {n.ref for n in nodes}):raise OperationError('Both pins of a component appear shorted; confirm the source using vision or reviewed JSON.')
 names={};used_names=set()
 for word in ocr:
  text=word['text'].upper()
  if text not in ['GND','VIN','VOUT','VCC','VDD','VSS']:continue
  cx=word['x']+word['w']//2;cy=word['y']+word['h']//2
  distances=[]
  for idx in nets:
   ys,xs=np.where(labels==idx);dist=float(np.min((xs-cx)**2+(ys-cy)**2));distances.append((dist,idx))
  dist,idx=min(distances)
  if dist<100**2 and idx not in names and text not in used_names:names[idx]=text;used_names.add(text)
 warnings+=['CPU geometry recognition supports clean axis-aligned R/C/V diagrams; other symbols, handwritten topology and unmarked wire crossings require review.','Physical pin numbering follows the selected KiCad symbols. Review values, source polarity, every junction and all inferred connections before applying.']
 return Circuit(components=components,nets=[Net(name=names.get(idx,'NET_'+str(i+1)),nodes=nodes) for i,(idx,nodes) in enumerate(nets.items())],warnings=warnings)
