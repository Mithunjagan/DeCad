"""Recover clipped pin digits from real pixels using independent package facts."""
from collections import Counter, defaultdict
import re
import sqlite3


def reference_numbers(value, path=None):
    """Return an unambiguous library pin-number set, never signal connections.

    Existing Capture value correction/substitution rules may identify the package
    used for checking a misread marking. They do not rewrite that marking here.
    """
    try:
        return _reference_numbers(value, path)
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return None


def _reference_numbers(value, path):
    from .recognition_catalog import connect, pin_tables
    from .orcad_capture import correct_value, SUBSTITUTES
    value = (value or '').upper()
    tables = pin_tables(value, path)
    if not tables and re.fullmatch(r'[A-Z0-9][A-Z0-9].{3,}', value):
        with connect(path) as db:
            if db is None:
                return None
            names = {r[0]: None for r in db.execute(
                'SELECT DISTINCT normalized FROM names WHERE normalized LIKE ?', (value[:2]+'%',))}
        value = correct_value(value, names)
        tables = pin_tables(value, path)
        if not tables and value in SUBSTITUTES:
            tables = pin_tables(SUBSTITUTES[value][1], path)
    sets = {frozenset(row['pins']) for row in tables if row['pins']}
    if len(sets) != 1:
        return None
    pins = sets.pop()
    return pins if len(pins) >= 4 and all(re.fullmatch(r'[1-9]\d{0,2}', pin) for pin in pins) else None


def recover(page, edge_pins, reads, components, ch, read_strip, *, numbers=reference_numbers):
    """Only replace an impossible pin after two readers agree at two widths.

    Existing valid/unique physical numbers are never reconsidered. The original
    label is preserved. Most observed pins must corroborate the library package;
    destination pins must be unused and unique. Soft/degraded pages are excluded.
    """
    if page.soft is not None:
        return []
    observed = defaultdict(Counter)
    for key, _, _, _, _, _, ref in edge_pins:
        if reads[key][0]:
            observed[ref][reads[key][0]] += 1
    valid = {}
    for ref, counts in observed.items():
        pins = numbers(components.get(ref))
        if pins and len(counts.keys() & pins) >= 8 and len(counts.keys() & pins)/len(counts) >= .9:
            valid[ref] = pins
    proposals = []
    for key, _, x, y, ux, uy, ref in edge_pins:
        old, labels = reads[key]
        pins = valid.get(ref)
        if not pins or not old or old in pins or observed[ref][old] != 1 or not labels:
            continue
        options = []
        for side in (-1, 1):
            original = {}
            num, _ = read_strip(page, x, y, ux, uy, ch, side, audit=original)
            primary = original.get('primary')
            if num != old or not primary or primary[1] >= .85:
                continue
            retry = []
            for width in (1.04, 1.08):
                audit = {}
                number, candidates = read_strip(page, x, y, ux, uy, ch*width, side, audit=audit)
                a, b = audit.get('primary'), audit.get('secondary')
                if (not number or number not in pins or number in observed[ref] or not a or not b
                        or a[0] != number or b[0] != number or min(a[1], b[1]) < .95
                        or not candidates or len(candidates) != 2 or candidates[0] != candidates[1]
                        or candidates[0] not in labels):
                    break
                retry.append(number)
            if len(retry) == 2 and len(set(retry)) == 1:
                options.append(retry[0])
        if len(set(options)) == 1:
            proposals.append((key, ref, old, options[0], labels))
    destinations = Counter((ref, new) for _, ref, _, new, _ in proposals)
    changed = []
    for key, ref, old, new, labels in proposals:
        if destinations[ref, new] == 1:
            reads[key] = new, labels
            changed.append((ref, old, new))
    return changed
