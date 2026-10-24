"""Serialize full suites, fresh affected-case OCR, then all-corpus readback.

Unchanged cases retain cached raster postprocessing provenance. This is never
reported as a fresh eighteen-case OCR run.
"""
import json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tools/eval')]
from recognition_provenance import snapshot
from closure_checks import closure_retained
from native_recognition_gate import measure
from recognition_gate import regressions
from benchmark_paths import prediction_path

OUT=ROOT/'evidence/closure-20261024';BASE=ROOT/'evidence/upgrade-20261024/final-fresh'
def read(p):return json.loads(p.read_text())
def run(command,name):
    print('Running',name,flush=True)
    with (OUT/(name+'.log')).open('w',encoding='utf-8') as stream:
        p=subprocess.run(list(map(str,command)),cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError(name+' failed')

if __name__=='__main__':
    os.environ.update(PYTHONPATH=str(ROOT/'backend'),PYTHONIOENCODING='utf-8',KICAD_CLI='D:/KICAD/bin/kicad-cli.exe',KICAD_SYMBOL_DIR='D:/KICAD/share/kicad/symbols',KICAD_FOOTPRINT_DIR='D:/KICAD/share/kicad/footprints',KICAD_PYTHON='D:/KICAD/bin/python.exe')
    cpu=ROOT/'backend/.venv/Scripts/python.exe';frozen=snapshot()
    run([cpu,'-m','pytest','backend/tests','-q','--disable-warnings'],'backend-tests')
    with (OUT/'frontend-tests.log').open('w',encoding='utf-8') as stream:
        p=subprocess.run(['npm.cmd','test'],cwd=ROOT/'frontend',stdout=stream,stderr=subprocess.STDOUT)
    assert p.returncode==0
    accepted=OUT/'accepted';shutil.copytree(OUT/'cached-final',accepted)
    original=read(accepted/'original/report.json');native=read(accepted/'native/report.json')['cases'];fresh=[]
    for name in ('S5','S4-scan300'):
        run([sys.executable,'tools/eval/profile_eval.py','recognition_gate',name,'--out',OUT/'fresh-original'],name)
        row=read(OUT/'fresh-original/report.json')[name];errors=regressions({name:read(BASE/'original/report.json')[name]},{name:row});assert not errors,errors
        assert row['providers'] and all('CUDAExecutionProvider' in p for p in row['providers'].values())
        shutil.copytree(OUT/'fresh-original'/name,accepted/'original'/name,dirs_exist_ok=True);original[name]=row;fresh.append(name)
    for name in ('native-3b2a49a524e2d50dcf26','native-c4d88e79bc63688e0e7c','native-c4d7791b4ebdf13c3944','native-c6bcc506a3200b19e089'):
        row=native[name];piece=OUT/'fresh-native'/name
        command=[sys.executable,'tools/eval/profile_eval.py','native_recognition_gate','--sources',row['source'],'--include',name,'--baseline',BASE/'native','--out',piece,'--diagnostic']
        print('Running',name,flush=True)
        with (OUT/(name+'.log')).open('w',encoding='utf-8') as stream:subprocess.run(list(map(str,command)),cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        result=read(piece/'report.json');observed=result['cases'][name];graph=read(prediction_path(piece,name));before=read(prediction_path(BASE/'native',name))
        assert observed['providers'] and all('CUDAExecutionProvider' in p for p in observed['providers'].values())
        record=next(json.loads(l) for l in (Path(row['source'])/'candidates.jsonl').read_text().splitlines() if json.loads(l)['sample_id']==name)
        errors=closure_retained(record['circuit'],before,graph);assert not errors,errors
        shutil.copytree(prediction_path(piece,name).parent,accepted/'native'/name,dirs_exist_ok=True);native[name]={**observed,'fresh_ocr':True};fresh.append(name)
    (accepted/'original/report.json').write_text(json.dumps(original,indent=2));(accepted/'native/report.json').write_text(json.dumps({'cases':native,'regressions':[]},indent=2))
    gate=read(accepted/'gate.json');gate.update(passed=True,source_snapshot=frozen,fresh_ocr=False,fresh_case_scope=fresh,
        scope='All eighteen cases validated; six affected cases use fresh OCR and remaining cases use cached raster postprocessing',
        clear_pin_total=sum(original[n]['pins_exact'] for n in ('S1','S3','S4','S5')),
        native_totals={k:sum(r[k] for r in native.values()) for k in ('physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')})
    assert gate['clear_pin_total']>=228 and gate['native_totals']['physical_pins_found']>=131
    assert gate['native_totals']['connected_pin_pairs_correct']>=10 and gate['native_totals']['connected_pin_pairs_wrong']==0
    assert snapshot()==frozen
    (accepted/'gate.json').write_text(json.dumps(gate,indent=2))
    run([cpu,'tools/eval/tonight_corpus.py','--phase',accepted,'--out',OUT/'xml-corpus'],'xml-corpus')
    xml=read(OUT/'xml-corpus/report.json');old=read(ROOT/'evidence/upgrade-20261024/xml-corpus/report.json')
    assert all(xml['xml_cases'][n]['passed'] for n,r in old['xml_cases'].items() if r['passed'])
    assert xml['xml_passed']==18
    run([cpu,'tools/eval/observed_export_gate.py','--phase',accepted,'--out',OUT/'native-exports'],'native-exports')
    run([sys.executable,'tools/eval/precision_demo.py','--automatic','--out',OUT/'unseen-final'],'unseen-final')
    unseen=read(OUT/'unseen-final/report.json');assert unseen['literal']['physical_pin_coverage']['tp']==19
    assert unseen['symmetric_terminal_equivalence']['topology_pairwise']['fp']==0
    assert snapshot()==frozen
    (OUT/'verification.json').write_text(json.dumps({'passed':True,'source_snapshot':frozen,'fresh_case_scope':fresh,'xml_passed':18,'unseen_pins':19},indent=2))
    print('Final validation passed',flush=True)
