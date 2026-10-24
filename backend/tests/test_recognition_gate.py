import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/eval'))
from recognition_gate import regressions


def observation():
    return dict(scope='recognition_without_CAD_library_check', source_sha256='same', fresh_ocr=True,
                parts_found=24, values_ok=24, pins_exact=51, pins_present=53, parts_spurious=0,
                missed_parts=['U1', 'R1', 'R3', 'S1'], wrong_values=[],
                wrong_pins=[['U64.4', 'BAD', 'DD6']])


def test_same_totals_cannot_hide_losing_a_different_correct_pin():
    old = observation()
    new = copy.deepcopy(old)
    new['wrong_pins'] = [['U64.9', 'BAD', 'DD7']]
    assert any('lost previously correct' in e for e in regressions({'S1': old}, {'S1': new}))


def test_replay_and_different_sources_cannot_pass_acceptance():
    old = observation()
    new = {**old, 'fresh_ocr': False, 'source_sha256': 'different'}
    errors = regressions({'S1': old}, {'S1': new})
    assert any('replay' in e for e in errors) and any('incomparable' in e for e in errors)
    assert regressions({'S1': old}, {})


def test_serialized_baseline_and_live_score_rows_compare_identically():
    import json
    new = observation()
    new['wrong_pins'] = [tuple(row) for row in new['wrong_pins']]
    old = json.loads(json.dumps(new))
    assert regressions({'S1': old}, {'S1': new}) == []


def test_partial_value_count_improvement_does_not_count_placeholders_as_false_parts():
    old = {**observation(), 'parts_found': 0, 'values_ok': 0, 'pins_exact': 0, 'pins_present': 0,
           'parts_spurious': 11, 'missed_parts': [], 'wrong_pins': [], 'value_counts': {'TC514100': [7, 16]}}
    new = {**old, 'parts_spurious': 12, 'value_counts': {'TC514100': [8, 16]}}
    assert regressions({'S2': old}, {'S2': new}) == []
    new['value_counts'] = {'TC514100': [6, 16]}
    assert any('fewer TC514100' in e for e in regressions({'S2': old}, {'S2': new}))
