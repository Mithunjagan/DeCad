import json, sys, re
gt = json.load(open(sys.argv[1])); rec = json.load(open(sys.argv[2]))
norm = lambda r: re.sub(r'[A-H]$', '', r) if re.match(r'^U\d+[A-H]$', r) else r
rc = {norm(c['ref']): c['value'].upper() for c in rec['components']}
G = {k: v.upper() for k, v in gt['components'].items()}
tp = [r for r in G if r in rc]; fp = [r for r in rc if r not in G]; fn = [r for r in G if r not in rc]
val_ok = [r for r in tp if rc[r] == G[r] or G[r] in ("CONNECTOR", "SWITCH", "PROM")]
part = gt.get('partial')
if part: fp = [r for r in fp if not re.match(r'^U\d+$', r) or r in G]
print(f"PARTS{' (partial GT: unlisted U-refs not counted)' if part else ''} recall {len(tp)}/{len(G)}={len(tp)/max(1,len(G)):.0%} precision {len(tp)}/{len(tp)+len(fp)}={len(tp)/max(1,len(tp)+len(fp)):.0%} values {len(val_ok)}/{len(tp)}")
print('  missed', fn, ' spurious', fp, ' wrong values', [(r, rc[r], G[r]) for r in tp if r not in val_ok])
pin_net = {}
for n in rec['nets']:
    for nd in n['nodes']: pin_net[f"{norm(nd['ref'])}.{nd['pin']}"] = n['name'].upper()
P = gt.get('pins', {})
ok = [k for k, v in P.items() if pin_net.get(k) == v.upper()]
found = [k for k in P if k in pin_net]
print(f"PINS labeled-net exact {len(ok)}/{len(P)}={len(ok)/max(1,len(P)):.0%}; pin present {len(found)}/{len(P)}")
print('  wrong', [(k, pin_net.get(k), P[k]) for k in P if k not in ok][:40])
vc = gt.get('value_counts')
if vc:
    from collections import Counter
    got = Counter(c['value'].upper() for c in rec['components'])
    print('VALUE COUNTS (expected at least):', {k: f"{got.get(k, 0)}/{v}" for k, v in vc.items()}, ' total parts read', len(rec['components']))
