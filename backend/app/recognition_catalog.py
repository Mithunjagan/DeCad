"""Read-only names and physical-pin facts for schematic recognition.

The catalog contains local library metadata, never circuit instance connections.
It is reference knowledge, not generated training data. Missing/ambiguous facts
leave the image reading unchanged.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]


def recover_marking(text):
    """Unambiguous catalog identity within one substitution, no family guesses."""
    import re
    value=text.strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{3,}',value):return None
    try:
        with connect() as db:
            if db is None:return None
            if db.execute('SELECT 1 FROM names WHERE normalized=? LIMIT 1',(value,)).fetchone():return value
            # Only logic/memory-shaped captions qualify for fuzzy matching.
            if not re.search(r'\d{2}',value):return None
            matches=set()
            for i in range(len(value)):
                pattern=value[:i]+'_'+value[i+1:]
                for row in db.execute('SELECT DISTINCT normalized FROM names WHERE length(normalized)=? AND normalized LIKE ?',(len(value),pattern)):
                    if sum(a!=b for a,b in zip(value,row[0]))==1:matches.add(row[0])
            return next(iter(matches)) if len(matches)==1 else None
    except (OSError,sqlite3.Error):return None


@contextmanager
def connect(path=None):
    path = Path(path or os.getenv('S2SDN_COMPONENT_CATALOG') or ROOT/'backend/.state/recognition-catalog.sqlite')
    connection = None
    try:
        if path.is_file():
            connection = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=1)
            try:
                complete = connection.execute("SELECT value FROM metadata WHERE key='complete'").fetchone()
            except sqlite3.Error:
                complete = None
            if complete != ('1',):
                connection.close(); connection = None
        yield connection
    finally:
        if connection is not None:
            connection.close()


def correct_literal(value, path=None):
    """One O/0 or I/L/1 slip, only if the full alternative name is unique.

    Exact known names, numeric substitutions, insertions, deletions and multiple
    alternatives are never corrected. Original casing of other glyphs survives.
    """
    try:
        with connect(path) as connection:
            if connection is None:
                return value
            known = lambda name: connection.execute('SELECT 1 FROM names WHERE normalized=? LIMIT 1', (name,)).fetchone() is not None
            upper = value.upper()
            if known(upper):
                return value
            confusable = {'0':'O', 'O':'0', '1':'IL', 'I':'1', 'L':'1'}
            matches = set()
            for index, char in enumerate(upper):
                for alternative in confusable.get(char, ''):
                    candidate = upper[:index]+alternative+upper[index+1:]
                    if known(candidate):
                        matches.add((index, alternative))
            if len(matches) == 1:
                index, alternative = matches.pop()
                return value[:index]+alternative+value[index+1:]
    except (OSError, sqlite3.Error, ValueError):
        pass
    return value


def pin_tables(value, path=None):
    """All exact-name package alternatives; physical numbers retain their names.

    Callers must resolve package ambiguity from image evidence. No alternative
    is silently selected. KiCad inheritance stays within its original library.
    """
    try:
        with connect(path) as connection:
            if connection is None:
                return []
            rows = connection.execute('SELECT p.id,p.source,p.name,p.pins,p.parent FROM packages p JOIN names n ON n.package=p.id WHERE n.normalized=?', (value.upper(),)).fetchall()
            def inherited(row, seen=()):
                identity, source, name, pins, parent = row
                if identity in seen or len(seen) > 32:
                    raise ValueError('Invalid symbol inheritance.')
                result = {}
                if parent:
                    ancestor = connection.execute('SELECT id,source,name,pins,parent FROM packages WHERE source=? AND name=?', (source,parent)).fetchone()
                    if ancestor is None:
                        return {}
                    result.update(inherited(ancestor, (*seen,identity)))
                result.update(json.loads(pins))
                return result
            return [{'source': row[1], 'package': row[2], 'pins': inherited(row)} for row in rows]
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return []
