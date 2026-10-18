"""Brief real mouse/keyboard move/save check, restricted to our smoke project."""
import ctypes as ct
from ctypes import wintypes as wt
import hashlib
import json
from pathlib import Path
import sys
import time
sys.path[:0]=[str(Path('desktop').resolve()),str(Path('backend').resolve())]
import native_host as host
from app.sexpr import parse,children,child
u=host.user32
for name,args,result in [
 ('GetForegroundWindow',[],wt.HWND),('SetForegroundWindow',[wt.HWND],wt.BOOL),
 ('GetCursorPos',[ct.POINTER(wt.POINT)],wt.BOOL),('SetCursorPos',[ct.c_int,ct.c_int],wt.BOOL),
 ('GetWindowRect',[wt.HWND,ct.POINTER(wt.RECT)],wt.BOOL),
 ('WindowFromPoint',[wt.POINT],wt.HWND),
 ('EnumChildWindows',[wt.HWND,host.CALLBACK,wt.LPARAM],wt.BOOL),
 ('GetAsyncKeyState',[ct.c_int],ct.c_short),
 ('keybd_event',[wt.BYTE,wt.BYTE,wt.DWORD,ct.c_size_t],None),
 ('mouse_event',[wt.DWORD,wt.DWORD,wt.DWORD,wt.DWORD,ct.c_size_t],None),
 ('AttachThreadInput',[wt.DWORD,wt.DWORD,wt.BOOL],wt.BOOL),
]:
 fn=getattr(u,name);fn.argtypes=args;fn.restype=result
assert '--allow-visible' in sys.argv,'This check briefly shows its own desktop window.'
status=next(json.loads(p.read_text()) for p in Path('backend/.state/native-desktop').glob('*/status.json')
            if json.loads(p.read_text()).get('hwnd') and not json.loads(p.read_text()).get('closed'))
path=Path(status['path']);assert path.parent.name.startswith('smoke-native-')
frame=next(hwnd for hwnd,name in host.windows(status['pid']) if 'DeCad' in name)
def position():return [child(s,'at')[1:] for s in children(parse(path.read_text()),'symbol')]
before=position();old_focus=u.GetForegroundWindow();old_mouse=wt.POINT();u.GetCursorPos(ct.byref(old_mouse))
def owned_focus():
 pid=wt.DWORD();u.GetWindowThreadProcessId(u.GetForegroundWindow(),ct.byref(pid))
 return pid.value in (status['pid'],status['editor_pid'])
try:
 assert not any(u.GetAsyncKeyState(k)&0x8000 for k in (16,17,18)),'A user modifier key is held.'
 u.SetWindowPos(frame,wt.HWND(-1),30,55,0,0,0x51)
 frame_rect=wt.RECT();u.GetWindowRect(frame,ct.byref(frame_rect))
 title_point=wt.POINT(frame_rect.left+200,frame_rect.top+15)
 assert u.WindowFromPoint(title_point)==frame,'Test title bar is covered; no click sent.'
 u.SetCursorPos(title_point.x,title_point.y);u.mouse_event(2,0,0,0,0);u.mouse_event(4,0,0,0,0)
 u.SetWindowPos(frame,wt.HWND(-2),0,0,0,0,0x13)
 kernel=ct.WinDLL('kernel32');kernel.GetCurrentThreadId.restype=wt.DWORD
 caller=kernel.GetCurrentThreadId();foreground_thread=u.GetWindowThreadProcessId(old_focus,None)
 attached=u.AttachThreadInput(caller,foreground_thread,True)
 try:u.SetForegroundWindow(frame)
 finally:
  if attached:u.AttachThreadInput(caller,foreground_thread,False)
 time.sleep(.25)
 assert owned_focus(),'Could not focus the owned test window; no keys sent.'
 canvases=[]
 @host.CALLBACK
 def find(hwnd,_):
  cls=ct.create_unicode_buffer(100);u.GetClassNameW(hwnd,cls,100)
  if cls.value=='wxGLCanvas' and u.IsWindowVisible(hwnd):canvases.append(hwnd)
  return True
 u.EnumChildWindows(status['hwnd'],find,0);canvas=canvases[0]
 rect=wt.RECT();u.GetWindowRect(canvas,ct.byref(rect));x=(rect.left+rect.right)//2;y=(rect.top+rect.bottom)//2
 u.SetCursorPos(x,y);time.sleep(.15)
 assert u.WindowFromPoint(wt.POINT(x,y))==canvas,'Canvas is covered; no click sent.'
 def click():u.mouse_event(2,0,0,0,0);u.mouse_event(4,0,0,0,0)
 def key(value):
  assert owned_focus(),'Focus changed; stopping input.'
  u.keybd_event(value,0,0,0);u.keybd_event(value,0,2,0)
 click();time.sleep(.15);key(ord('M'));time.sleep(.15)
 u.SetCursorPos(x+60,y+35);time.sleep(.15);click();time.sleep(.15);key(27)
 u.PostMessageW(status['hwnd'],0x111,status['commands']['save'],0)
 deadline=time.monotonic()+3
 while time.monotonic()<deadline and position()==before:time.sleep(.1)
 after=position();result={'before':before,'after':after,'moved_and_saved':before!=after,
    'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 Path('backend/.state/codex-20261018/native-move-check.json').write_text(json.dumps(result,indent=1))
 assert result['moved_and_saved'],result
 print('PASS: actual canvas mouse/keyboard component move and native Save; saved coordinates changed.',result)
finally:
 u.SetWindowPos(frame,wt.HWND(-2),0,0,0,0,0x13)
 if owned_focus():u.SetCursorPos(old_mouse.x,old_mouse.y);u.SetForegroundWindow(old_focus)
 u.SetWindowPos(frame,None,-2800,0,0,0,0x15)
