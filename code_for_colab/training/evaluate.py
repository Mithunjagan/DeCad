#!/usr/bin/env python3
"""Evaluate a configured vision server against untouched, reviewed test pairs."""
import argparse,asyncio,hashlib,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.ingestion import Circuit,extract_image
from app.simulation import number
from app.ground import reference_name

def value(text):
 try:return number(text.removeprefix('DC '))
 except Exception:return text.strip()

def metrics(expected,predicted):
 def components(circuit):
  return {(c.ref,value(c.value),c.library) for c in circuit.components}
 def partitions(circuit):
  return {(net.name==reference_name(n.name for n in circuit.nets),tuple(sorted((node.ref,node.pin) for node in net.nodes))) for net in circuit.nets}
 def scores(truth,guess):
  matched=len(truth&guess);precision=matched/len(guess) if guess else float(not truth);recall=matched/len(truth) if truth else float(not guess)
  return {'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0}
 tc,gc=components(expected),components(predicted);tn,gn=partitions(expected),partitions(predicted)
 return {'component_ref_value_library':scores(tc,gc),'pin_net_ground_partitions':scores(tn,gn),'exact_graph_match':tc==gc and tn==gn}

async def run(args):
 if os.getenv('IMAGE_MODE')!='vision':raise SystemExit('Set IMAGE_MODE=vision and configure the evaluated VISION_MODEL/server explicitly.')
 root=args.dataset.resolve();records=[json.loads(line) for line in (root/'test.jsonl').read_text().splitlines() if line.strip()]
 train=[json.loads(line) for line in (root/'train.jsonl').read_text().splitlines() if line.strip()]
 validation=[json.loads(line) for line in (root/'validation.jsonl').read_text().splitlines() if line.strip()]
 if {r['group'] for r in records}&{r['group'] for r in train+validation}:raise SystemExit('Test circuit groups overlap training/validation.')
 if not records:raise SystemExit('Test split is empty.')
 checks=[]
 for record in records[:args.limit]:
  path=(root/record['image']).resolve()
  if not path.is_relative_to(root) or not path.is_file():raise SystemExit('Unsafe or missing test image.')
  if record.get('image_source_review')!='verified' or not record.get('netlist_equivalence_verified'):raise SystemExit('Test image/netlist annotations must be reviewed and verified.')
  if hashlib.sha256(path.read_bytes()).hexdigest()!=record['image_sha256']:raise SystemExit('Test image hash mismatch.')
  started=time.monotonic()
  try:
   predicted=await extract_image(path);truth=Circuit.model_validate(record['circuit'])
   checks.append({'sample_id':record['sample_id'],'metrics':metrics(truth,predicted),'prediction':predicted.model_dump(),'elapsed_seconds':time.monotonic()-started})
  except Exception as e:checks.append({'sample_id':record['sample_id'],'failed':True,'reason':str(e),'elapsed_seconds':time.monotonic()-started})
 exact=sum(check.get('metrics',{}).get('exact_graph_match',False) for check in checks)
 report={'model':os.getenv('VISION_MODEL'),'samples':len(checks),'failed':sum(check.get('failed',False) for check in checks),'exact_graph_matches':exact,'exact_graph_match_rate':exact/len(checks),'release_approved':False,'note':'Measured graph accuracy only. Native ERC, simulation equivalence, hardware limits and manual failure review remain separate release gates.','checks':checks}
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=20);args=p.parse_args()
 if args.limit<1 or args.limit>1000:p.error('Evaluate 1–1000 images per run.')
 asyncio.run(run(args))
