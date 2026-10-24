"""Retention of known observations while preserving explicitly provisional data."""
from copy import deepcopy
from native_recognition_gate import retained,facts

def closure_retained(truth,before,after):
    checked=deepcopy(after)
    # STUB identifiers explicitly abstain from claiming a package pin number.
    # Numeric IDs, including provisional numeric IDs, retain the strict checks.
    unknown={(p['ref'],p['pin']) for n in checked['nets'] for p in n['nodes']
             if p.get('source')=='provisional_stub' and p['pin'].startswith('STUB')}
    for n in checked['nets']:n['nodes']=[p for p in n['nodes'] if (p['ref'],p['pin']) not in unknown]
    checked['physical_pins']=[p for p in checked.get('physical_pins',[]) if (p['ref'],p['pin']) not in unknown]
    old={c['ref']:c for c in before['components']};active={c['ref'] for c in checked['components']};pins=facts(before)[2]
    for q in after.get('image_metadata',{}).get('quarantined_components',[]):
        c=q['component'];ref=c['ref']
        if q.get('kind')!='unanchored_zero_pin_caption' or q.get('no_incident_stub_within_px')!=12:continue
        if ref not in old or ref in active or any(p[0]==ref for p in pins):continue
        if all(c.get(key)==old[ref].get(key) for key in ('ref','value','library','footprint')):
            checked['components'].append(c)
    return retained(truth,before,checked)
