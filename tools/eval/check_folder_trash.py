"""Real Windows handle + headless browser + off-screen owned KiCad acceptance."""
import ctypes as ct
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import httpx

root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'backend'),str(root/'desktop')]
import app
import native_host as host
from app.project_trash import retained_receipt

name='smoke-folder-trash-'+str(time.time_ns());project=root/'backend/workspaces/local'/name
out=root/'backend/.state/codex-20261018/folder-trash';out.mkdir(parents=True,exist_ok=True)
kernel=ct.WinDLL('kernel32',use_last_error=True)
kernel.CreateFileW.argtypes=[wt.LPCWSTR,wt.DWORD,wt.DWORD,ct.c_void_p,wt.DWORD,wt.DWORD,wt.HANDLE];kernel.CreateFileW.restype=wt.HANDLE
kernel.CloseHandle.argtypes=[wt.HANDLE]
handle=None;process=None
with httpx.Client(base_url='http://localhost:3100/api',timeout=45) as client:
 client.get('/auth/dev').raise_for_status();client.post('/projects',json={'name':name}).raise_for_status()
 try:
  folder=project/'orcad';folder.mkdir();(folder/'watcher.txt').write_text('Directory watcher fixture, not an EDA asset.')
  handle=kernel.CreateFileW(str(folder),0x80,3,None,3,0x02000000,None);assert handle!=ct.c_void_p(-1).value
  log=(out/'native.log').open('w')
  process=subprocess.Popen([r'D:\KICAD\bin\pythonw.exe',str(root/'desktop/native_host.py'),'--root',str(project.parent),'--state',str(root/'backend/.state'),'--eeschema',r'D:\KICAD\bin\eeschema.exe','--project',name,'--local-login','--verify'],cwd=root,stdout=log,stderr=log)
  env={**os.environ,'DECAD_TRASH_TEST_PROJECT':name}
  result=subprocess.run(['node',str(root/'tools/eval/check_folder_trash.cjs')],cwd=root,env=env,timeout=150,capture_output=True,text=True)
  (out/'browser.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
  print(result.stdout+result.stderr,flush=True)
  assert result.returncode==0,'Browser/native acceptance failed.'
 finally:
  if handle and handle!=ct.c_void_p(-1).value:kernel.CloseHandle(handle)
  if process:
   for hwnd,title in host.windows(process.pid):
    if 'DeCad' in title:host.user32.PostMessageW(hwnd,0x10,0,0)
   try:process.wait(timeout=25)
   except subprocess.TimeoutExpired:print('Finish the owned verification KiCad dialog before cleanup.')
  # Only this generated fixture may be recovered and then physically archived.
  assert project.parent==root/'backend/workspaces/local' and name.startswith('smoke-folder-trash-')
  receipt=retained_receipt(project)
  if receipt:client.post('/projects/'+name+'/restore',json={'receipt':receipt}).raise_for_status()
  if project.exists():client.delete('/projects/'+name).raise_for_status()
