#!/usr/bin/env python3
"""No network listener: process application launches through the shared local state folder."""
from __future__ import annotations
import argparse,json,os,platform,shutil,subprocess,time
from pathlib import Path

NAMES={'kicad':'KiCad','ltspice':'LTspice','qucs-s':'Qucs-S','ngspice':'ngspice'}

def discover():
 system=platform.system();apps={}
 for tool,name in NAMES.items():
  configured=os.getenv('S2SDN_'+tool.upper().replace('-','_')+'_PATH')
  candidates=[configured] if configured else []
  if system=='Darwin':
   candidates+= {'kicad':['/Applications/KiCad/KiCad.app','/Applications/KiCad.app'],'ltspice':['/Applications/LTspice.app'],'qucs-s':['/Applications/Qucs-S.app','/Applications/qucs-s.app'],'ngspice':[]}[tool]
  elif system=='Windows':
   for root in [os.getenv('ProgramFiles','C:/Program Files'),os.getenv('LOCALAPPDATA','')]:
    candidates+= {'ltspice':[f'{root}/ADI/LTspice/LTspice.exe',f'{root}/LTspice/LTspice.exe'],'qucs-s':[f'{root}/Qucs-S/bin/qucs-s.exe'],'kicad':[str(p) for p in Path(root,'KiCad').glob('*/bin/eeschema.exe')],'ngspice':[]}[tool]
  executable=next((p for p in candidates if p and Path(p).exists()),None) or shutil.which({'kicad':'eeschema','ltspice':'LTspice','qucs-s':'qucs-s','ngspice':'ngspice'}[tool])
  apps[tool]={'name':name,'installed':bool(executable),'path':executable}
 return apps

def atomic(path,data):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data));temp.replace(path)

def process(folder,apps):
 request=json.loads((folder/'request.json').read_text());tool=request.get('tool');name=request.get('file','')
 if request.get('action')!='open' or tool not in apps:raise ValueError('Unsupported bridge action.')
 path=folder/name
 if Path(name).name!=name or path.is_symlink() or not path.is_file():raise ValueError('Invalid application artifact.')
 if not apps[tool]['installed']:raise ValueError('Application is not installed.')
 exe=apps[tool]['path']
 if platform.system()=='Darwin' and exe.endswith('.app'):command=['open','-a',exe,str(path.resolve())]
 elif tool=='ngspice':command=[exe,'-b',str(path.resolve())]
 else:command=[exe,str(path.resolve())]
 # Fixed arguments only; no shell, arbitrary executable, URL, or script command accepted.
 log=open(folder/'application.log','w')
 proc=subprocess.Popen(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT);log.close()
 if platform.system()=='Darwin' and exe.endswith('.app'):
  code=proc.wait(timeout=15)
  if code:raise ValueError('Application launch failed; see application.log.')
  return {'id':request['id'],'status':'launched','tool':tool,'file':name}
 if tool=='ngspice':
  try:code=proc.wait(timeout=45)
  except subprocess.TimeoutExpired:
   proc.kill();proc.wait();raise ValueError('ngspice timed out; see application.log.')
  if code:raise ValueError('ngspice failed; see application.log.')
  return {'id':request['id'],'status':'completed','tool':tool,'file':name,'pid':proc.pid}
 try:code=proc.wait(timeout=0.25)
 except subprocess.TimeoutExpired:code=None
 if code not in [None,0]:raise ValueError('Application exited with an error; see application.log.')
 return {'id':request['id'],'status':'launched','tool':tool,'file':name,'pid':proc.pid}

def run(root):
 root.mkdir(parents=True,exist_ok=True);status=root/'bridge-status.json'
 lock=root/'bridge.lock'
 try:lock.mkdir()
 except FileExistsError:
  try:pid=int((lock/'pid').read_text());os.kill(pid,0)
  except ProcessLookupError:
   (lock/'pid').unlink(missing_ok=True);lock.rmdir();lock.mkdir()
  except (OSError,ValueError):raise SystemExit('Bridge lock cannot be verified. Stop the previous bridge before restarting.')
  else:raise SystemExit('Desktop bridge is already running.')
 (lock/'pid').write_text(str(os.getpid()))
 (root/'bridge-stop').unlink(missing_ok=True)
 try:
  while True:
   if (root/'bridge-stop').exists():break
   apps=discover();atomic(status,{'updated_at':time.time(),'os':platform.system(),'applications':apps})
   for folder in sorted((root/'bridge-jobs').glob('*')):
    if folder.is_symlink() or not folder.is_dir() or not (folder/'request.json').is_file() or (folder/'response.json').exists():continue
    try:
     request=json.loads((folder/'request.json').read_text())
     if time.time()-request.get('created_at',0)>300:raise ValueError('Application job expired; submit it again.')
     response=process(folder,apps)
    except Exception as e:response={'id':folder.name,'status':'failed','error':str(e)}
    atomic(folder/'response.json',response)
   time.sleep(1)
 finally:status.unlink(missing_ok=True);(lock/'pid').unlink(missing_ok=True);lock.rmdir()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--state',type=Path,required=True);parser.add_argument('--once',action='store_true');args=parser.parse_args()
 if args.once:print(json.dumps(discover(),indent=2))
 else:run(args.state.resolve())
