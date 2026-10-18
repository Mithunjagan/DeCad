"""Read-only lookup of installed KiCad footprints for board planning."""
import os
from functools import lru_cache
from pathlib import Path
from .engine import OperationError
from .sexpr import parse, children, child


def library_root():
    roots = [
        *([Path(os.environ['KICAD_FOOTPRINT_DIR'])] if os.getenv('KICAD_FOOTPRINT_DIR') else []),
        Path(__file__).resolve().parents[2] / 'libraries' / 'kicad' / 'official' / 'footprints',
        Path('/usr/share/kicad/footprints'),
        Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
    ]
    root = next((p for p in roots if p.is_dir()), None)
    if root is None:
        raise OperationError('KiCad footprint libraries are unavailable. Install kicad-footprints or run tools/sync_libraries.py.')
    return root


@lru_cache(maxsize=2)
def catalog(root):
    return tuple(sorted(f'{p.parent.stem}:{p.stem}' for p in Path(root).glob('*.pretty/*.kicad_mod')))


def search(query, limit=30):
    tokens = query.casefold().split()
    if not tokens:
        return []
    return [name for name in catalog(str(library_root())) if all(t in name.casefold() for t in tokens)][:limit]


def details(identifier):
    parts = identifier.split(':')
    if len(identifier)>300 or any(ord(c)<32 for c in identifier) or len(parts) != 2 or any(not x or '..' in x or '/' in x or '\\' in x for x in parts):
        raise OperationError('Choose an exact Library:Footprint identifier.')
    root = library_root().resolve()
    path = (root / (parts[0] + '.pretty') / (parts[1] + '.kicad_mod')).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise OperationError('Footprint is not installed: ' + identifier)
    if path.stat().st_size > 5_000_000:
        raise OperationError('Footprint exceeds the supported size.')
    tree = parse(path.read_text())
    pads = sorted({str(p[1]) for p in children(tree, 'pad') if p[1]})
    description = child(tree, 'descr', ['', ''])[1]
    return {'id': identifier, 'pads': pads, 'description': description}
