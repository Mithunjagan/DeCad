"""Serialize the post-recognition XML, real CAD reopen and unseen raster checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/upgrade-20261024'
sys.path.insert(0,str(ROOT/'backend'))
from recognition_provenance import snapshot


def run(command,log):
    print('Running',log.name,flush=True)
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(c) for c in command],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(log.name+' failed; inspect its receipt')


if __name__=='__main__':
    gate=json.loads((OUT/'final-fresh/gate.json').read_text())
    assert gate['passed'] and gate['fresh_ocr'],gate.get('errors')
    assert snapshot()==gate['source_snapshot'],'Recognition code changed after the gate'
    os.environ.update(KICAD_CLI='D:/KICAD/bin/kicad-cli.exe',KICAD_SYMBOL_DIR='D:/KICAD/share/kicad/symbols',
                      KICAD_FOOTPRINT_DIR='D:/KICAD/share/kicad/footprints',KICAD_PYTHON='D:/KICAD/bin/python.exe')
    cpu=ROOT/'backend/.venv/Scripts/python.exe'
    run([cpu,'tools/eval/tonight_corpus.py','--phase',OUT/'final-fresh','--out',OUT/'xml-corpus'],OUT/'xml-corpus.log')
    xml=json.loads((OUT/'xml-corpus/report.json').read_text())
    old_xml=json.loads((ROOT/'evidence/precision-20261023/xml-corpus/report.json').read_text())
    old_passed={name for name,row in old_xml['xml_cases'].items() if row['passed']}
    new_passed={name for name,row in xml['xml_cases'].items() if row['passed']}
    assert old_passed<=new_passed,'A previously valid raw XML export was lost'
    run([cpu,'tools/eval/observed_export_gate.py','--phase',OUT/'final-fresh','--out',OUT/'native-exports'],OUT/'native-exports.log')
    run([sys.executable,'tools/eval/precision_demo.py','--automatic','--out',OUT/'unseen-automatic'],OUT/'unseen-automatic.log')
    unseen=json.loads((OUT/'unseen-automatic/report.json').read_text())
    assert unseen['literal']['component_detection']['tp']==8
    assert unseen['literal']['physical_pin_coverage']['tp']>=18
    assert unseen['symmetric_terminal_equivalence']['topology_pairwise']['fp']==0
    assert unseen['faculty']['passed']
    assert unseen['providers'] and all('CUDAExecutionProvider' in values for values in unseen['providers'].values())
    assert snapshot()==gate['source_snapshot'],'Source changed during readback verification'
    digest=hashlib.sha256((ROOT/'checkpoints/schematic-ocr/model.onnx').read_bytes()).hexdigest()
    assert digest==gate['protected_model_sha256']
    receipt={'passed':True,'source_unchanged':True,'protected_model_sha256':digest,
             'xml':json.loads((OUT/'xml-corpus/report.json').read_text())['xml_passed'],
             'native_readbacks':json.loads((OUT/'native-exports/report.json').read_text())['passed'],
             'unseen_fresh':json.loads((OUT/'unseen-automatic/report.json').read_text())['fresh_ocr']}
    (OUT/'post-verification.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
