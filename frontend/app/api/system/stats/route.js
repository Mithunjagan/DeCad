import {execFile} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

export const runtime='nodejs';
export const dynamic='force-dynamic';
const key=Symbol.for('decad.system.telemetry');
const cache=globalThis[key]||(globalThis[key]={sample:null,cpu:null,pending:null,at:0});
const headers={'Cache-Control':'no-store'};

function collect(){
  if(cache.sample&&Date.now()-cache.at<2000)return Promise.resolve(cache.sample);
  if(cache.pending)return cache.pending;
  cache.pending=new Promise((resolve,reject)=>{
    const root=path.resolve(process.cwd(),'..');
    const python=process.env.S2SDN_METRICS_PYTHON||path.join(root,'backend','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
    if(!fs.existsSync(python)){reject(Error('System metrics Python is unavailable.'));return;}
    const child=execFile(python,[path.join(root,'backend','app','system_metrics.py')],
      {cwd:root,windowsHide:true,timeout:5000,maxBuffer:128*1024,encoding:'utf8'},(error,stdout)=>{
        if(error){reject(Error('System metrics could not be read.'));return;}
        try{
          const data=JSON.parse(stdout);cache.cpu=data._cpu_counters;delete data._cpu_counters;
          cache.sample=data;cache.at=Date.now();resolve(data);
        }catch{reject(Error('System metrics returned an unreadable sample.'));}
      });
    child.stdin.on('error',()=>{});
    child.stdin.end(JSON.stringify({previous_cpu:cache.cpu}));
  }).finally(()=>{cache.pending=null;});
  return cache.pending;
}

export async function GET(request){
  // Reuse the existing authenticated session before collecting any host data.
  try{
    const auth=await fetch(`${process.env.INTERNAL_API_URL||'http://localhost:8100'}/auth/me`,
      {headers:{cookie:request.headers.get('cookie')||''},cache:'no-store',signal:AbortSignal.timeout(2500)});
    if(!auth.ok)return Response.json({detail:'Sign in to view system resources.'},{status:auth.status===401?401:503,headers});
    return Response.json(await collect(),{headers});
  }catch{return Response.json({detail:'Live system readings are unavailable. Retrying automatically.'},{status:503,headers});}
}
