"""Measure recognizer coverage against original real native CAD graphs.

This is an evaluation-only stress corpus, not approved training data. Native
graphs can include hidden pins/fields, so coverage is reported separately from
visual legibility. No source target is passed to the recognizer.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'training'))
from app import digital_vision as dv, orcad_capture as oc
from native_pairs import circuit_from_xml, graph_signature
from app.ingestion import Circuit


def pin(node):
    return (node['ref'].upper(), str(node['pin']))


def facts(graph):
    components = {row['ref'].upper(): row['value'] for row in graph['components']}
    nets = {frozenset(pin(node) for node in net['nodes']) for net in graph['nets'] if net['nodes']}
    pins = set().union(*nets) if nets else set()
    pairs = {tuple(sorted(pair)) for net in nets for pair in itertools.combinations(sorted(net), 2)}
    return components, nets, pins, pairs


def measure(truth, prediction):
    actual, actual_nets, actual_pins, actual_pairs = facts(truth)
    found, found_nets, found_pins, found_pairs = facts(prediction)
    correct_values = {ref for ref in actual.keys() & found.keys() if actual[ref] == found[ref]}
    casefold_values = {ref for ref in actual.keys() & found.keys() if actual[ref].upper() == found[ref].upper()}
    matched = actual_pairs & found_pairs
    return {'components_gt': len(actual), 'components_found': len(actual.keys() & found.keys()),
            'components_spurious': sorted(found.keys() - actual.keys()),
            'component_values_exact': sorted(correct_values),
            'component_values_case_insensitive': sorted(casefold_values),
            'physical_pins_gt': len(actual_pins), 'physical_pins_found': len(actual_pins & found_pins),
            'physical_pins_spurious': sorted(found_pins - actual_pins),
            'connected_pin_pairs_gt': len(actual_pairs), 'connected_pin_pairs_found': len(found_pairs),
            'connected_pin_pairs_correct': len(matched), 'connected_pin_pairs_wrong': len(found_pairs - actual_pairs),
            'pair_precision': len(matched) / len(found_pairs) if found_pairs else 0.,
            'pair_recall': len(matched) / len(actual_pairs) if actual_pairs else 0.,
            'complete_nets_gt': len(actual_nets), 'complete_nets_matched': len(actual_nets & found_nets),
            'whole_graph_exact': actual == found and actual_nets == found_nets}


def retained(before_truth, before, after):
    truth, _, truth_pins, truth_pairs = facts(before_truth)
    old, _, old_pins, old_pairs = facts(before)
    new, _, new_pins, new_pairs = facts(after)
    errors = []
    if not truth.keys() & old.keys() <= new.keys():
        errors.append('lost recognized reference')
    for ref in truth.keys() & old.keys():
        if truth[ref] == old[ref] and new.get(ref) != truth[ref]:
            errors.append('lost exact source value ' + ref)
        elif truth[ref].upper() == old[ref].upper() and new.get(ref, '').upper() != truth[ref].upper():
            errors.append('lost correct value ' + ref)
    if not truth_pins & old_pins <= new_pins:
        errors.append('lost correct physical pin')
    if not truth_pairs & old_pairs <= new_pairs:
        errors.append('lost correct pin connectivity')
    if new.keys() - truth.keys() - old.keys():
        errors.append('additional spurious component')
    if new_pins - truth_pins - old_pins:
        errors.append('additional invalid physical pin')
    if new_pairs - truth_pairs - old_pairs:
        errors.append('additional incorrect pin connectivity')
    return errors


def main(args):
    from recognition_provenance import snapshot
    source_snapshot = snapshot()
    oc.available = lambda: False
    report = {'scope': 'recognition without native CAD cleanup; complete original graph recovery coverage',
              'visual_scope_review': 'Native targets may contain hidden pin/field information. This is not a complete image-accuracy certification.',
              'training_performed': False, 'cases': {}, 'regressions': []}
    records = []
    for source in args.sources:
        for line in (source / 'candidates.jsonl').read_text().splitlines():
            records.append((source, json.loads(line)))
    if args.include:
        records = [(source, row) for source, row in records if row['sample_id'] in args.include]
    # Older verified exports predate the explicit image_origin/false flags.
    # Establish provenance from their actual unchanged native source and XML,
    # rather than silently adding training-review metadata to those records.
    for source, row in records:
        xml = source / row['native_netlist']
        native = xml.parent / 'source.kicad_sch'
        assert hashlib.sha256(native.read_bytes()).hexdigest() == row['source_sha256']
        assert graph_signature(circuit_from_xml(xml)) == graph_signature(Circuit.model_validate(row['circuit']))
        assert row.get('image_origin') in (None, 'native_export_of_real_design')
    args.out.mkdir(parents=True, exist_ok=False)
    for source, row in records:
        identity = row['sample_id']
        if identity in report['cases']:
            raise ValueError('Duplicate original source identity.')
        image = source / row['image']
        xml = source / row['native_netlist']
        assert hashlib.sha256(image.read_bytes()).hexdigest() == row['image_sha256']
        assert hashlib.sha256(xml.read_bytes()).hexdigest() == row['native_netlist_sha256']
        assert row['netlist_equivalence_verified'] and not row.get('synthetic') and not row.get('ai_generated')
        assert (source / row['source_license']).is_file()
        print('Recognizing', identity, image.name, flush=True)
        folder = args.out / identity
        folder.mkdir()
        def profile(frame, event, arg):
            if event == 'return' and frame.f_code is dv.recognize.__code__:
                local = frame.f_locals
                data = {key: local[key] for key in ('ch', 'candidates', 'bxs', 'anchors')}
                data['tokens'] = [asdict(token) for token in local['toks']]
                (folder / 'diagnostics.json').write_text(json.dumps(data, indent=2))
        started = time.monotonic()
        failure = None
        try:
            if args.diagnostic:
                sys.setprofile(profile)
            graph = dv.extract(image, ROOT / 'backend/.state').model_dump()
        except (ValueError, RuntimeError) as error:
            graph = {'components': [], 'nets': []}
            failure = type(error).__name__ + ': ' + str(error)[:1000]
        finally:
            sys.setprofile(None)
        (folder / 'recognized.json').write_text(json.dumps(graph, indent=2))
        result = measure(row['circuit'], graph)
        result.update(source_image_sha256=row['image_sha256'], native_netlist_sha256=row['native_netlist_sha256'],
                      source=str(source), seconds=round(time.monotonic()-started, 2), failure=failure,
                      original_native_source_hash_verified=True,
                      recognizer_sha256=source_snapshot[str(Path(dv.__file__).resolve())],
                      recognizer_support_files=source_snapshot,
                      protected_model_sha256=hashlib.sha256((ROOT/'checkpoints/schematic-ocr/model.onnx').read_bytes()).hexdigest())
        report['cases'][identity] = result
        if args.baseline:
            old = json.loads((args.baseline / identity / 'recognized.json').read_text())
            errors = retained(row['circuit'], old, graph)
            report['regressions'].extend(identity + ': ' + error for error in errors)
        (args.out / 'report.json').write_text(json.dumps(report, indent=2))
        print(identity, {key: result[key] for key in ('components_found', 'components_gt', 'physical_pins_found', 'physical_pins_gt', 'whole_graph_exact', 'seconds')}, flush=True)
    assert snapshot() == source_snapshot, 'Recognizer code or library facts changed during evaluation.'
    report['passed_regression_check'] = not report['regressions'] if args.baseline else None
    (args.out / 'report.json').write_text(json.dumps(report, indent=2))
    if report['regressions']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', nargs='+', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--include', nargs='+', help='Optional source identities for diagnosis.')
    parser.add_argument('--diagnostic', action='store_true')
    main(parser.parse_args())
