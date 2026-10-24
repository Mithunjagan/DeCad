"""Compare topology allowing R/C/L terminal swaps, without changing exports."""
from copy import deepcopy
import itertools
import re


def symmetric_mapping(reference,candidate):
    """Return the best equivalent candidate and the explicit swap receipt.

    Diodes and sources are polarized and are never interchangeable. This helper
    is for evaluation/ERC comparison only; canonical/export IDs stay unchanged.
    Bound exhaustive search to twelve symmetric devices and reject larger
    comparisons explicitly rather than silently certifying a partial search.
    """
    def pairs(g):
        return {tuple(sorted(p)) for n in g['nets'] for p in itertools.combinations(
            {(p['ref'],str(p['pin'])) for p in n['nodes']},2)}
    a={c['ref']:c for c in reference['components']};b={c['ref']:c for c in candidate['components']}
    def terminals(g,ref):
        return {str(p['pin']) for n in g['nets'] for p in n['nodes'] if p['ref']==ref}|{
            str(p['pin']) for p in g.get('physical_pins',[]) if p['ref']==ref}
    refs=sorted(r for r in a.keys()&b.keys() if re.fullmatch(r'[RCL]\d+[A-H]?',r)
                and terminals(reference,r)=={'1','2'} and terminals(candidate,r)=={'1','2'})
    if len(refs)>12:raise ValueError('Terminal-equivalence comparison is limited to twelve symmetric devices.')
    target=pairs(reference);best=None
    for mask in range(1<<len(refs)):
        swaps={r for i,r in enumerate(refs) if mask&(1<<i)}
        graph=deepcopy(candidate)
        for net in graph['nets']:
            for node in net['nodes']:
                if node['ref'] in swaps and str(node['pin']) in ('1','2'):node['pin']=str(3-int(node['pin']))
        for pin in graph.get('physical_pins',[]):
            if pin['ref'] in swaps and str(pin['pin']) in ('1','2'):pin['pin']=str(3-int(pin['pin']))
        found=pairs(graph);score=(len(target&found),-len(found-target),-len(swaps))
        if best is None or score>best[0]:best=(score,graph,sorted(swaps))
    return best[1],{'swapped_refs':best[2],'scope':'R/C/L topology equivalence only; literal IDs remain unchanged in the canonical graph'}
