"""Native two-ecosystem acceptance with original CC0 fixtures; no recognition.

Run from project root. Output lives under backend/.state/codex-20261018.
Does not copy vendor assets or modify installed libraries.
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
from app import orcad_capture as oc
from app.component_library import ComponentLibrary, digest
from app.component_formats import kicad_symbol
from app.engine import Schematic, run_cli
from app.sexpr import children, dump


def main():
    output = ROOT/'backend/.state/codex-20261018/component-acceptance'
    output.mkdir(parents=True, exist_ok=True)
    source = output/'cc0-source'
    source.mkdir(exist_ok=True)
    (source/'LICENSE.txt').write_text('Original DeCad acceptance fixtures. CC0-1.0. No vendor library assets.\n')
    (source/'Test.kicad_sym').write_text('''(kicad_symbol_lib (version 20231120) (generator "decad")
      (symbol "TestTwoPin" (in_bom yes) (on_board yes)
        (property "Reference" "U" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
        (property "Value" "TestTwoPin" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
        (property "MPN" "DECAD-TEST-001" (at 0 0 0) (effects (font (size 1.27 1.27))))
        (property "Footprint" "Test:TwoPad" (at 0 0 0) (effects (font (size 1.27 1.27))))
        (symbol "TestTwoPin_1_1"
          (rectangle (start -2.54 2.54) (end 2.54 -2.54) (stroke (width 0) (type default)) (fill (type none)))
          (pin passive line (at -5.08 0 0) (length 2.54) (name "A" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
          (pin passive line (at 5.08 0 180) (length 2.54) (name "B" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27))))))))''')
    pretty = source/'Test.pretty'; pretty.mkdir(exist_ok=True)
    (pretty/'TwoPad.kicad_mod').write_text('''(footprint "TwoPad" (version 20240108) (generator "decad") (layer "F.Cu")
      (pad "1" smd rect (at -2.54 0) (size 1.2 1.4) (layers "F.Cu" "F.Paste" "F.Mask"))
      (pad "2" smd rect (at 2.54 0) (size 1.2 1.4) (layers "F.Cu" "F.Paste" "F.Mask")))''')
    checks = {}
    if oc.available():
        native = output/'native-write';native.mkdir(exist_ok=True)
        olb, dsn = source/'OriginalTwoPin.olb', native/'OriginalTwoPin.DSN'
        if not olb.exists():
            graph = {'components':[{'ref':'U1','value':'DECAD_TEST_TWO_PIN'}], 'nets':[]}
            oc._write(oc.orcad_root(),native,dsn,olb,graph,
                      {'U1':('', 'DECAD_TEST_TWO_PIN','generated symbol')},
                      {'DECAD_TEST_TWO_PIN':('U',{'1','2'})}, {})
        checks['native_olb_generated'] = olb.is_file()
    before = {str(p):digest(p) for p in source.rglob('*') if p.is_file()}
    library = ComponentLibrary(output/'workspace')
    key = library.configure(source,'Mixed',{'name':'CC0-1.0','allow_import':True,'allow_redistribute':True})
    scan = library.scan(key)
    assert not scan['errors'], scan
    symbols = library.search('TestTwoPin')
    kicad = next(r for r in symbols if r['source_format']=='.kicad_sym')
    footprint = next(r for r in library.search('TwoPad') if r['kind']=='footprint')
    paired = library.validate_pair(kicad['id'],footprint['id'])
    assert paired['cached'] and library.verified(kicad['id'])
    checks.update(kicad_import=True,pin_pad_mapping=paired['validation'],cache=True)
    for record in [kicad]+[r for r in library.search('DECAD_TEST_TWO_PIN') if r['source_format']=='.olb']:
        materialized = library.get(record['id'],True)
        assert {p['number'] for p in materialized['pins']}=={'1','2'}
        assert materialized['symbol_geometry']
        content,ext = library.export(record['id'],'kicad')
        target = output/(record['source_format'][1:]+'-export'+ext)
        target.write_bytes(content)
        svg_dir = output/(record['source_format'][1:]+'-svg');svg_dir.mkdir(exist_ok=True)
        run_cli('sym','export','svg','--output',str(svg_dir)+os.sep,target)
        assert list(svg_dir.glob('*.svg'))
        project = output/(record['source_format'][1:]+'-placement')
        if not project.exists(): Schematic.create(project,project.name)
        sch = Schematic(project)
        if not sch.get('U1'):
            definition = children(kicad_symbol(materialized,record['id']),'symbol')[0]
            definition[1]='DeCad:'+record['id']
            sch.add('U1',record['name'],definition[1],x=50,y=50,definition=definition);sch.save()
        nodes=sch.graph()
        assert nodes['components'][0]['ref']=='U1'
        checks[record['source_format']+'_export_and_placement']=True
        if record['source_format']=='.olb':
            native_bytes,native_ext=library.export(record['id'],'orcad')
            assert native_ext=='.olb' and len(native_bytes)>1000
            (output/'verified-native-export.olb').write_bytes(native_bytes)
            checks['native_orcad_export_independent_readback']=True
    checks['shared_search']={ext:sum(r['source_format']==ext for r in library.search('')) for ext in ('.olb','.kicad_sym','.kicad_mod')}
    after = {str(p):digest(p) for p in source.rglob('*') if p.is_file()}
    assert before==after, 'Source files changed during import'
    checks['sources_unchanged']=True
    (output/'report.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks,indent=2))


if __name__=='__main__':main()
