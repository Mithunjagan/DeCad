"""Low-memory image diagnostics and OCR. Never fabricate component pin connectivity."""
from __future__ import annotations
import asyncio,csv,io,re,shutil,subprocess,tempfile
from pathlib import Path
from PIL import Image,ImageOps
from .engine import OperationError
from .ingestion import Circuit,Component

# Restrict decompressed input size independently of the compressed upload limit.
MAX_PIXELS=16_000_000

def prepare(path):
 try:
  with Image.open(path) as original:
   if original.width*original.height>MAX_PIXELS:raise OperationError('Image exceeds 16 million pixels. Resize it before import.')
   img=ImageOps.exif_transpose(original).convert('RGB');img.thumbnail((1600,1600));return img.copy()
 except OperationError:raise
 except Exception as e:raise OperationError('The uploaded file is not a readable image.') from e

def analyze(path):
 import cv2
 import numpy as np
 cv2.setNumThreads(1)
 img=prepare(path);gray=np.asarray(img.convert('L'))
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
   if row['level']=='5' and float(row['conf'])>=60 and row['text'].strip():
    words.append({'text':row['text'].strip(),'x':int(row['left']),'y':int(row['top']),'w':int(row['width']),'h':int(row['height'])})
 except (KeyError,ValueError) as e:raise OperationError('Invalid OCR output.') from e
 components=[];seen=set()
 for word in words:
  ref=word['text']
  if not re.fullmatch(r'[RCLV]\d+',ref):continue
  candidates=[other for other in words if re.fullmatch(VALUE,other['text']) and 0<other['y']-word['y']<=max(80,word['h']*5) and abs(other['x']+other['w']/2-word['x']-word['w']/2)<=max(40,word['w']*1.5)]
  if not candidates:continue
  value=min(candidates,key=lambda other:other['y']-word['y'])['text']
  if ref in seen:raise OperationError('OCR found duplicate references. Review the source manually.')
  seen.add(ref);components.append(Component(ref=ref,value=value))
 if not components:raise OperationError('OCR did not recover trustworthy reference/value pairs. Review the image manually or supply JSON/SPICE; no circuit was changed.')
 return Circuit(components=components,warnings=['OCR recovered candidate component text only; this may be incomplete or wrong. Review each reference/value against the image.','Pin-to-net connections are NOT recovered. Add wiring in reviewed JSON or the editor.'])

def ocr(path):
 if not shutil.which('tesseract'):raise OperationError('Local OCR is not installed. Use the Docker package or configure a vision model.')
 img=prepare(path)
 with tempfile.TemporaryDirectory() as td:
  source=Path(td)/'image.png';img.save(source)
  try:r=subprocess.run(['tesseract',str(source),'stdout','--psm','11','tsv'],capture_output=True,text=True,timeout=30,env={**__import__('os').environ,'OMP_THREAD_LIMIT':'1'})
  except subprocess.TimeoutExpired as e:raise OperationError('Local OCR timed out. Crop or resize the source image.') from e
  if r.returncode:raise OperationError('Local OCR could not read the image.')
 return ocr_candidates(r.stdout)
