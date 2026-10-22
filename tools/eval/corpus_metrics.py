"""Graph accuracy for arbitrary circuit corpora, independent of net numbering.

Connectivity uses physical pin pairs. Counts use intersections of net partitions,
so even large power nets do not require constructing quadratically many pairs.
"""
from collections import Counter
import re


def _ratio(correct, total):
    return correct / total if total else None


def _score(correct, predicted, expected):
    return {'correct': correct, 'predicted': predicted, 'expected': expected,
            'precision': _ratio(correct, predicted), 'recall': _ratio(correct, expected)}


def _pairs(size):
    return size * (size - 1) // 2


def score(expected, predicted):
    def components(graph):
        return {c['ref']: c['value'].strip() for c in graph['components']}

    def pins(graph):
        return {(node['ref'], str(node['pin'])): index
                for index, net in enumerate(graph.get('nets', [])) for node in net['nodes']}

    def named_pins(graph):
        return {(node['ref'], str(node['pin'])): net['name'] for net in graph.get('nets', [])
                if not re.fullmatch(r'(?:N\d+|NET[_$]?\d+|Net-\(.+\))', net['name'], re.I)
                for node in net['nodes']}

    ec, pc = components(expected), components(predicted)
    ep, pp = pins(expected), pins(predicted)
    shared = ep.keys() & pp.keys()
    values = sum(ec[ref] == pc[ref] for ref in ec.keys() & pc.keys())
    joint = Counter((ep[pin], pp[pin]) for pin in shared)
    correct_pairs = sum(_pairs(n) for n in joint.values())
    expected_pairs = sum(_pairs(n) for n in Counter(ep.values()).values())
    predicted_pairs = sum(_pairs(n) for n in Counter(pp.values()).values())
    expected_names, predicted_names = named_pins(expected), named_pins(predicted)
    labelled_shared = expected_names.keys() & pp.keys()
    label_correct = sum(expected_names[pin] == predicted_names.get(pin) for pin in labelled_shared)
    wiring_exact = ep.keys() == pp.keys() and correct_pairs == expected_pairs == predicted_pairs
    return {'components': _score(len(ec.keys() & pc.keys()), len(pc), len(ec)),
            'values': _score(values, len(pc), len(ec)),
            'physical_pins': _score(len(shared), len(pp), len(ep)),
            'connections': _score(correct_pairs, predicted_pairs, expected_pairs),
            'net_labels': _score(label_correct, len(labelled_shared), len(expected_names)),
            'false_connections': predicted_pairs - correct_pairs,
            'missing_connections': expected_pairs - correct_pairs,
            'sheet_exact': ec == pc and wiring_exact and label_correct == len(expected_names),
            'missing_components': sorted(ec.keys() - pc.keys()),
            'extra_components': sorted(pc.keys() - ec.keys()),
            'wrong_values': sorted(ref for ref in ec.keys() & pc.keys() if ec[ref] != pc[ref])}
