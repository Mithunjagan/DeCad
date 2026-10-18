"""Capture only our test desktop window, including when it is off screen."""
import ctypes as ct
from ctypes import wintypes as wt
import json
from pathlib import Path
import sys
import argparse
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'desktop'))
import native_host as host
u=host.user32;g=host.gdi32
for name,args,result in [
 ('GetWindowRect',[wt.HWND,ct.POINTER(wt.RECT)],wt.BOOL),
 ('GetWindowDC',[wt.HWND],wt.HDC),('ReleaseDC',[wt.HWND,wt.HDC],ct.c_int),
 ('PrintWindow',[wt.HWND,wt.HDC,wt.UINT],wt.BOOL),
]:
 fn=getattr(u,name);fn.argtypes=args;fn.restype=result
for name,args,result in [
 ('CreateCompatibleDC',[wt.HDC],wt.HDC),('DeleteDC',[wt.HDC],wt.BOOL),
 ('CreateCompatibleBitmap',[wt.HDC,ct.c_int,ct.c_int],wt.HBITMAP),
 ('SelectObject',[wt.HDC,wt.HANDLE],wt.HANDLE),
 ('GetBitmapBits',[wt.HBITMAP,wt.LONG,ct.c_void_p],wt.LONG),
]:
 fn=getattr(g,name);fn.argtypes=args;fn.restype=result
parser=argparse.ArgumentParser();parser.add_argument('--pid',type=int);parser.add_argument('--output')
args=parser.parse_args()
for file in Path('backend/.state/native-desktop').glob('*/status.json'):
 status=json.loads(file.read_text())
 if status.get('closed'):continue
 if args.pid and status['pid']!=args.pid:continue
 for hwnd,title in host.windows(status['pid']):
  if 'DeCad' not in title:continue
  rect=wt.RECT();u.GetWindowRect(hwnd,ct.byref(rect))
  width,height=rect.right-rect.left,rect.bottom-rect.top
  dc=u.GetWindowDC(hwnd);mem=g.CreateCompatibleDC(dc)
  bitmap=g.CreateCompatibleBitmap(dc,width,height);previous=g.SelectObject(mem,bitmap)
  try:
   assert u.PrintWindow(hwnd,mem,2)
   data=ct.create_string_buffer(width*height*4);g.GetBitmapBits(bitmap,len(data),data)
   out=Path(args.output or 'backend/.state/codex-20261018/native-offscreen.png')
   Image.frombuffer('RGB',(width,height),data,'raw','BGRX',0,1).save(out)
   print(title,width,height,out)
  finally:g.SelectObject(mem,previous);g.DeleteObject(bitmap);g.DeleteDC(mem);u.ReleaseDC(hwnd,dc)
