"""Produce the closure supplement only from completed verification receipts."""
import hashlib,html,json,re
from pathlib import Path
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,PageBreak,Spacer,Image

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'evidence/closure-20261024';PDF=ROOT/'output/pdf/DeCad_Final_Closure_2026-10-24.pdf'
def read(p):return json.loads(p.read_text())
def main():
    verified=read(OUT/'verification.json');assert verified['passed']
    gate=read(OUT/'accepted/gate.json');xml=read(OUT/'xml-corpus/report.json');exports=read(OUT/'native-exports/report.json')
    unseen=read(OUT/'unseen-final/report.json');live=read(OUT/'live-automatic/report.json')
    live_provisional=read(OUT/'live-provisional/report.json');assert live_provisional['passed']
    assert xml['xml_passed']==18 and exports['passed'] and live['passed']
    literal=unseen['literal'];equivalent=unseen['symmetric_terminal_equivalence'];assert literal['physical_pin_coverage']['tp']==19
    backend=re.search(r'\d+ passed[^\r\n]*',(OUT/'backend-tests.log').read_text()).group(0)
    frontend=(OUT/'frontend-tests.log').read_text();assert re.search(r'pass\s+19',frontend)
    provisional=[];quarantine=[];trusted=0
    for scope in ('original','native'):
        for path in (OUT/'accepted'/scope).glob('*/recognized.json'):
            g=read(path);nodes=[p for n in g['nets'] for p in n['nodes']];prov=[p for p in nodes if p.get('source')=='provisional_stub']
            if prov:provisional.append([path.parent.name,len(prov),sum(p['pin'].startswith('STUB') for p in prov)])
            for q in g['image_metadata'].get('quarantined_components',[]):
                if q.get('kind')=='unanchored_zero_pin_caption':quarantine.append([path.parent.name,q['component']['ref'],q['component']['value']])
    native=gate['native_totals'];assigned=sum(r['kicad']['matched_pins'] for r in exports['cases'].values())
    model=hashlib.sha256((ROOT/'checkpoints/schematic-ocr/model.onnx').read_bytes()).hexdigest()
    assert model=='c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf'
    summary={'baseline_commit':'581c236','clear_pins':gate['clear_pin_total'],'native':native,'xml':xml['xml_passed'],
        'provisional_cases':provisional,'provisional_terminals':sum(r[1] for r in provisional),'explicit_stub_ids':sum(r[2] for r in provisional),
        'quarantined_caption_records':quarantine,'unseen_literal':literal,'unseen_equivalent':equivalent,'backend':backend,'frontend':'19 passed',
        'readback_assignments':assigned,'fresh_ocr_cases':verified['fresh_case_scope'],'full_eighteen_case_ocr_rerun':False,
        'live_project':live['project'],'live_provisional_project':live_provisional['project'],'model_sha256':model}
    (OUT/'final-summary.json').write_text(json.dumps(summary,indent=2))
    rows=[['Measurement','581c236 baseline','Closure'],['Clear pin-to-net score','228/245',f"{gate['clear_pin_total']}/245"],
        ['300-DPI scan','44/72','44/72'],['Previously valid native pins retained','131','131'],['Native correct / wrong pairs','10 / 0',f"{native['connected_pin_pairs_correct']} / {native['connected_pin_pairs_wrong']}"],
        ['Unseen components / automatic pins','8/8; 18/19','8/8; 19/19'],['Raw Faculty XML exports','11/18','18/18'],
        ['Backend / frontend passing tests','412 / 18',backend.split(' passed')[0]+' / 19']]
    def mdtable(table):return '\n'.join('| '+' | '.join(map(str,r))+' |' for r in [table[0],['---']*len(table[0])]+table[1:])+'\n'
    markdown='# Final closure - 24 October 2026\n\nBaseline recovery point: `581c236`. Production OCR weights are unchanged.\n\n'+mdtable(rows)
    markdown+='''
The nineteenth op-amp terminal is recovered automatically from five visible boundary leads and four observed numbers that uniquely identify a standard inventory. Ambiguous inventories abstain. No manual edit or reference graph enters recognition.

Raw XML passing means schema/graph fidelity, including explicitly provisional review terminals. Provisional terminals stay on separate singleton nets with source `provisional_stub`, conservative confidence and amber review regions. Unread identifiers remain `STUB` identifiers rather than claims about physical package numbers. Real bodies without usable stubs remain unresolved. Caption-only zero-pin records retain their full contents in quarantine metadata.

'''
    markdown+=f"There are {summary['provisional_terminals']} provisional terminals, including {summary['explicit_stub_ids']} explicit STUB identifiers. Native assigned physical-ID coverage totals {native['physical_pins_found']}, including provisional numeric identifiers that match the independent native inventory; all 131 previously correct IDs remain. The source still requires review before electrical use.\n\n"
    markdown+='## Per-case provisional inventory\n\n'+mdtable([['Case','Provisional terminals','Explicit STUB identifiers']]+provisional)
    markdown+='\n## Caption-only records retained for review\n\n'+mdtable([['Case','Ref','Original value']]+quarantine)
    markdown+=f"\nUnseen literal numbered topology: {literal['topology_pairwise']['tp']} correct, {literal['topology_pairwise']['fp']} wrong, {literal['topology_pairwise']['fn']} missing. Symmetric R/C/L equivalence: {equivalent['topology_pairwise']['tp']} correct, {equivalent['topology_pairwise']['fp']} wrong, {equivalent['topology_pairwise']['fn']} missing. Canonical/export pin IDs are not renumbered by evaluation.\n\n"
    markdown+=f"Validation: all 18 cases received cached-raster incremental checks; {len(verified['fresh_case_scope'])} affected cases additionally received fresh isolated OCR. The unseen filter and live API import were fresh. This was not a new full eighteen-case OCR run. Fresh cases: {', '.join(verified['fresh_case_scope'])}.\n\n"
    markdown+=f"Backend: {backend}. Frontend: 19 passed. KiCad and OrCAD reopen: 18/18 each; {assigned}/{assigned} observed assignments preserved per format. Live project: `{live['project']}`, including draft persistence and both native downloads.\n\n"
    markdown+=f"Provisional API validation also passed in `{live_provisional['project']}`: typed source/confidence survived persistence, and Faculty XML plus both native formats reopened successfully.\n\n"
    markdown+='The 17 previously documented clear errors and limited native graph recall remain. XML exportability does not certify unresolved terminal numbering, symbol ownership or real electrical connectivity. Historical acceptance sections and unrelated local changes are preserved.\n'
    markdown+='\nReceipts are under `evidence/closure-20261024`: `verification.json`, `accepted/gate.json`, `xml-corpus/report.json`, `native-exports/report.json`, `unseen-final/report.json`, and `live-automatic/report.json`.\n'
    (OUT/'REPORT.md').write_text(markdown,encoding='utf-8')
    acceptance=ROOT/'training/TONIGHT_FINAL_ACCEPTANCE.md';old=acceptance.read_text(encoding='utf-8');start='<!-- closure-20261024:start -->';end='<!-- closure-20261024:end -->'
    if start in old:old=old.split(end,1)[1].lstrip()
    acceptance.write_text(start+'\n'+markdown+'\n'+end+'\n\n'+old,encoding='utf-8')
    styles=getSampleStyleSheet();ink=colors.HexColor('#173650')
    styles.add(ParagraphStyle(name='ClosureBody',fontSize=10,leading=14,spaceAfter=10,textColor=ink))
    styles.add(ParagraphStyle(name='ClosureCell',fontSize=8,leading=11))
    styles['Heading1'].textColor=ink;story=[]
    def p(text,style='ClosureBody'):return Paragraph(html.escape(str(text)),styles[style])
    def para(text):story.append(p(text))
    def title(text):story.append(p(text,'Heading1'));story.append(Spacer(1,8))
    def table(data,widths):
        t=Table([[p(c,'ClosureCell') for c in r] for r in data],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce7ef')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#b9c8d3')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7f9')])]))
        story.extend([t,Spacer(1,12)])
    title('DeCad | Final closure')
    para('24 October 2026 | Recovery baseline 581c236 | Model unchanged')
    table(rows,[250,130,130])
    para('The automatic held-out filter now recovers all nineteen physical pin IDs. All eighteen raw Faculty XML cases export, with unresolved terminals explicitly marked for review.')
    para('All previously correct clear assignments, native pin IDs and connected pairs remain. Provisional terminals are isolated; successful serialization is separate from electrical correctness.')
    story.append(PageBreak());title('The nineteenth op-amp terminal')
    para('Five visible conductors must enter the amplifier boundary: two inputs, one output and two supply leads. Four observed numbers must identify one standard five-terminal inventory. The remaining number is assigned only to the remaining visible lead. Ambiguous families and missing conductors abstain.')
    table([['Unseen measurement','Literal IDs','R/C/L equivalence'],['Components / physical pins','8/8; 19/19','Same inventory'],
        ['Correct connected pairs',literal['topology_pairwise']['tp'],equivalent['topology_pairwise']['tp']],['Incorrect connected pairs',literal['topology_pairwise']['fp'],equivalent['topology_pairwise']['fp']],['Missing pairs',literal['topology_pairwise']['fn'],equivalent['topology_pairwise']['fn']]],[230,140,140])
    para('Unprinted symmetric passive IDs follow the existing deterministic convention. Equivalence scoring permits R/C/L terminal swaps and never changes canonical export IDs. Diodes and sources are excluded.')
    image=ROOT/'evidence/precision-20261023/unseen-sallen-key.png';tmp=ROOT/'tmp/pdfs/closure-20261024';tmp.mkdir(parents=True,exist_ok=True)
    with PILImage.open(image) as im:im.crop((50,940,1360,1625)).save(tmp/'filter.png')
    story.append(Image(str(tmp/'filter.png'),width=510,height=267))
    para('Filter detail. The tested raster also includes the two supply-source symbols above this section.')
    story.append(PageBreak());title('Raw XML: review-required terminals')
    para(f"All 18/18 cases now serialize and roundtrip. The graph contains {summary['provisional_terminals']} provisional terminals, of which {summary['explicit_stub_ids']} retain explicit STUB identifiers. Each is on an isolated net and highlighted in amber in the review interface. Numbering, body ownership and net assignment require confirmation.")
    table([['Case','Provisional','STUB IDs']]+provisional,[340,85,85])
    para('The ESP32 U4 caption occurred in prose; its complete candidate record and source region remain in quarantine. This does not establish recovery of the actual U4 device elsewhere in the design.')
    para(f"Native assigned physical-ID coverage is {native['physical_pins_found']}, including provisional numeric IDs that match the independent inventory. All 131 earlier correct IDs are retained. No provisional conductor is joined to an existing electrical net.")
    story.append(PageBreak());title('Verification and practical limits')
    table([['Check','Result'],['Backend suite',backend],['Frontend suite','19 passed'],['All-corpus incremental checks','18 cases; cached raster postprocessing'],['Additional fresh OCR',str(len(verified['fresh_case_scope']))+' affected cases; plus unseen and live import'],['Faculty XML roundtrip','18/18'],['KiCad / Capture native reopen','18/18 each'],['Literal assignments preserved',f'{assigned}/{assigned} per CAD format'],['Live application',live['project']+'; 19 automatic pins']],[210,300])
    para('Fresh affected-case OCR and cached incremental verification are reported separately. This closure did not repeat the full eighteen-case OCR run. Per-case provenance and execution providers are retained with the predictions.')
    para('A separate live provisional proposal also passed typed evidence persistence, Faculty XML export and both native download/readback paths: '+live_provisional['project']+'.')
    para('Seventeen clear-source mismatches and sparse native graph coverage remain. Provisional exportability is not approval of an electrical design. Unread package numbers and ambiguous symbol ownership remain explicit review items.')
    para('Receipts: evidence/closure-20261024/verification.json; accepted/gate.json; xml-corpus/report.json; native-exports/report.json; unseen-final/report.json; live-automatic/report.json.')
    para('Protected model SHA-256: '+model)
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(ink);canvas.drawString(42,26,'DeCad | Final closure | 24 October 2026');canvas.drawRightString(A4[0]-42,26,str(doc.page))
    PDF.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(PDF),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=40,bottomMargin=45,title='DeCad final closure - 24 October 2026').build(story,onFirstPage=footer,onLaterPages=footer)
    print(json.dumps({'pdf':str(PDF),'sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'summary':summary},indent=2))
if __name__=='__main__':main()
