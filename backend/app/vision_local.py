"""Low-memory image diagnostics and OCR. Never fabricate component pin connectivity."""
from __future__ import annotations
import asyncio,csv,io,re,shutil,subprocess,tempfile
from pathlib import Path
from PIL import Image,ImageOps
from .engine import OperationError
from .ingestion import Circuit,Component

# Allow large schematic scans up to 100 megapixels (e.g. 10000x7000)
MAX_PIXELS=100_000_000

def prepare(path,max_dim=3200):
 try:
  with Image.open(path) as original:
   if original.width*original.height>MAX_PIXELS:raise OperationError('Image exceeds 100 million pixels. Resize it before import.')
   img=ImageOps.exif_transpose(original).convert('RGB')
   if max(img.size)>max_dim:
    img.thumbnail((max_dim,max_dim))
   return img.copy()
 except OperationError:raise
 except Exception as e:raise OperationError('The uploaded file is not a readable image.') from e

def analyze(path):
 import cv2
 import numpy as np
 cv2.setNumThreads(1)
 img=prepare(path,max_dim=1600);gray=np.asarray(img.convert('L'))
 binary=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,9)
 lines=cv2.HoughLinesP(binary,1,np.pi/180,threshold=35,minLineLength=25,maxLineGap=3)
 contours,_=cv2.findContours(binary,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
 regions=[]
 for contour in contours:
  x,y,w,h=cv2.boundingRect(contour)
  if w*h>=30:regions.append({'x':int(x),'y':int(y),'width':int(w),'height':int(h)})
 return {'width':img.width,'height':img.height,'regions':regions[:500],'line_segments':lines[:,0,:].tolist()[:1000] if lines is not None else [],'algorithm':'OpenCV adaptive threshold + contours + Hough segments','connectivity_verified':False}

VALUE=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[fpnumkKMG])?(?:ohms?|Ω|[FfHhVv])?'

def ocr_candidates(tsv):
 """Associate numeric values below exact references using OCR word geometry."""
 words=[]
 try:
  for row in csv.DictReader(io.StringIO(tsv),delimiter='\t'):
   if row.get('level')=='5' and float(row.get('conf',0))>=30 and row.get('text','').strip():
    words.append({'text':row['text'].strip(),'x':int(row['left']),'y':int(row['top']),'w':int(row['width']),'h':int(row['height'])})
 except (KeyError,ValueError) as e:raise OperationError('Invalid OCR output.') from e
 components=[];seen=set()
 for word in words:
  ref=word['text']
  if not re.fullmatch(r'[RCLVUJQD]\d+',ref,re.I):continue
  ref=ref.upper()
  candidates=[other for other in words if re.fullmatch(VALUE,other['text']) and 0<other['y']-word['y']<=max(120,word['h']*6) and abs(other['x']+other['w']/2-word['x']-word['w']/2)<=max(60,word['w']*2)]
  if not candidates:continue  # An unreadable value is never an invented 10k/100nF/IC.
  value=min(candidates,key=lambda other:other['y']-word['y'])['text']
  if ref in seen:continue
  seen.add(ref);components.append(Component(ref=ref,value=value))
 if not components:raise OperationError('OCR did not recover reference/value pairs. Review the image manually or supply JSON/SPICE.')
 return Circuit(components=components,warnings=['OCR recovered candidate component text only; this may be incomplete or wrong. Review each reference/value against the image.','Pin-to-net connections are NOT recovered. Add wiring in reviewed JSON or the editor.'])

def ocr(path):
 if not shutil.which('tesseract'):raise OperationError('Local OCR is not installed. Use the Docker package or configure a vision model.')
 img=prepare(path,max_dim=3200)
 with tempfile.TemporaryDirectory() as td:
  source=Path(td)/'image.png';img.save(source)
  r=subprocess.run(['tesseract',str(source),'stdout','--psm','11','tsv'],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
  if r.returncode:raise OperationError('Local OCR failed to process image.')
  return ocr_candidates(r.stdout)
