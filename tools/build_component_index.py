#!/usr/bin/env python3
"""Build a fast, searchable SQLite component and SPICE model index from downloaded libraries."""
from __future__ import annotations
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / 'libraries'
INDEX_DB = LIB_DIR / 'index' / 'components.db'

# Import s-expression parser from backend
sys.path.insert(0, str(ROOT / 'backend'))
from app.sexpr import parse, children, child

def init_db(conn: sqlite3.Connection):
    with conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lib_id TEXT UNIQUE,
                library TEXT,
                name TEXT,
                description TEXT,
                keywords TEXT,
                footprint TEXT,
                pin_count INTEGER,
                pins_json TEXT
            );
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_symbols_lib ON symbols(library);')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS spice_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                model_type TEXT,
                definition TEXT,
                source_file TEXT
            );
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_spice_name ON spice_models(name);')

def index_kicad_sym_file(path: Path, lib_name: str, conn: sqlite3.Connection):
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
        tree = parse(content)
    except Exception as e:
        print(f"[!] Error parsing {path.name}: {e}")
        return 0

    records = []
    for sym in children(tree, 'symbol'):
        name = sym[1] if len(sym) > 1 and isinstance(sym[1], str) else None
        if not name or ':' in name: # skip sub-unit symbols if named like Symbol_1_1
            continue

        lib_id = f"{lib_name}:{name}"
        props = {p[1]: p[2] for p in children(sym, 'property') if len(p) >= 3}
        desc = props.get('Description', '')
        keywords = props.get('ki_keywords', '')
        footprint = props.get('Footprint', '')

        pins = []
        for pin in children(sym, 'pin'):
            num = child(pin, 'number')
            pname = child(pin, 'name')
            pnum = num[1] if num and len(num) > 1 else ''
            pstr = pname[1] if pname and len(pname) > 1 else ''
            if pnum:
                pins.append({'number': pnum, 'name': pstr})

        import json
        records.append((lib_id, lib_name, name, desc, keywords, footprint, len(pins), json.dumps(pins)))

    if records:
        with conn:
            conn.executemany('''
                INSERT OR REPLACE INTO symbols (lib_id, library, name, description, keywords, footprint, pin_count, pins_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', records)
    return len(records)

def index_symbols(conn: sqlite3.Connection):
    total = 0
    search_paths = [
        LIB_DIR / 'kicad' / 'official' / 'symbols',
        LIB_DIR / 'kicad' / 'community',
        Path('/usr/share/kicad/symbols'),
        Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols')
    ]
    env_sym = os.getenv('KICAD_SYMBOL_DIR')
    if env_sym:
        search_paths.insert(0, Path(env_sym))

    for base in search_paths:
        if not base.exists():
            continue
        print(f"[*] Indexing symbols in {base}...")
        for sym_file in base.rglob('*.kicad_sym'):
            # If inside a .kicad_symdir (e.g. Timer.kicad_symdir/NE555P.kicad_sym), the library is Timer
            if sym_file.parent.name.endswith('.kicad_symdir'):
                lib_name = sym_file.parent.name.removesuffix('.kicad_symdir')
            else:
                lib_name = sym_file.stem
            count = index_kicad_sym_file(sym_file, lib_name, conn)
            total += count
    return total

def index_spice_models(conn: sqlite3.Connection):
    total = 0
    search_paths = [
        LIB_DIR / 'spice',
        LIB_DIR / 'qucs_s'
    ]
    model_re = re.compile(r'^\s*\.model\s+([A-Za-z0-9_#$]+)\s+([A-Za-z0-9_]+)\s*(.*)', re.I | re.M)
    subckt_re = re.compile(r'^\s*\.subckt\s+([A-Za-z0-9_#$]+)\s*(.*)', re.I | re.M)

    for base in search_paths:
        if not base.exists():
            continue
        print(f"[*] Indexing SPICE models in {base}...")
        for f in base.rglob('*'):
            if f.suffix.lower() in ['.mod', '.model', '.lib', '.sub', '.cir', '.dio', '.bjt', '.mos']:
                try:
                    text = f.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    continue
                records = []
                for m in model_re.finditer(text):
                    m_name = m.group(1).upper()
                    m_type = m.group(2).upper()
                    records.append((m_name, m_type, m.group(0).strip(), str(f.relative_to(ROOT))))
                for s in subckt_re.finditer(text):
                    s_name = s.group(1).upper()
                    records.append((s_name, 'SUBCKT', s.group(0).strip(), str(f.relative_to(ROOT))))

                if records:
                    with conn:
                        conn.executemany('''
                            INSERT OR REPLACE INTO spice_models (name, model_type, definition, source_file)
                            VALUES (?, ?, ?, ?)
                        ''', records)
                    total += len(records)
    return total

def main():
    INDEX_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(INDEX_DB))
    init_db(conn)
    print(f"[*] Connected to {INDEX_DB}")

    sym_count = index_symbols(conn)
    spice_count = index_spice_models(conn)
    conn.close()

    print(f"[+] Indexing completed successfully!")
    print(f"    - Symbols indexed: {sym_count}")
    print(f"    - SPICE models/subcircuits indexed: {spice_count}")

if __name__ == '__main__':
    main()
