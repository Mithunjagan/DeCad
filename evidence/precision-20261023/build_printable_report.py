"""Print the accepted evidence without changing application code or metrics."""
from pathlib import Path
import json
import html
import subprocess
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image
from PIL import Image as PILImage

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'evidence/precision-20261023'
OUT=ROOT/'output/pdf/DeCad_Verified_Engineering_Report_2026-10-23.pdf'
TMP=ROOT/'tmp/pdfs/precision-20261023';TMP.mkdir(parents=True,exist_ok=True);OUT.parent.mkdir(parents=True,exist_ok=True)
S=json.loads((DATA/'final-summary.json').read_text())
AUDIT=json.loads((DATA/'source-audit/audit.json').read_text())
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyAudit',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=9))
styles.add(ParagraphStyle(name='SmallAudit',fontName='Helvetica',fontSize=8.5,leading=11,spaceAfter=6))
styles.add(ParagraphStyle(name='CellAudit',fontName='Helvetica',fontSize=8.3,leading=10.4))
styles['Title'].textColor=colors.HexColor('#16324d');styles['Title'].fontSize=27
styles['Heading1'].fontSize=20;styles['Heading1'].leading=24;styles['Heading1'].textColor=colors.HexColor('#16324d')
story=[]
def p(text,style='BodyAudit'):return Paragraph(html.escape(str(text)),styles[style])
def para(text):story.append(p(text))
def title(text):story.append(Paragraph(html.escape(text),styles['Heading1']));story.append(Spacer(1,8))
def table(rows,widths):
    t=Table([[p(c,'CellAudit') for c in r] for r in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5edf4')),
        ('GRID',(0,0),(-1,-1),.35,colors.HexColor('#b8c6d2')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f8fa')])]))
    story.append(t);story.append(Spacer(1,11))
def image(path,width=500,height=500):
    im=PILImage.open(path);w,h=im.size;scale=min(width/w,height/h)
    result=Image(str(path),width=w*scale,height=h*scale);result.hAlign='CENTER';return result
def page():story.append(PageBreak())

story.append(Paragraph('DeCad',styles['Title']));title('Verified engineering report')
para('23 October 2026 | Application b0d6c9b | Evidence cff361e | Recovery 871ee61')
para('The review-assisted application is verified. Automatic schematic recovery remains incomplete. This report separates accepted graph improvements, rejected experiments, serialization fidelity and manual corrections.')
table([['Measurement','Before','Accepted'],['Clear exact assignments','227/245','227/245 (92.65%)'],
    ['Native valid assigned pins','103','103'],['Native correct connected pairs','9','9'],
    ['Native incorrect connected pairs','14','13'],['Native pair precision','39.13%','40.91% (+1.78 points)'],
    ['Native CAD readback','18/18 each','18/18 each; 2,206 pins each']], [235,125,155])
para('Accepted improvement: Wio R1.1--R1.4 is no longer connected through an incompatible OCR reading. Invalid observations R1.4 and R1.55 remain available as review evidence. No replacement number or signal label is inferred.')
para('Final verification: 384 backend tests passed, 6 environment-dependent skipped; 65 focused tests and 18 frontend tests passed. All previously correct native pins, source labels and connected pairs were retained.')
para('Remaining automatic errors: 13 native false pairs and all 18 clear errors. Native stress-corpus pair recall remains 9/21,025 (0.0428%). Dense native targets can include hidden or unprinted information; the result does not certify whole-board automatic recovery.')

page();title('Changes, preservation and evidence boundaries')
para('Only the passive-pin guard was accepted. The explicit two-terminal R/C/L/D library type must be corroborated by observed terminals 1 and 2 with collinear, opposed outward anchors. Extra IDs are quarantined outside the electrical graph; original nodes, previous nets, anchors, warnings and review regions survive canonical review serialization.')
para('Changed application module: backend/app/local_recovery.py. Tests include malformed-number and uncertain-identity cases, three opposing-anchor rejection cases, and an audited real Wio excerpt checked through canonical pin inventory and an independent XML reader.')
para('Rejected parser experiment: a stricter connector boundary removed a phantom pair but created nonexistent P3.2 on another design through regex reference backtracking. Execution stopped. digital_vision.py was restored byte-for-byte to the accepted baseline. That apparent improvement is not shipped.')
para('Accepted evidence mode: exact guard replay over all 18 baseline graphs, with no graph changes on the other 17, plus fresh current-code Wio and ESP32 rollback workers. Sixteen final cohort outputs use unchanged accepted recognition and two use current fresh targets. Rejected candidate fresh workers are archived separately and never relabeled as current acceptance.')
para('Preserved achievements: TD9-style XML codec and inventory; persistent canonical review drafts; revision checks and saved undo; manual component and net correction; split/merge; confidence handling; stale-source invalidation; exact observed-pin native exports; frontend; and launcher readiness checks.')
para('Independent faculty XML checks retain all 129 nodes, 41 nets and meaningful attributes: 114 used / 15 unused pins, four QD0 members, and used-but-unassigned J2.15. Actual vendor TD9 import remains NOT VERIFIED.')
para('No training, large model download, new dependency or application UI redesign. The protected OCR model is unchanged:')
story.append(p('c5ad0e9ebe43373f1986ed5d6c39be0b73a29cb4dcb257e45ca7f91f41ce07cf','SmallAudit'))
para('Visual UI interaction was disabled by Work settings and was not repeated. Live HTTP upload, recognition, saved-review reopening and downloads passed. Existing frontend regressions pass.')

page();title('All 14 original native false pairs')
rows=[['Case','Pair','Independent reference','Status']]
for identity,entries in AUDIT['native_false_pairs'].items():
    case='Grove U2' if '3b2a' in identity else 'Wio R1' if 'a39a' in identity else 'nRF GPIO' if '37735' in identity else 'CM4 U6'
    for row in entries:
        a,b=row['a'],row['b'];reference=row['reference_a']+' / '+row['reference_b']
        if case=='Wio R1':reference='Pin 4 does not belong to this two-terminal resistor'
        elif case=='nRF GPIO':reference='P0 is not a physical component'
        elif case=='CM4 U6':reference='Source owner is U6, not U504'
        rows.append([case,f'{a[0]}.{a[1]} -- {b[0]}.{b[1]}',reference,'REMOVED' if case=='Wio R1' else 'OPEN'])
table(rows,[70,150,225,70])
para('Grove pins 3/9 are VBUS and pin 6 is V33IO, while pins 2/17 and R34.1 are genuine ground. Capacitors and unresolved anchors were mistaken for shared ground paths. U2.3--U2.9 is a previously correct pair even though its detected net name is wrong; a guessed split must not destroy it.')
para('CM4 U6.4--U6.9 is a real junction. The error is the fused reference U504, not a false physical dot. Source images follow on later pages.')

page();title('All 18 clear-sample errors')
para('These are 11 missing physical-anchor observations and 7 incorrect assignments. Printed source labels can be read manually; no sample-specific substitutions or unverified recovery connections were inserted.')
rows=[['Sample','Pin','Observed net','Expected net','Remaining cause']]
for identity,row in AUDIT['clear_errors'].items():
    sample,ref,pin=identity.split('.')
    cause='Missing physical anchor; fused or crowded number/label strip' if not row['anchor_observed'] else 'Wrong label association or unresolved local trace'
    rows.append([sample,ref+'.'+pin,row['read'] or 'missing',row['expected'],cause])
table(rows,[42,66,88,83,236])
para('Low-resolution limits remain: the 200-dpi scan and blurred cases have 0/72 exact assignments. The 300-dpi scan retains 44/72. Clear results remain S1 54/56, S3 62/69, S4 69/72, S5 42/48.')

page();title('Why 11 faculty exports still need review')
para('All observed pins and assignments round-trip. The 11 blocked graphs contain 37 component records with no observed physical IDs. A component-only faculty node would require an invented pin. No codec defect was found.')
labels={'native-3b2a49a524e2d50dcf26':'Grove Vision','native-c4d88e79bc63688e0e7c':'XIAO ESP32','native-e9b7597c67252bf7707d':'AU7 native','native-901de51001a98cc2361a':'Raccoon native','native-c6bcc506a3200b19e089':'PL test native','native-c4d7791b4ebdf13c3944':'CM4 native'}
notes={'S3':'R1 aliases printed R11; R6 is visible, numbering unprinted.','S4':'Visible resistor bodies; physical numbers unprinted.','S5':'Visible resistor bodies; physical numbers unprinted.','S4-scan300':'R1 aliases R13; other resistors visible with degraded ink.','S4-scan200':'Blurred but visible R11; numbers unprinted.','Grove Vision':'Visible bodies; R32 prints 1/2. C36 value also misassociated.','XIAO ESP32':'Visible resistors; U4 from prose and U58 from USB text.','AU7 native':'Visible resistors with unprinted numbers.','Raccoon native':'Visible resistor; numbers unprinted.','PL test native':'Visible resistors; duplicate references also occur in a component list.','CM4 native':'Resistors omit numbers; U4 visibly prints 1..5 but has no extracted anchors.'}
rows=[['Case','Zero-pin component records','Source finding']]
for name,row in AUDIT['xml_blockers'].items():
    case=labels.get(name,name);rows.append([case,', '.join(c['ref'] for c in row['components']),notes[case]])
table(rows,[100,160,255])
para('Unprinted physical numbering is a genuine source-information limit. A visible symbol with missed anchors is a recognition defect. Prose and fused-reference false components need component review. These must not be conflated with exporter defects.')

page();title('Unseen Sallen-Key: raw versus reviewed')
para('Unchanged installed KiCad demonstration; raster only supplied to recognition. Raw output was saved before the native reference was read. The source is shown in two crops from the same image: signal circuit and remote supply blocks.')
source=PILImage.open(DATA/'unseen-sallen-key.png')
for name,bounds in [('signal',(70,940,1400,1640)),('supplies',(1470,55,1740,640))]:source.crop(bounds).save(TMP/(name+'.png'))
fig=Table([[image(TMP/'signal.png',380,220),image(TMP/'supplies.png',108,235)]],colWidths=[395,120]);fig.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE')]));story.append(fig);story.append(Spacer(1,12))
table([['Measure','Raw recognition','Manual review + native pin lookup'],['Components','2/8','8/8, values exact'],['Assigned physical pins','0/19','19/19'],['Positive pairs','0/18','18/18'],['False pairs','0','0'],['Negative pairs preserved','Not a complete graph','153/153']], [180,130,205])
para('The first manual convention produced 6 correct and 12 wrong pairs. The raster omits R/C terminal IDs; native embedded symbol pins and rotations resolve them. R1/R2/C1 pin 1 is at the right; C2 pin 1 is below. The initial transcription and failed comparison remain in the evidence.')
para('This is not an automatic accuracy gain. Reviewed XML and both native readbacks preserve all 19 assignments with zero extras. All 11 named-label assignments match after root-sheet slash normalization; literal full names match 8/19 because unprinted intermediate nets use different generated names.')

page();title('Source evidence: Grove ground propagation')
story.append(image(DATA/'source-audit/Grove-U2-complete.png',475,350))
story.append(Spacer(1,8))
para('U2 pins 3/9 are VBUS and pin 6 is V33IO. C1/C2/C30 separate these nets from ground. The accepted pass does not guess a global rail split.')
story.append(image(DATA/'source-audit/Grove-R34-ground-wide.png',475,260))
story.append(Spacer(1,8))
story.append(p('Separate source region: R34 pin 1 visibly reaches the ground rail. R34.1 with U2.2/U2.17 is a valid ground relationship to preserve.','SmallAudit'))

page();title('Source evidence: accepted Wio correction')
story.append(image(DATA/'native-a39a7a1fc84f921b27fd.png',465,445))
story.append(Spacer(1,8))
para('R1 is a 10K resistor with printed terminals 1 and 2. The raw R1.4 and R1.55 observations cannot be terminals of this corroborated two-terminal symbol. The guard quarantines them without assigning either to another component or inventing the missing LORA_RST label.')
para('Fresh current-code result: 17 previously valid pins and the correct pair retained; R1.1--R1.4 removed. Every rejected reading remains in source-review metadata. Canonical inventory and independent XML tests prove these readings do not reappear as exported physical nodes.')

page();title('Source evidence: unresolved nRF phantom port')
story.append(image(DATA/'native-37735b083f0b9f56549f.png',440,525))
story.append(Spacer(1,8))
para('P0.00/XL1 and P0.31/AIN7 are U1 function names. They are not a separate physical P0 connector. The parser experiment that removed this pair regressed elsewhere, so it was rejected. This false pair remains open in the accepted application.')

page();title('Source evidence: CM4 owner versus junction')
story.append(image(DATA/'native-c4d7791b4ebdf13c3944.png',500,430))
story.append(Spacer(1,8))
para('The source reference is U6 (ATECC608A-MAHDA). Pins 4 and 9 visibly join with a dot and reach ground. The detected U504 is fused internal text. A junction-cut repair would damage real connectivity; component identity needs correction first.')
para('No speculative body rewrite or source-specific reference replacement was merged. This error stays explicit in the remaining-pair inventory.')

page();title('Launch, reproduce and independently review')
for line in ['Repository: D:\\DeCad-main\\Jrk_DeCad\\Schematic2SDN','Run: & .\\start-native.ps1','Workbench: http://localhost:3100; API: http://localhost:8100','Choose PrecisionUnseenFilter, then Saved review. Its source raster is attached.','Recheck existing review: backend/.venv/Scripts/python.exe tools/eval/precision_demo.py --verify','Recovery branch: recovery/precision-871ee61; accepted application commit: b0d6c9b.']:
    para(line)
para('Reproduction scripts: precision_acceptance.py checks the exact 18-graph guard delta with two current fresh target workers; precision_audit.py recreates source crops and independent inventories. Full commands and evidence paths are in training/TONIGHT_FINAL_ACCEPTANCE.md.')
title('Verified implementation history')
lines=subprocess.check_output(['git','log','--oneline','2202e54..cff361e'],cwd=ROOT,text=True).splitlines()
table([['Commit','Verified change']]+[line.split(' ',1) for line in lines],[75,440])
para('Final limits: 13 native false pairs, 18 clear errors, incomplete automatic unseen recovery, unprinted physical-ID ambiguity, no repeated visual UI run, and TD9 vendor import not verified. Serialization fidelity is not evidence of image-recognition correctness.')

def footer(canvas,doc):
    canvas.saveState();canvas.setStrokeColor(colors.HexColor('#ccd6df'));canvas.line(40,39,A4[0]-40,39)
    canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#546779'))
    canvas.drawString(40,27,'DeCad verification | 23 Oct 2026 | application b0d6c9b')
    canvas.drawRightString(A4[0]-40,27,str(doc.page));canvas.restoreState()

doc=SimpleDocTemplate(str(OUT),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=42,bottomMargin=51,
    title='DeCad verified engineering and precision report',author='Codex')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
