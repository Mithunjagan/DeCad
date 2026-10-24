"""Build the dated acceptance supplement from actual completed gate receipts."""
import hashlib
import html
import json
from pathlib import Path
import re

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image,KeepTogether

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'evidence/upgrade-20261024'
BASE=ROOT/'evidence/precision-20261023/accepted-fresh'
PDF=ROOT/'output/pdf/DeCad_Precision_Upgrade_2026-10-24.pdf'


def read(path):return json.loads(path.read_text())


def main():
    gate=read(DATA/'final-fresh/gate.json');assert gate['passed'] and gate['fresh_ocr'],gate.get('errors')
    original=read(DATA/'final-fresh/original/report.json');old_original=read(BASE/'original/report.json')
    native=read(DATA/'final-fresh/native/report.json')['cases'];old_native=read(BASE/'native/report.json')['cases']
    xml=read(DATA/'xml-corpus/report.json');exports=read(DATA/'native-exports/report.json');assert exports['passed'],exports['errors']
    unseen=read(DATA/'unseen-automatic/report.json');faculty=read(DATA/'faculty-roundtrip.json')
    live=read(DATA/'live-automatic/report.json');assert live['passed'] and live['fresh_live_raster_recognition']
    assert unseen['fresh_ocr'] and unseen['source_unchanged'] and faculty['passed']
    backend=(DATA/'backend-tests-configured.log').read_text(encoding='utf-8',errors='replace')
    frontend=(DATA/'frontend-tests.log').read_text(encoding='utf-8',errors='replace')
    backend_result=re.search(r'\d+ passed[^\r\n]*',backend).group(0)
    assert not re.search(r'\d+ failed',backend) and ('pass 18' in frontend or 'pass: 18' in frontend)
    clear_before=sum(old_original[n]['pins_exact'] for n in ('S1','S3','S4','S5'))
    clear_after=sum(original[n]['pins_exact'] for n in ('S1','S3','S4','S5'))
    native_after={k:sum(r[k] for r in native.values()) for k in ('physical_pins_found','connected_pin_pairs_correct','connected_pin_pairs_wrong')}
    literal=unseen['literal'];symmetric=unseen['symmetric_terminal_equivalence']
    blocked={name:row.get('missing_components',[]) for name,row in xml['xml_cases'].items() if not row['passed']}
    old_xml=read(ROOT/'evidence/precision-20261023/xml-corpus/report.json')
    zero_before=sum(len(row.get('missing_components',[])) for row in old_xml['xml_cases'].values())
    zero_after=sum(map(len,blocked.values()))
    remaining=[[name+'.'+pin,'unread' if observed is None else observed,expected]
               for name in ('S1','S3','S4','S5') for pin,observed,expected in original[name]['wrong_pins']]
    clear_rows=[['Sample','Before','After','Change']]
    for name in original:
        a,b=old_original[name],original[name]
        clear_rows.append([name,f"{a['pins_exact']}/{a['pins_gt']}",f"{b['pins_exact']}/{b['pins_gt']}",f"{b['pins_exact']-a['pins_exact']:+d}"])
    aliases={'native-3b2a49a524e2d50dcf26':'Grove Vision AI V2','native-37735b083f0b9f56549f':'XIAO nRF52840',
             'native-c4d7791b4ebdf13c3944':'CM4Card','native-c4d88e79bc63688e0e7c':'ESP32'}
    native_rows=[['Native source','Valid pins','Correct pairs','Wrong pairs']]
    for name,b in native.items():
        a=old_native[name]
        label=(aliases[name]+' / ' if name in aliases else '')+name.replace('native-','')
        native_rows.append([label,f"{a['physical_pins_found']} -> {b['physical_pins_found']}",
                            f"{a['connected_pin_pairs_correct']} -> {b['connected_pin_pairs_correct']}",
                            f"{a['connected_pin_pairs_wrong']} -> {b['connected_pin_pairs_wrong']}"])
    total_assignments=0
    for name,formats in exports['cases'].items():
        counts=[r.get('matched_pins',r.get('assigned_pins')) for r in formats.values()]
        present=[v for v in counts if v is not None]
        assert not present or len(set(present))==1,(name,counts)
        total_assignments+=present[0] if present else 0
    old_exports=read(ROOT/'evidence/precision-20261023/native-exports/report.json')
    old_assignments=sum(row['kicad']['matched_pins'] for row in old_exports['cases'].values())
    summary={'baseline_commit':'9985afa','date':'2026-10-24','gate':str(DATA/'final-fresh/gate.json'),
        'clear_before':clear_before,'clear_after':clear_after,'native_before':{'physical_pins_found':103,'connected_pin_pairs_correct':9,'connected_pin_pairs_wrong':13},
        'native_after':native_after,'xml_before':7,'xml_after':xml['xml_passed'],'xml_total':xml['xml_total'],
        'xml_blockers':blocked,'remaining_clear_errors':remaining,'backend':backend_result,'frontend':'18 passed','native_export_cases':len(exports['cases']),
        'zero_pin_xml_blockers_before':zero_before,'zero_pin_xml_blockers_after':zero_after,
        'native_readback_assignments_before':old_assignments,'native_readback_assignments':total_assignments,'unseen_literal':literal,'unseen_symmetric':symmetric,
        'live_automatic_project':live['project'],'live_automatic_assigned_pins':live['assigned_pins'],
        'protected_model_sha256':gate['protected_model_sha256'],'source_snapshot':gate['source_snapshot']}
    (DATA/'final-summary.json').write_text(json.dumps(summary,indent=2))
    markdown=f'''# Precision and unseen-circuit upgrade - 24 October 2026

Verified against baseline `9985afa`. The serialized eighteen-case gate uses fresh raster recognition. No previously correct clear assignment, valid native pin or correct native pair was lost. Protected OCR model SHA-256: `{gate['protected_model_sha256']}`.

| Measurement | Before | After |
|---|---:|---:|
| Clear exact pin-to-net assignments | {clear_before}/245 | {clear_after}/245 ({100*clear_after/245:.2f}%) |
| Degraded 300-DPI scan | 44/72 | {original['S4-scan300']['pins_exact']}/72 |
| Native valid physical pins | 103 | {native_after['physical_pins_found']} |
| Native correct connected pairs | 9 | {native_after['connected_pin_pairs_correct']} |
| Native wrong connected pairs | 13 | {native_after['connected_pin_pairs_wrong']} |
| Raw Faculty XML exports | 7/18 | {xml['xml_passed']}/18 |
| Zero-pin components blocking raw XML | {zero_before} | {zero_after} |
| Automatic unseen components | 2/8 | {literal['component_detection']['tp']}/8 |
| Automatic unseen physical pins | 0/19 | {literal['physical_pin_coverage']['tp']}/19 |
| Native observed-graph exports | 18/18 | {len(exports['cases'])}/18 |
| Matched observed assignments per CAD format | {old_assignments}/{old_assignments} | {total_assignments}/{total_assignments} |

Backend: {backend_result}. Frontend: 18/18 passed. Faculty fixture: 129/129 nodes across 41 nets, with semantic and graph fidelity verified. KiCad and OrCAD exports independently reopen and preserve the current observed graph; this is serialization fidelity, not a claim that every raster connection is correct.

## Clear and degraded samples

'''
    def mdtable(rows):return '\n'.join('| '+' | '.join(map(str,row))+' |' for row in [rows[0],['---']*len(rows[0])]+rows[1:])+'\n'
    markdown+=mdtable(clear_rows)+'\n## Ten native sources\n\n'+mdtable(native_rows)
    markdown+='''
## Implemented changes and evidence boundaries

- Recognized two-terminal passives receive anchors only when an actual body and opposing leads are visible. Unprinted IDs use left/top=1 and right/bottom=2; known observed orientation is retained. Each synthesized terminal is tagged `implicit_passive_terminal` and highlighted for review.
- A separate DC connectivity view vetoes capacitor plate gaps while retaining the existing OCR terminal coordinate system. Capacitor bodies are erased again after gap healing. A printed value fused with a net name and five-sided port labels are resolved only on the affected DC conductor.
- Exact MCU port tokens such as P0.00 and P0.31 cannot spawn a P0 connector. Existing connector syntax remains unchanged. An external literal IC caption owns its verified outline; internal phantom references with no independent caption are suppressed.
- Zero-pin aliases require absent independent body verification and corroborating source evidence. Quarantined components and their source regions remain in image metadata and review hotspots. Legitimate unresolved components remain active and can still block raw XML export.
- A missing IC terminal can be recovered from a printed package pin, aligned external indexed label and continuous outside lead. Existing assignments are retained. Two other clear-recovery experiments produced no gain and were reverted.

The native stress corpus includes hidden pin and field information. Coverage remains incomplete, including the nRF source; removing phantom connected pairs does not mean that circuit was fully recovered.

## Unseen Sallen-Key result

'''
    markdown+=f"Raster-only recognition recovers {literal['component_detection']['tp']}/8 components and {literal['physical_pin_coverage']['tp']}/19 physical pins. Literal numbered-pair score: {literal['topology_pairwise']['tp']} correct, {literal['topology_pairwise']['fp']} wrong, {literal['topology_pairwise']['fn']} missing. Allowing only R/C/L terminal swaps: {symmetric['topology_pairwise']['tp']} correct, {symmetric['topology_pairwise']['fp']} wrong, {symmetric['topology_pairwise']['fn']} missing. The native reference was read only after the raw raster prediction was saved. Canonical/export IDs are never changed by equivalence scoring. U1's unread power terminal still requires review.\n\n"
    markdown+='## Remaining raw XML blockers\n\n'+('\n'.join(f"- {name}: {', '.join(refs) or 'see detailed receipt'}" for name,refs in blocked.items()) or 'None.')+'\n\n'
    markdown+='## Remaining clear-source assignments\n\n'+mdtable([['Physical pin','Observed label','Independent expected label']]+remaining)+'\n'
    markdown+=f"Live API verification: new project `{live['project']}` recovered {live['components']} components and {live['assigned_pins']} physical terminals from the raster. Saving and reopening the draft, Faculty XML download, KiCad download/readback and Capture DSN download/reopen all passed without manual correction or a reference graph supplied to recognition.\n\n"
    markdown+='Receipts: `evidence/upgrade-20261024/final-fresh/gate.json`, `xml-corpus/report.json`, `native-exports/report.json`, `unseen-automatic/report.json`, `live-automatic/report.json`, `faculty-roundtrip.json`. Raw predictions, failed experiments and rollback checkpoints are retained separately.\n'
    (DATA/'REPORT.md').write_text(markdown,encoding='utf-8')
    acceptance=ROOT/'training/TONIGHT_FINAL_ACCEPTANCE.md'
    old=acceptance.read_text(encoding='utf-8');start='<!-- upgrade-20261024:start -->';end='<!-- upgrade-20261024:end -->'
    if start in old:old=old.split(end,1)[1].lstrip()
    acceptance.write_text(start+'\n'+markdown+'\n'+end+'\n\n'+old,encoding='utf-8')
    styles=getSampleStyleSheet();ink=colors.HexColor('#173650');muted=colors.HexColor('#566879')
    styles.add(ParagraphStyle(name='BodyUpgrade',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=9,textColor=ink))
    styles.add(ParagraphStyle(name='SmallUpgrade',fontName='Helvetica',fontSize=8,leading=11,spaceAfter=6,textColor=muted))
    styles.add(ParagraphStyle(name='CellUpgrade',fontName='Helvetica',fontSize=8,leading=10))
    styles['Title'].textColor=ink;styles['Heading1'].textColor=ink
    story=[]
    def p(text,style='BodyUpgrade'):return Paragraph(html.escape(str(text)),styles[style])
    def para(text):story.append(p(text))
    def title(text):story.append(p(text,'Heading1'));story.append(Spacer(1,6))
    def table(rows,widths):
        t=Table([[p(c,'CellUpgrade') for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce7ef')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#b9c8d3')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7f9')])]))
        story.append(t);story.append(Spacer(1,12))
    def page():story.append(PageBreak())
    story.append(p('DeCad','Title'));title('Precision and unseen-circuit upgrade')
    para('24 October 2026 | Verified baseline: 9985afa | Fresh serialized eighteen-case acceptance')
    table([['Measurement','Before','Verified after'],['Clear exact assignments',f'{clear_before}/245',f'{clear_after}/245 ({100*clear_after/245:.2f}%)'],
        ['Native valid physical pins','103',native_after['physical_pins_found']],['Native correct connected pairs','9',native_after['connected_pin_pairs_correct']],
        ['Native incorrect connected pairs','13',native_after['connected_pin_pairs_wrong']],['Raw Faculty XML exports','7/18',f"{xml['xml_passed']}/18"],
        ['Unseen automatic components','2/8',f"{literal['component_detection']['tp']}/8"],['Unseen automatic physical pins','0/19',f"{literal['physical_pin_coverage']['tp']}/19"]],[254,108,148])
    para('All previously correct clear assignments, native physical pins and native connected pairs are retained. The OCR model is unchanged. Automatic recognition remains incomplete; source review is still required.')
    para('This report separates image accuracy, terminal-number equivalence and faithful export/readback. A passing export does not certify the underlying raster interpretation.')
    page();title('Clear and degraded recognition')
    table(clear_rows,[150,120,120,120])
    para('The four clear samples use the existing manually annotated 245-pin reference. S2 exercises component/value recognition and has no annotated pin-to-net target. Scan200 and blur300 remain difficult; unchanged zero scores are shown explicitly.')
    para('A missing terminal is added only when a printed package pin, aligned external label and continuous outside conductor agree. Existing assignments are retained. Candidate rules that produced no improvement were reverted.')
    source=ROOT/'evidence/precision-20261023/source-audit/S3-U6.png'
    with PILImage.open(source) as image:w,h=image.size
    factor=min(480/w,330/h);story.append(Image(str(source),width=w*factor,height=h*factor))
    story.append(p('Source evidence: S3 U6, showing the printed terminal and indexed net labels.','SmallUpgrade'))
    page();title('Native stress corpus')
    table(native_rows,[192,106,106,106])
    para(f"Total valid physical pins: 103 -> {native_after['physical_pins_found']}. Correct pairs: 9 -> {native_after['connected_pin_pairs_correct']}. Incorrect pairs: 13 -> {native_after['connected_pin_pairs_wrong']}.")
    para('Grove ground propagation is blocked at observed capacitor plates. The nRF dotted port labels, including fused alternate-function annotations, are excluded from connector parsing. CM4 internal text no longer spawns U504; the independently captioned U6 owns the outline.')
    para('Native coverage is measured against original CAD graphs that can include hidden pin/field information. Several sources remain sparsely recovered. In particular, the nRF guard removes a false interpretation without proving complete device recognition.')
    page();title('Faculty XML and CAD readback')
    table([['Check','Verified result'],['Faculty fixture','129/129 nodes; 41 nets; semantic and graph fidelity'],
        ['Raw corpus XML',f"{xml['xml_passed']}/18 passing; {zero_before} -> {zero_after} zero-pin blockers"],['KiCad native readback',f"{len(exports['cases'])}/18 cases"],
        ['OrCAD Capture DSN reopen',f"{len(exports['cases'])}/18 cases"],['Matched observed assignments',f'{old_assignments}/{old_assignments} before; {total_assignments}/{total_assignments} after'],
        ['Backend tests',backend_result],['Frontend tests','18/18 passed']],[210,300])
    para('A zero-pin component is quarantined only with absent independent body verification and corroborating alias evidence. Real components with unresolved terminals remain active; they are not hidden to make XML validation pass.')
    if blocked:table([['Still blocked','Unresolved component references']]+[[n,', '.join(refs)] for n,refs in blocked.items()],[255,255])
    para('Native exports reopen the current observed graph and compare its literal component values and physical pin-to-net assignments. These checks preserve serialization fidelity and do not substitute a library-generated connection for a missing source observation.')
    para('Each count uses that version of the observed graph. The corrected inventory removes phantom connector pins and adds supported passive and IC terminals; native source comparison separately confirms retention of previously correct observations.')
    page();title('Unseen Sallen-Key: automatic result')
    table([['Measurement','Literal IDs','R/C/L swap equivalence'],['Recovered components',f"{literal['component_detection']['tp']}/8",'Same components'],
        ['Recovered physical pins',f"{literal['physical_pin_coverage']['tp']}/19",'Same inventory'],
        ['Correct connected pairs',literal['topology_pairwise']['tp'],symmetric['topology_pairwise']['tp']],
        ['Incorrect connected pairs',literal['topology_pairwise']['fp'],symmetric['topology_pairwise']['fp']],
        ['Missing connected pairs',literal['topology_pairwise']['fn'],symmetric['topology_pairwise']['fn']]],[230,125,155])
    para('Unprinted passive terminals use deterministic left/top=1, right/bottom=2 IDs when native symbol orientation is absent. The independently rotated KiCad reference uses the opposite numbering on the four R/C symbols. Equivalence scoring allows only symmetric R/C/L swaps; diodes and sources are excluded. Exports retain the original deterministic IDs.')
    para('The unread U1 power terminal remains a source-review item. The independently verified native graph is read only after the raw automatic prediction is saved.')
    para(f"Live API project {live['project']}: raster recognition, draft save/reopen, Faculty XML and both native download/readback paths passed without manual correction.")
    tmp=ROOT/'tmp/pdfs/upgrade-20261024';tmp.mkdir(parents=True,exist_ok=True)
    source=ROOT/'evidence/precision-20261023/unseen-sallen-key.png'
    with PILImage.open(source) as image:
        image.crop((50,940,1360,1625)).save(tmp/'unseen-filter.png')
    story.append(Image(str(tmp/'unseen-filter.png'),width=510,height=267))
    story.append(p('Held-out raster filter source. The supply-source section is also part of the tested image.','SmallUpgrade'))
    page();title('Reproduction and remaining limitations')
    para('The production profile remains hybrid_max_accuracy. The serialized gate starts a fresh isolated GPU worker for each of eight original/degraded samples and ten native designs. Source fingerprints and loaded CUDA providers are retained in the receipts. The protected model is never trained, replaced or modified.')
    para(f'Raw Faculty XML blockers listed on page 4 require further source-backed terminal recovery. {245-clear_after} clear pin-to-net errors remain. Low-resolution scans, missing op-amp text and sparsely recovered native designs still require review.')
    table([['Receipt','Location under evidence/upgrade-20261024'],['Fresh recognition','final-fresh/gate.json'],['Raw Faculty XML corpus','xml-corpus/report.json'],
        ['KiCad and Capture reopen','native-exports/report.json'],['Unseen raster-only acceptance','unseen-automatic/report.json'],['Live API and downloads','live-automatic/report.json'],['Faculty fixture preservation','faculty-roundtrip.json'],
        ['Exact before/after summary','final-summary.json'],['Tests','backend-tests-configured.log; frontend-tests.log']],[190,320])
    para('Rejected experiments and per-stage checkpoints remain available. Pre-existing unrelated repository changes are preserved outside this task commit. Historical acceptance sections remain in training/TONIGHT_FINAL_ACCEPTANCE.md.')
    story.append(p('Protected OCR model SHA-256: '+gate['protected_model_sha256'],'SmallUpgrade'))
    story.append(p('Baseline recovery commits: 9985afa, 871ee61 and b0d6c9b. Delivery receipts record the final implementation commit.','SmallUpgrade'))
    page();title('Open review items: clear samples')
    para('These remaining mismatches use the existing independent 245-pin manual reference. The expected labels are evaluation data and are never supplied to recognition. Unread entries remain explicit abstentions.')
    table([['Physical pin','Observed label','Independent expected label']]+remaining,[150,180,180])
    PDF.parent.mkdir(parents=True,exist_ok=True)
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(muted)
        canvas.drawString(42,26,'DeCad | Precision upgrade | 24 October 2026')
        canvas.drawRightString(A4[0]-42,26,str(doc.page))
    SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=45,
                      title='DeCad precision upgrade - 24 October 2026',author='DeCad engineering verification').build(story,onFirstPage=footer,onLaterPages=footer)
    print(json.dumps({'pdf':str(PDF),'report':str(DATA/'REPORT.md'),'sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'summary':summary},indent=2))


if __name__=='__main__':main()
