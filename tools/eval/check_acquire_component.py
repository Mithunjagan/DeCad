"""Real find/validate/place acceptance. --public simulates missing local assets."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app import component_acquisition as acq
from app.component_library import ComponentLibrary
from app.component_project import place
from app.engine import Schematic
from app.sexpr import child,children,parse


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--public',action='store_true');args=parser.parse_args()
    output=ROOT/'backend/.state/codex-20261018'/('acquire-public' if args.public else 'acquire-local')
    output.mkdir(parents=True,exist_ok=True)
    # The override belongs only to this acceptance process; app source stays unchanged.
    if args.public:
        acq.kicad_paths=lambda query:[]
        acq.footprint_paths=lambda query:[]
    library=ComponentLibrary(output/('workspace-'+str(time.time_ns())))
    result=acq.acquire_component(library,'Timer:NE555P',external=args.public)
    (output/'acquisition.json').write_text(json.dumps(result,indent=1))
    assert result['status']=='ready',result
    record=result['component']
    assert {p['number'] for p in record['pins']}=={str(i) for i in range(1,9)}
    project=output/('project-'+str(time.time_ns()));Schematic.create(project,project.name)
    placed=place(project,record,'U1',50,50)
    sch=Schematic(project)
    assert len(sch.pin_positions(sch.get('U1')))==8
    props={p[1]:child(p,'at') for p in children(sch.get('U1'),'property')}
    assert [round(float(v),2) for v in props['Reference'][1:3]]==[39.84,41.11]
    assert [round(float(v),2) for v in props['Value'][1:3]]==[52.54,41.11]
    second=place(project,record,'U2')
    assert second['position']!={'x':50,'y':50}
    actual=Schematic(project)
    pins1=actual.pin_positions(actual.get('U1'));pins2=actual.pin_positions(actual.get('U2'))
    assert min(((x-a)**2+(y-b)**2)**.5 for x,y in pins1.values() for a,b in pins2.values())>=5
    footprint=project/'DeCadUnified.pretty'/(record['validation']['sources'][1]+'.kicad_mod')
    assert {str(p[1]) for p in children(parse(footprint.read_text()),'pad')}=={str(i) for i in range(1,9)}
    import pcbnew
    physical=pcbnew.FootprintLoad(str(footprint.parent),footprint.stem)
    assert physical and {p.GetNumber() for p in physical.Pads()}=={str(i) for i in range(1,9)}
    assert (project/'fp-lib-table').is_file() and (project/'component-assets.json').is_file()
    (output/'preview.svg').write_text(sch.preview())
    cached=acq.acquire_component(library,'Timer:NE555P',external=False)
    assert cached['trace'][-1]['stage']=='verified cache'
    report={'query':'Timer:NE555P','source_format':record['source_format'],'source_version':record['source_version'],
            'source':record['original_library_path'],'license':record['source_license']['name'],
            'pins':8,'pads':8,'native_footprint_readback':True,'placement':placed,'cache_reused':True,'trace':result['trace']}
    (output/'report.json').write_text(json.dumps(report,indent=1))
    print(json.dumps({k:v for k,v in report.items() if k!='placement'},indent=1))


if __name__=='__main__':main()
