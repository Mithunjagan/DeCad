#!/usr/bin/env python3
"""Check recorded release evidence. Never substitutes for native acceptance runs."""
import argparse,json
from pathlib import Path

REQUIRED=('specctra_router_roundtrip','macos_native_acceptance','windows_native_acceptance','linux_native_acceptance',
          'current_ui_acceptance','ltspice_roundtrip','hardware_performance',
          'dataset_license_review','vision_failure_review','gpu_training_validation')

def check(root):
 blockers=[]
 def load(path):
  try:return json.loads((root/path).read_text())
  except (OSError,ValueError):return {}
 evidence=load('release-evidence.json')
 for name in REQUIRED:
  entry=evidence.get(name,{})
  artifact=entry.get('artifact','')
  resolved=(root/artifact).resolve()
  if entry.get('status')!='passed' or not entry.get('reviewer') or not entry.get('date') or not artifact or not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
   blockers.append(name+': recorded review and local evidence artifact required')
 training=load('checkpoints/circuit-lora/training-report.json')
 if training.get('status')!='trained_not_release_approved' or training.get('training_pairs',0)<100:
  blockers.append('custom training: completed training report required')
 if not (root/'checkpoints/circuit-lora/adapter/adapter_config.json').is_file() or not list((root/'checkpoints/circuit-lora/adapter').glob('*.safetensors')):
  blockers.append('custom training: adapter configuration and safetensors weights required')
 vision=load('vision-evaluation.json')
 # Conservative provisional release policy; approval also requires failure review.
 if vision.get('samples',0)<100 or vision.get('failed',1)!=0 or vision.get('exact_graph_match_rate',0)<0.99:
  blockers.append('vision: at least 100 held-out cases, zero extraction failures and >=99% exact graph matches required by provisional policy')
 checks=vision.get('checks',[])
 measured=sum(x.get('metrics',{}).get('exact_graph_match') is True for x in checks)
 if len(checks)!=vision.get('samples') or len({x.get('sample_id') for x in checks})!=len(checks) or any(not x.get('sample_id') for x in checks):
  blockers.append('vision: complete per-sample results with unique sample identifiers required')
 if not checks or vision.get('exact_graph_match_rate')!=measured/len(checks) or vision.get('failed')!=sum(x.get('failed',False) is True for x in checks):
  blockers.append('vision: aggregate metrics must match per-sample results')
 live=load('live-acceptance.json')
 if live.get('passed',0)<12 or len(live.get('checks',[]))!=live.get('passed') or any(x.get('passed') is not True for x in live.get('checks',[])):
  blockers.append('core live acceptance: successful current API evidence required')
 return {'ready_for_release_review':not blockers,'blockers':blockers,
         'note':'Checks recorded artifacts only. This does not certify authenticity, safety, accuracy or every machine. Native acceptance and accountable human review remain required.'}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path)
 a=p.parse_args();result=check(a.root.resolve())
 if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2));raise SystemExit(0 if result['ready_for_release_review'] else 1)
