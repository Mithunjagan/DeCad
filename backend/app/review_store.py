"""Atomic canonical review drafts, independent of lossy symbol substitution.

All review exports use this same Circuit. Native workspace edits are separate;
drafts are explicitly reopened and never silently substituted for native edits.
"""
import hashlib
import json
import time
from pathlib import Path

from .engine import OperationError,atomic_text,project_lock
from .ingestion import Circuit


def load(project):
    path=Path(project)/'.review/circuit.json'
    if not path.exists():raise OperationError('No saved review draft. Analyze a source and save its review first.')
    data=path.read_bytes()
    return {'circuit':Circuit.model_validate_json(data).model_dump(),
            'revision':hashlib.sha256(data).hexdigest()}


def save(project,circuit,expected=None):
    project=Path(project);path=project/'.review/circuit.json'
    with project_lock(project):
        if expected is not None and (not path.exists() or load(project)['revision']!=expected):
            raise OperationError('Review draft changed. Reopen the saved review before overwriting it.')
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            history=path.parent/'history';history.mkdir(exist_ok=True)
            atomic_text(history/f'{time.time_ns()}.json',path.read_text(encoding='utf-8'))
            for old in sorted(history.glob('*.json'))[:-50]:old.unlink()
        atomic_text(path,json.dumps(circuit.model_dump(),ensure_ascii=False,indent=2))
    return load(project)


def undo(project,expected):
    project=Path(project)
    with project_lock(project):
        current=load(project)
        if current['revision']!=expected:raise OperationError('Review draft changed. Reopen it before undo.')
        history=project/'.review/history';files=sorted(history.glob('*.json'))
        if not files:raise OperationError('No earlier saved review.')
        restored=Circuit.model_validate_json(files[-1].read_bytes())
        atomic_text(project/'.review/circuit.json',restored.model_dump_json(indent=2));files[-1].unlink()
        return load(project)
