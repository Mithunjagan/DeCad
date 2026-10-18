"""Schematic2SDN local workbench API."""
from __future__ import annotations
import asyncio
import csv
import io
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.parse
import unicodedata
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode
import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from .assistant import execute, apply_circuit, remember, template, undo_redo
from .engine import OperationError, Schematic, atomic_text, find_cli, library_dir, project_lock
from .formats import edif, spice
from .ingestion import Circuit
from .simulation import simulate
from .integrations import TOOLS, bundle, bridge_status, enqueue, job_result, simulate_qucs
from . import model_runtime

BASE=Path(__file__).resolve().parent.parent
load_dotenv(BASE/'.env')
ROOT=Path(os.getenv('WORKSPACE_ROOT',str(BASE/'workspaces'))).resolve();ROOT.mkdir(parents=True,exist_ok=True)
STATE=Path(os.getenv('STATE_ROOT',str(BASE/'.state'))).resolve();STATE.mkdir(parents=True,exist_ok=True)
FRONTEND=os.getenv('FRONTEND_URL','http://localhost:3100')
BACKEND=os.getenv('BACKEND_URL','http://localhost:8100')
GH_ID=os.getenv('GITHUB_CLIENT_ID','');GH_SECRET=os.getenv('GITHUB_CLIENT_SECRET','')
LOCAL=os.getenv('ALLOW_LOCAL_LOGIN','true').lower()=='true'
SECRET=os.getenv('SESSION_SECRET')
if not SECRET:
    secret_file=STATE/'session-secret'
    if not secret_file.exists():atomic_text(secret_file,secrets.token_urlsafe(48));secret_file.chmod(0o600)
    SECRET=secret_file.read_text()
DB=STATE/'sessions.sqlite3'

def db():
    c=sqlite3.connect(DB)
    c.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL, expires REAL NOT NULL)')
    return c

with db() as c:c.execute('DELETE FROM sessions WHERE expires < ?',(time.time(),))
DB.chmod(0o600)
app=FastAPI(title='Schematic2SDN',version='1.1.0')
app.add_middleware(SessionMiddleware,secret_key=SECRET,session_cookie='s2sdn_session',same_site='lax',https_only=BACKEND.startswith('https://'),max_age=86400)
app.add_middleware(CORSMiddleware,allow_origins=[FRONTEND],allow_credentials=True,allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Content-Type'])

@app.middleware('http')
async def origin_guard(request,call_next):
    origin=request.headers.get('origin')
    if request.method in ['POST','PUT','DELETE','PATCH'] and origin and origin!=FRONTEND:
        return Response(json.dumps({'detail':'Untrusted request origin.'}),403,media_type='application/json')
    return await call_next(request)

@app.exception_handler(OperationError)
async def operation_error(request,error):
    return Response(json.dumps({'detail':str(error)}),422,media_type='application/json')

def put_session(request,data,replace=False):
    sid=request.session.get('sid')
    if replace and sid:
        with db() as c:c.execute('DELETE FROM sessions WHERE id=?',(sid,))
        sid=None
    sid=sid or secrets.token_urlsafe(32)
    with db() as c:c.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?)',(sid,json.dumps(data),time.time()+86400))
    request.session.clear();request.session['sid']=sid

def session(request):
    sid=request.session.get('sid')
    if not sid:return {}
    with db() as c:row=c.execute('SELECT data FROM sessions WHERE id=? AND expires>?',(sid,time.time())).fetchone()
    return json.loads(row[0]) if row else {}

def user(request:Request):
    data=session(request)
    if not data.get('user'):raise HTTPException(401,'Sign in first.')
    return data['user']

def safe_id(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',name):raise HTTPException(400,'Use 1–80 letters, digits, underscores, dots, or dashes; begin with a letter or digit.')
    return name

def user_root(u):
    return ROOT/safe_id(u['login'])

def pdir(u,pid):
    safe_id(pid);base=user_root(u).resolve();p=(base/pid).resolve()
    if p.parent!=base:raise HTTPException(400,'Project path escapes workspace.')
    if not p.is_dir():raise HTTPException(404,'No such project.')
    return p

def public_file(project,name,must_exist=True):
    parts=Path(name).parts
    if not parts or any(p.startswith('.') for p in parts) or Path(name).is_absolute():raise HTTPException(400,'Invalid file path.')
    path=(project/name).resolve()
    if not path.is_relative_to(project.resolve()):raise HTTPException(400,'File path escapes project.')
    if must_exist and not path.is_file():raise HTTPException(404,'No such file.')
    return path

def git(project,*args,check=True,env=None):
    try:r=subprocess.run(['git',*args],cwd=project,capture_output=True,text=True,timeout=90,env=env)
    except (FileNotFoundError,subprocess.TimeoutExpired) as e:raise OperationError('Git is unavailable or timed out.') from e
    if check and r.returncode:raise OperationError((r.stderr or r.stdout).strip()[-1500:])
    return r

def init_git(p,u):
    git(p,'init','-b','main');git(p,'config','user.name',u['name']);git(p,'config','user.email',f"{u['login']}@users.noreply.github.com")
    atomic_text(p/'.gitignore','.history/\n.redo/\n*.kicad_prl\n*.lck\n~*\n')
    git(p,'add','-A');git(p,'commit','-m','Create schematic')
    atomic_text(p/'.git'/'s2sdn_created',str(time.time()))

@app.get('/health')
def health():
    return {'status':'ready','kicad':bool(shutil.which(find_cli()) or Path(find_cli()).is_file()),'symbols':bool(library_dir()),'ngspice':bool(shutil.which('ngspice')),'embedded':os.getenv('KICAD_EMBEDDED','false')=='true','image_mode':os.getenv('IMAGE_MODE','circuit'),'vision_model':os.getenv('VISION_MODEL','qwen3-vl:2b-instruct') if os.getenv('IMAGE_MODE','circuit')=='vision' else None}

@app.get('/auth/config')
def auth_config():return {'github':bool(GH_ID and GH_SECRET),'local':LOCAL}

@app.get('/auth/dev')
def local_login(request:Request):
    if not LOCAL:raise HTTPException(403,'Local login is disabled.')
    put_session(request,{'user':{'login':'local','name':'Local User','token':None}},replace=True)
    return {'ok':True}

@app.get('/auth/login')
def login(request:Request,switch:bool=False):
    if not GH_ID or not GH_SECRET:return RedirectResponse(FRONTEND+'/?auth_error=not_configured')
    state=secrets.token_urlsafe(32);data=session(request);data['oauth']={'state':state,'created':time.time()};put_session(request,data)
    return RedirectResponse('https://github.com/login/oauth/authorize?'+urlencode({'client_id':GH_ID,'scope':'repo read:user','state':state,'redirect_uri':BACKEND+'/auth/callback'}))

@app.get('/auth/callback')
async def callback(request:Request,code:str='',state:str='',error:str=''):
    data=session(request);oauth=data.pop('oauth',{})
    put_session(request,data)
    if not state or not secrets.compare_digest(state,oauth.get('state','')) or time.time()-oauth.get('created',0)>600:
        raise HTTPException(400,'Invalid or expired OAuth state.')
    if error or not code:return RedirectResponse(FRONTEND+'/?auth_error=denied')
    async with httpx.AsyncClient(timeout=30) as client:
        r=await client.post('https://github.com/login/oauth/access_token',headers={'Accept':'application/json'},data={'client_id':GH_ID,'client_secret':GH_SECRET,'code':code,'redirect_uri':BACKEND+'/auth/callback'})
        if r.status_code>=300:raise HTTPException(502,'GitHub token exchange failed.')
        token=r.json().get('access_token')
        if not token:raise HTTPException(400,'GitHub did not issue an access token.')
        r=await client.get('https://api.github.com/user',headers={'Authorization':'Bearer '+token})
        if r.status_code>=300:raise HTTPException(502,'GitHub identity lookup failed.')
        identity=r.json();safe_id(identity['login'])
    put_session(request,{'user':{'login':identity['login'],'name':identity.get('name') or identity['login'],'token':token}},replace=True)
    return RedirectResponse(FRONTEND)

@app.get('/auth/me')
def me(u:dict=Depends(user)):return {'login':u['login'],'name':u['name'],'git_linked':bool(u['token'])}

@app.post('/auth/logout')
def logout(request:Request):
    with db() as c:c.execute('DELETE FROM sessions WHERE id=?',(request.session.get('sid'),))
    request.session.clear();return {'ok':True}

class NewProject(BaseModel):name:str

@app.get('/projects')
def projects(u:dict=Depends(user)):
    base=user_root(u)
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith('.')) if base.exists() else []

@app.post('/projects')
def create(body:NewProject,u:dict=Depends(user)):
    name=safe_id(body.name);base=user_root(u);base.mkdir(parents=True,exist_ok=True);p=base/name
    if p.exists():raise HTTPException(409,'Project already exists.')
    try:Schematic.create(p,name);init_git(p,u)
    except Exception:
        if p.is_dir():shutil.rmtree(p)
        raise
    return {'id':name}

@app.delete('/projects/{pid}')
def delete(pid:str,u:dict=Depends(user)):
    p=pdir(u,pid);trash=user_root(u)/'.trash';trash.mkdir(exist_ok=True);dest=trash/f'{pid}-{time.time_ns()}';p.rename(dest)
    return {'deleted':pid,'recoverable':True}

@app.get('/projects/{pid}/files')
def files(pid:str,u:dict=Depends(user)):
    p=pdir(u,pid)
    return sorted(str(f.relative_to(p)) for f in p.rglob('*') if f.is_file() and not any(part.startswith(('.', '~')) for part in f.relative_to(p).parts) and not f.is_symlink() and f.suffix!='.kicad_prl')

@app.get('/projects/{pid}/file')
def file(pid:str,name:str,u:dict=Depends(user)):
    p=pdir(u,pid);path=public_file(p,name)
    data=path.read_bytes()
    media={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif','.pdf':'application/pdf','.docx':'application/octet-stream'}.get(path.suffix.lower(),'text/plain')
    disposition="attachment; filename*=UTF-8''"+urllib.parse.quote(path.name,safe='')
    return Response(data,media_type=media,headers={'Content-Disposition':disposition,'X-Content-SHA256':hashlib.sha256(data).hexdigest()})

class FileText(BaseModel):
    content:str=Field(max_length=5000000)
    expected_sha256:str | None=Field(default=None,pattern=r'^[a-f0-9]{64}$')

@app.put('/projects/{pid}/file')
def save_file(pid:str,name:str,body:FileText,u:dict=Depends(user)):
    p=pdir(u,pid);path=public_file(p,name)
    if path.suffix!='.kicad_sch':raise HTTPException(400,'Source editing supports .kicad_sch files.')
    with project_lock(p):
        prepare_embedded(p)
        before=path.read_text()
        if body.expected_sha256 and hashlib.sha256(path.read_bytes()).hexdigest()!=body.expected_sha256:
            raise HTTPException(409,'The schematic changed since loading Source. Copy your edits, reload Source, then merge and save.')
        try:atomic_text(path,body.content);Schematic(p).graph();remember(p,before,'source edit')
        except Exception:atomic_text(path,before);raise
    refresh_embedded(p,quiet=True)
    return {'saved':name}

@app.get('/projects/{pid}/preview.svg')
def preview(pid:str,u:dict=Depends(user)):return Response(Schematic(pdir(u,pid)).preview(),media_type='image/svg+xml')

@app.get('/projects/{pid}/graph')
def graph(pid:str,u:dict=Depends(user)):return Schematic(pdir(u,pid)).graph()

@app.get('/vision/status')
async def vision_status():
    mode=os.getenv('IMAGE_MODE','circuit')
    if mode in ['ocr','circuit']:return {'ready':bool(shutil.which('tesseract')),'mode':mode,'model':None,'models':[],'connectivity_verified':False}
    model=os.getenv('VISION_MODEL','qwen3-vl:2b-instruct')
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r=await client.get((os.getenv('VISION_OLLAMA_URL') or os.getenv('OLLAMA_URL','http://localhost:11434')).rstrip('/')+'/api/tags')
            r.raise_for_status()
            models=[m.get('name') for m in r.json().get('models',[])]
        return {'ready':model in models,'mode':'vision','model':model,'models':models,'accuracy_verified':False}
    except Exception:return {'ready':False,'mode':'vision','model':model,'models':[],'accuracy_verified':False}

@app.get('/projects/{pid}/netlist')
def netlist(pid:str,u:dict=Depends(user)):return Response(Schematic(pdir(u,pid)).netlist(),media_type='application/xml')

@app.get('/projects/{pid}/validate')
def validate(pid:str,u:dict=Depends(user)):return Schematic(pdir(u,pid)).erc()

@app.get('/projects/{pid}/details')
def details(pid:str,u:dict=Depends(user)):
    p=pdir(u,pid);sch=Schematic(p)
    with project_lock(p):
        graph=sch.graph()
        try:erc=sch.erc()
        except OperationError as e:erc={'status':'unavailable','passed':False,'violations':[],'error':str(e)}
    for c in graph['components']:
        part=c['fields'].get('LCSC',c['fields'].get('LCSC Part',''))
        c.update({'lcsc':part or 'Not specified','supplier':'LCSC search','supplierUrl':'https://www.lcsc.com/search?q='+urllib.parse.quote(part or c['value']),'unitPrice':'Not queried','stock':'Not queried'})
    revisions=[]
    r=git(p,'log','--format=%h%x1f%s%x1f%aI%x1f%an','-n','25',check=False)
    for line in r.stdout.splitlines():
        parts=line.split('\x1f')
        if len(parts)==4:revisions.append(dict(zip(['hash','msg','time','author'],parts)))
    file_list=[{'name':n,'size':(p/n).stat().st_size} for n in files(pid,u)]
    return {'id':pid,'name':pid,'activeRevision':revisions[0]['hash'] if revisions else None,'components':graph['components'],'nets':graph['nets'],'checks':erc['violations'],'validation':{k:v for k,v in erc.items() if k!='report'},'revisions':revisions,'files':file_list,'hierarchy':[{'name':pid,'pages':len(list(p.glob('*.kicad_sch'))),'active':True}],'hasSch':True}

@app.get('/libraries/footprints')
def footprint_search(q:str='',u:dict=Depends(user)):
    from .footprints import search
    if len(q)>200:raise OperationError('Footprint search is limited to 200 characters.')
    return {'items':search(q)}

@app.get('/libraries/footprint')
def footprint_details(id:str,u:dict=Depends(user)):
    from .footprints import details
    return details(id)

@app.get('/libraries/symbols')
def symbol_search(q:str='',u:dict=Depends(user)):
    if len(q)>200:raise OperationError('Search query is limited to 200 characters.')
    tokens = q.strip().split()
    if not tokens:return {'items':[]}
    db_path = Path(__file__).resolve().parents[2] / 'libraries' / 'index' / 'components.db'
    if not db_path.exists():return {'items':[]}
    try:
        import sqlite3
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.cursor()
            clause = " AND ".join(["(name LIKE ? OR keywords LIKE ? OR description LIKE ? OR lib_id LIKE ?)"] * len(tokens))
            params = []
            for t in tokens:
                p = f'%{t}%'
                params.extend([p, p, p, p])
            cur.execute(f"SELECT lib_id, name, library, description, pin_count, footprint FROM symbols WHERE {clause} LIMIT 50", params)
            rows = cur.fetchall()
            return {'items':[{'lib_id':r[0],'name':r[1],'library':r[2],'description':r[3],'pin_count':r[4],'footprint':r[5]} for r in rows]}
    except Exception as e:
        return {'items':[],'error':str(e)}

@app.post('/projects/{pid}/export/specctra')
def export_specctra(pid:str,plan:dict,u:dict=Depends(user)):
    from .specctra import export
    try:
        with project_lock(pdir(u,pid)):
            data=export(Schematic(pdir(u,pid)).graph(),plan)
    except (KeyError,ValueError,subprocess.TimeoutExpired) as e:raise OperationError('Invalid PCB plan or timed-out export: '+str(e))
    return Response(data,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{pid}-specctra.zip"'})

@app.get('/projects/{pid}/export/edif')
def export_edif(pid:str,u:dict=Depends(user)):
    return Response(edif(pid,Schematic(pdir(u,pid)).graph()),media_type='application/edif',headers={'Content-Disposition':f'attachment; filename="{pid}.edf"'})

@app.get('/projects/{pid}/export/orcad-bundle')
def export_orcad_handoff(pid:str,u:dict=Depends(user)):
    from .orcad_handoff import bundle as orcad_bundle
    data=orcad_bundle(pid,Schematic(pdir(u,pid)).graph())
    return Response(data,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{pid}-orcad-handoff.zip"'})

@app.get('/projects/{pid}/export/orcad-tcl')
def orcad(pid:str,u:dict=Depends(user)):
    pdir(u,pid);raise HTTPException(409,'Native OrCAD .DSN conversion requires OrCAD Capture. Use the connectivity-preserving EDIF download.')

def simulation_controls(p):
    path=p/'.simulation.json'
    data=json.loads(path.read_text()) if path.exists() else {}
    return {'models':[line for line in data.get('directives',[]) if line.lower().startswith('.model ')]}

@app.get('/projects/{pid}/export/spice')
def export_spice(pid:str,u:dict=Depends(user)):
    p=pdir(u,pid);text=spice(Schematic(p).graph(),simulation_controls(p))
    return Response(text,media_type='text/plain',headers={'Content-Disposition':f'attachment; filename="{pid}.cir"'})

@app.get('/projects/{pid}/simulate')
def simulation(pid:str,step:str='10u',stop:str='10m',u:dict=Depends(user)):
    p=pdir(u,pid)
    result=simulate(Schematic(p).graph(),{**simulation_controls(p),'step':step,'stop':stop});result['title']+=f': {pid}';return result

@app.get('/projects/{pid}/integrations/qucs-s/simulate')
def qucs_simulation(pid:str,step:str='10u',stop:str='10m',u:dict=Depends(user)):
    p=pdir(u,pid)
    with project_lock(p):return simulate_qucs(p,{**simulation_controls(p),'step':step,'stop':stop})

@app.post('/projects/{pid}/waveforms/import')
async def import_waveform(pid:str,name:str,request:Request,u:dict=Depends(user)):
    pdir(u,pid)
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>25*1024*1024:raise HTTPException(413,'Maximum waveform size is 25 MB.')
    from .waveforms import csv_waveform,raw_waveform
    if Path(name).suffix.lower()=='.raw':return await asyncio.to_thread(raw_waveform,bytes(data))
    if Path(name).suffix.lower()=='.csv':return await asyncio.to_thread(csv_waveform,bytes(data))
    raise HTTPException(400,'Choose an uncompressed .raw or waveform .csv file.')

@app.get('/integrations')
def integration_status(u:dict=Depends(user)):
    desktop=bridge_status(STATE)
    return {'desktop':desktop,'applications':[{'id':key,**info,'host_installed':bool(desktop.get('applications',{}).get(key,{}).get('installed')),'bundled':key in ['kicad','ngspice'] or key=='qucs-s' and bool(shutil.which('qucs-s'))} for key,info in TOOLS.items()]}

@app.get('/projects/{pid}/integrations/{tool}/bundle')
def integration_bundle(pid:str,tool:str,u:dict=Depends(user)):
    p=pdir(u,pid)
    with project_lock(p):data=bundle(tool,p,simulation_controls(p))
    return Response(data,media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{pid}-{tool}.zip"'})

@app.post('/projects/{pid}/integrations/{tool}/open')
def integration_open(pid:str,tool:str,u:dict=Depends(user)):
    p=pdir(u,pid)
    with project_lock(p):
        prepare_embedded(p)
        return enqueue(STATE,u['login'],tool,p,simulation_controls(p))

@app.get('/integrations/jobs/{jid}')
def integration_job(jid:str,u:dict=Depends(user)):
    return job_result(STATE,u['login'],jid)

@app.get('/projects/{pid}/git/status')
def git_status(pid:str,u:dict=Depends(user)):
    p=pdir(u,pid);marker=p/'.git'/'s2sdn_created';repo=p/'.git'/'s2sdn_repo'
    mt=[f.stat().st_mtime for f in p.rglob('*') if f.is_file() and not any(x.startswith('.') for x in f.relative_to(p).parts)]
    return {'dirty':bool(git(p,'status','--porcelain',check=False).stdout.strip()),'created':marker.read_text() if marker.exists() else None,'modified':max(mt) if mt else None,'repo':repo.read_text() if repo.exists() else None}

class Commit(BaseModel):message:str=Field(default='Update schematic',min_length=1,max_length=500)

@app.post('/projects/{pid}/git/commit')
def commit(pid:str,body:Commit,u:dict=Depends(user)):
    p=pdir(u,pid);git(p,'add','-A');r=git(p,'commit','-m',body.message,check=False)
    if r.returncode and 'nothing to commit' not in r.stdout:raise OperationError(r.stderr or r.stdout)
    return {'committed':r.returncode==0,'hash':git(p,'rev-parse','--short','HEAD').stdout.strip()}

@app.post('/projects/{pid}/git/push')
async def push(pid:str,body:Commit,u:dict=Depends(user)):
    if not u['token']:raise HTTPException(400,'Sign in with GitHub to push. Local commits are available without GitHub.')
    p=pdir(u,pid);await asyncio.to_thread(commit,pid,body,u);repo=f"{u['login']}/s2sdn-{pid}"
    h={'Authorization':'Bearer '+u['token'],'Accept':'application/vnd.github+json'}
    async with httpx.AsyncClient(timeout=30) as client:
        r=await client.get('https://api.github.com/repos/'+repo,headers=h)
        if r.status_code==404:
            r=await client.post('https://api.github.com/user/repos',headers=h,json={'name':'s2sdn-'+pid,'private':True})
        if r.status_code>=300:raise HTTPException(502,'GitHub repository lookup/creation failed.')
    with tempfile.TemporaryDirectory() as td:
        helper=Path(td)/'askpass.py';helper.write_text('#!/usr/bin/env python3\nimport os,sys\nprint("x-access-token" if "Username" in sys.argv[1] else os.environ["S2SDN_GIT_TOKEN"])\n');helper.chmod(0o700)
        env={**os.environ,'GIT_ASKPASS':str(helper),'GIT_TERMINAL_PROMPT':'0','S2SDN_GIT_TOKEN':u['token']}
        r=await asyncio.to_thread(git,p,'push','https://github.com/'+repo+'.git','HEAD:main',check=False,env=env)
        if r.returncode:raise HTTPException(502,(r.stderr or 'Git push failed.').replace(u['token'],'[redacted]'))
    url='https://github.com/'+repo;atomic_text(p/'.git'/'s2sdn_repo',url);return {'repo':url}

def attachment_name(name):
    name=unicodedata.normalize('NFC',name)
    if (not name or len(name.encode('utf-8'))>220 or name.startswith('.') or name.endswith((' ','.'))
        or any(ord(c)<32 or c in '/\\<>:"|?*' for c in name)
        or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',name.split('.')[0],re.I)):
        raise HTTPException(400,'Use a normal filename without path separators or reserved characters (up to 220 UTF-8 bytes). Spaces are supported.')
    return name

@app.post('/projects/{pid}/attachments')
async def attachment(pid:str,name:str,request:Request,u:dict=Depends(user)):
    p=pdir(u,pid);name=attachment_name(name)
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>25*1024*1024:raise HTTPException(413,'Maximum upload size is 25 MB.')
    if not data:raise HTTPException(400,'Empty upload.')
    folder=p/'references';folder.mkdir(exist_ok=True);path=public_file(p,'references/'+name,must_exist=False);path.write_bytes(data)
    return {'path':'references/'+name,'size':len(data)}

class Chat(BaseModel):
    project:str | None=None
    message:str=Field(min_length=1,max_length=50000)
    attachments:list[str]=Field(default_factory=list,max_length=10)
    recognition_mode:Literal['ocr','circuit','vision'] | None=None
    output_tool:Literal['kicad','ngspice','ltspice','qucs-s'] | None=None
    create_new_on_conflict:bool=False

@app.get('/models/status')
async def models_status(u:dict=Depends(user)):return await model_runtime.status()

@app.get('/projects/{pid}/vision/analyze')
def image_analysis(pid:str,name:str,u:dict=Depends(user)):
    from .vision_local import analyze
    path=public_file(pdir(u,pid),name)
    if path.suffix.lower() not in ['.png','.jpg','.jpeg','.webp','.bmp']:raise HTTPException(400,'Choose an image attachment.')
    return analyze(path)

@app.post('/ai/plan')
async def model_plan(body:Chat,u:dict=Depends(user)):
    if not body.project:raise HTTPException(400,'Select a project.')
    p=pdir(u,body.project)
    current=await asyncio.to_thread(lambda:Schematic(p).graph())
    return await model_runtime.plan(body.message,current)

def requested_output(result,p,tool):
    if not tool or not result.get('edits'):return result
    try:
        from .integrations import artifacts
        with project_lock(p):artifacts(tool,p,simulation_controls(p))
        result['output']={'tool':tool,'ready':True,'url':f'/projects/{p.name}/integrations/{tool}/bundle','filename':f'{p.name}-{tool}.zip'}
    except OperationError as e:
        result['output']={'tool':tool,'ready':False,'error':str(e)}
        result['reply']=result.get('reply','')+' Output export failed: '+str(e)
    return result

@app.post('/ai/chat')
async def chat(body:Chat,u:dict=Depends(user)):
    p=pdir(u,body.project) if body.project else None
    paths=[public_file(p,n) for n in body.attachments] if p else []
    options={'recognition_mode':body.recognition_mode} if body.recognition_mode else {}
    try:result=await execute(body.message,p,paths,before_mutation=prepare_embedded,**options)
    except OperationError as e:
        if not body.create_new_on_conflict or paths or not str(e).startswith('Import conflicts with existing'):
            raise
        # Creation requests never overwrite an existing component; isolate a conflicting design.
        name='Circuit-'+secrets.token_hex(4)
        create(NewProject(name=name),u);p=pdir(u,name)
        try:result=await execute(body.message,p,before_mutation=prepare_embedded,**options)
        except Exception:
            shutil.rmtree(p);raise
        result['project']=name
        result['reply']='Created '+name+' to preserve the existing project. '+result.get('reply','')
    if result.get('edits'):
        reloaded=await asyncio.to_thread(refresh_embedded,p,quiet=True)
        result['editor_reloaded']=reloaded
        if os.getenv('KICAD_EMBEDDED','false')=='true' and not reloaded:
            result.setdefault('warnings',[]).append('Changes saved; activate the project to reload the embedded editor.')
    return await asyncio.to_thread(requested_output,result,p,body.output_tool)

class Proposal(BaseModel):
    circuit:Circuit
    output_tool:Literal['kicad','ngspice','ltspice','qucs-s'] | None=None

@app.post('/projects/{pid}/import')
def apply_import(pid:str,body:Proposal,u:dict=Depends(user)):
    p=pdir(u,pid)
    with project_lock(p):
        prepare_embedded(p)
        sch=Schematic(p);before=sch.path.read_text()
        try:edits=apply_circuit(sch,body.circuit);sch.save();sch.graph();remember(p,before,'Apply reviewed import')
        except Exception:atomic_text(sch.path,before);raise
    refresh_embedded(p,quiet=True)
    return requested_output({'edits':edits,'validation':sch.erc()},p,body.output_tool)

ACTIVE=STATE/'active-project'
# Desktop processes do not survive a service restart; discard the stale activation marker.
if os.getenv('KICAD_EMBEDDED','false')=='true':ACTIVE.unlink(missing_ok=True)
DESKTOP_LOCK=threading.RLock()

def display_command(args,timeout=10):
    try:r=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env={**os.environ,'DISPLAY':os.getenv('DISPLAY',':1')})
    except (FileNotFoundError,subprocess.TimeoutExpired) as e:raise OperationError('Embedded KiCad is unavailable. Start Docker or use native KiCad.') from e
    if r.returncode:raise OperationError((r.stderr or 'Embedded KiCad operation failed.').strip()[-1000:])
    return r

def prepare_embedded(p):
    with DESKTOP_LOCK:return _prepare_embedded(p)

def _prepare_embedded(p):
    if os.getenv('KICAD_EMBEDDED','false')!='true' or not ACTIVE.exists() or ACTIVE.read_text()!=str(p):return
    result=display_command(['xdotool','search','--onlyvisible','--class','eeschema'])
    windows=result.stdout.splitlines()
    if not windows:raise OperationError('The active editor is unavailable; activate the project again.')
    display_command(['xdotool','windowactivate','--sync',windows[0]])
    display_command(['xdotool','key','--clearmodifiers','ctrl+s'])
    time.sleep(0.3)

def refresh_embedded(p,quiet=False):
    with DESKTOP_LOCK:return _refresh_embedded(p,quiet)

def _refresh_embedded(p,quiet=False):
    if os.getenv('KICAD_EMBEDDED','false')!='true':
        if quiet:return False
        raise OperationError('Embedded KiCad is not enabled. Start the Docker package or open native KiCad.')
    if quiet and (not ACTIVE.exists() or ACTIVE.read_text()!=str(p)):return False
    sch=Schematic(p)
    try:
        # switch-project performs a graceful close and reopens the file; never kill an unsaved editor.
        display_command(['/usr/local/bin/switch-project.sh',str(sch.path)],timeout=15)
    except OperationError:
        if quiet:return False
        raise
    atomic_text(ACTIVE,str(p));return True

@app.post('/projects/{pid}/activate')
def activate(pid:str,u:dict=Depends(user)):
    p=pdir(u,pid)
    with DESKTOP_LOCK:
        if ACTIVE.exists():
            old=Path(ACTIVE.read_text())
            if old==p:
                try:
                    r=display_command(['xdotool','search','--onlyvisible','--class','eeschema'])
                    if r.stdout.strip():return {'status':'already_active'}
                except OperationError:pass
            if old.is_dir():prepare_embedded(old)
        refresh_embedded(p)
    return {'status':'activated'}

@app.post('/projects/{pid}/open-native')
def native(pid:str,u:dict=Depends(user)):
    p=pdir(u,pid)
    if os.getenv('KICAD_EMBEDDED','false')=='true':refresh_embedded(p);return {'status':'Opened in embedded KiCad'}
    if shutil.which('open'):
        r=subprocess.run(['open','-a','KiCad',str(Schematic(p).path)],capture_output=True,text=True)
        if r.returncode:raise OperationError(r.stderr or 'Native KiCad could not open.')
    else:raise OperationError('Native opening is supported on macOS. Use embedded KiCad on other systems.')
    return {'status':'Opened in native KiCad'}

@app.post('/projects/{pid}/control')
def control(pid:str,action:str,u:dict=Depends(user)):
    p=pdir(u,pid)
    if action in ['undo','redo']:
        with project_lock(p):
            prepare_embedded(p);edits=undo_redo(p,action=='redo')
        refresh_embedded(p,quiet=True);return {'action':action,'edits':edits}
    keys={'zoom_in':'F1','zoom_out':'F2','zoom_fit':'ctrl+Home','redraw':'F5','save':'ctrl+s','grid':'F6'}
    if action not in keys:raise HTTPException(400,'Unknown control action.')
    if not ACTIVE.exists() or ACTIVE.read_text()!=str(p):raise OperationError('Activate this project in embedded KiCad before controlling it.')
    with DESKTOP_LOCK:
        result=display_command(['xdotool','search','--onlyvisible','--class','eeschema']);windows=result.stdout.splitlines()
        if not windows:raise OperationError('KiCad editor window is unavailable.')
        display_command(['xdotool','windowactivate','--sync',windows[0]])
        display_command(['xdotool','key','--clearmodifiers',keys[action]])
        return {'action':action,'key':keys[action]}
@app.get('/projects/{pid}/events')
async def events(pid:str,request:Request,u:dict=Depends(user)):
    p=pdir(u,pid)
    def stamp():
        try:return max((f.stat().st_mtime_ns for f in p.rglob('*') if f.is_file() and not any(x.startswith('.') for x in f.relative_to(p).parts)),default=0)
        except FileNotFoundError:return 0
    async def gen():
        last=stamp();yield 'data: ready\n\n'
        while not await request.is_disconnected():
            await asyncio.sleep(1)
            now=stamp()
            if now!=last:last=now;yield 'event: changed\ndata: 1\n\n'
            else:yield ': heartbeat\n\n'
    return StreamingResponse(gen(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

DATASETS=Path(os.getenv('DATASET_ROOT',str(BASE/'datasets')))

@app.get('/datasets/summary')
def dataset_summary(u:dict=Depends(user)):
    samples=list(DATASETS.glob('synthetic/*/circuit.json'))
    provided=DATASETS/'provided'/'audit.json'
    audit=json.loads(provided.read_text()) if provided.exists() else {'accepted':0,'groups':0,'custom_training_ready':False}
    return {'datasets':[{'name':'Verified synthetic KiCad circuits','count':len(samples),'types':['voltage divider','RC lowpass']},{'name':'Provided image/JSON/SPICE pairs','count':audit['accepted'],'audit':audit}],'training':{'status':'not_trained','description':'Pretrained models run inference. No custom vision checkpoint is verified. GPU training uses a separate environment and must pass held-out graph evaluations.'},'external_corpora':[{'name':name,'installed':False,'count':0} for name in ['CGHD','AMSnet 2.0','Masala-CHAI']]}

@app.post('/datasets/synthetic/generate')
def generate(count:int=4,u:dict=Depends(user)):
    if count<1 or count>20:raise HTTPException(400,'Generate 1–20 samples per request.')
    samples=[]
    for i in range(count):
        name=f'SYNTH_{time.time_ns()}';folder=DATASETS/'synthetic'/name;kind='divider' if i%2==0 else 'rc'
        Schematic.create(folder,name);sch=Schematic(folder);apply_circuit(sch,template(kind));sch.save();graph=sch.graph()
        svg=sch.preview()
        atomic_text(folder/'circuit.json',json.dumps(graph,indent=2));atomic_text(folder/'circuit.svg',svg);atomic_text(folder/'circuit.cir',spice(graph));atomic_text(folder/'circuit.edf',edif(name,graph))
        if shutil.which('rsvg-convert'):
            from .dataset_render import raster
            (folder/'circuit.png').write_bytes(raster(sch,svg))
        samples.append({'sample_id':name,'type':kind,'components':len(graph['components']),'nets':len(graph['nets']),'validated':sch.erc()['passed']})
    return {'generated':len(samples),'samples':samples}
