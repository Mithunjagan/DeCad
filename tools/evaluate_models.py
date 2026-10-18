#!/usr/bin/env python3
"""Evaluate actual model-backed planning against held-out requirements and solver results."""
import argparse,asyncio,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.model_runtime import plan
from app.assistant import apply_circuit
from app.ingestion import Circuit
from app.engine import Schematic
from app.simulation import simulate,number

CASES=[
 ('Make a divider powered by 3.3V with R1 4.7k and R2 22k.',{'V1':'3.3','R1':'4.7k','R2':'22k'},3.3*22000/26700),
 ('I need an RC lowpass using V1 5, R1 2.2k, C1 220nF.',{'V1':'5','R1':'2.2k','C1':'220nF'},5),
 ('Build a voltage divider V1 12, R1 10k, R2 10k.',{'V1':'12','R1':'10k','R2':'10k'},6),
]
async def evaluate(out):
 results=[]
 for i,(prompt,expected,target) in enumerate(CASES):
  started=time.monotonic()
  try:
   response=await plan(prompt,{'components':[],'nets':[]});circuit=Circuit.model_validate(response['proposal'])
   values={c.ref:number(c.value) for c in circuit.components};correct=values=={r:number(v) for r,v in expected.items()}
   with tempfile.TemporaryDirectory() as td:
    project=Path(td)/f'Eval{i}';Schematic.create(project,project.name);sch=Schematic(project);apply_circuit(sch,circuit);sch.save();graph=sch.graph();erc=sch.erc();wave=simulate(graph);vout=wave['data'][-1]['vout']
   passed=correct and erc['passed'] and abs(vout-target)<max(1e-4,abs(target)*1e-4)
   results.append({'prompt':prompt,'passed':passed,'exact_values':correct,'erc_passed':erc['passed'],'vout':vout,'expected_vout':target,'model':response['inference']['model'],'elapsed_seconds':round(time.monotonic()-started,2)})
  except Exception as e:results.append({'prompt':prompt,'passed':False,'error':str(e),'elapsed_seconds':round(time.monotonic()-started,2)})
 report={'task':'template planning','cases':len(results),'passed':sum(r['passed'] for r in results),'results':results,'coverage':'Three controlled requests; not a general image-to-netlist accuracy benchmark.'};out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
 if report['passed']!=report['cases']:raise SystemExit(1)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('model-evaluation.json'));args=parser.parse_args();asyncio.run(evaluate(args.output))
