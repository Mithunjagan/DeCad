"""Recoverable project removal, including Windows directories held by watchers."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time
from .engine import OperationError, atomic_text

MARKER='.decad-trash.json'


def retained_receipt(project):
    marker=Path(project)/MARKER
    try:
        if marker.is_symlink():return None
        data=json.loads(marker.read_text())
        receipt=data.get('receipt','')
        if data.get('retained_original') is True and re.fullmatch(re.escape(Path(project).name)+r'-[0-9]{1,25}',receipt):return receipt
    except (OSError,ValueError,AttributeError,TypeError):pass
    return None


def signature(folder):
    result={}
    for path in Path(folder).rglob('*'):
        name=path.relative_to(folder).as_posix()
        if getattr(path.lstat(),'st_reparse_tag',0)==0xA0000003:
            raise OperationError('A project directory is a junction. Disconnect that link before force recovery.')
        if path.is_symlink():result[name]=('link',os.readlink(path))
        elif path.is_dir():result[name]=('directory',)
        elif path.is_file():
            digest=hashlib.sha256()
            with path.open('rb') as data:
                for chunk in iter(lambda:data.read(1024*1024),b''):digest.update(chunk)
            result[name]=('file',digest.hexdigest())
        else:raise OperationError('A project asset is unavailable. Finish its updates and retry.')
    return result


def move_to_trash(project,target,force=False):
    project=Path(project).resolve();target=Path(target)
    trash=project.parent/'.trash'
    # This helper never operates outside the exact user's project trash.
    if target.parent.resolve()!=trash.resolve() or trash.is_symlink() or target.is_symlink():raise OperationError('Invalid project trash location.')
    if target.exists():raise OperationError('The trash recovery location already exists.')
    for attempt in range(3):
        try:project.rename(target);return False
        except PermissionError:
            if attempt<2:time.sleep(.1)
            elif not force:raise
    if (project/MARKER).exists() or (project/MARKER).is_symlink():raise OperationError('A recovery marker already exists. Restore the project before deleting it again.')
    # Never force-close an unrelated application or discard an open file. A
    # complete verified snapshot plus a tombstone makes removal transactional.
    before=signature(project)
    target.mkdir();identity=target.stat().st_ino
    try:
        shutil.copytree(project,target,symlinks=True,dirs_exist_ok=True)
        if signature(project)!=before or signature(target)!=before:
            raise OperationError('The project changed during recovery. Finish its updates and retry.')
        atomic_text(project/MARKER,json.dumps({'receipt':target.name,'retained_original':True,'snapshot_verified':True}))
    except Exception:
        # Delete only our partial snapshot, after checking the final absolute
        # path, symlink status and directory identity again.
        if target.exists() and target.resolve().parent==trash.resolve() and not target.is_symlink() and target.stat().st_ino==identity:
            def writable_retry(operation,path,exc):
                candidate=Path(path)
                if candidate.is_symlink() or not candidate.resolve().is_relative_to(target.resolve()):raise exc[1]
                candidate.chmod(candidate.stat().st_mode|stat.S_IWRITE)
                operation(path)
            shutil.rmtree(target,onerror=writable_retry)
        raise
    return True


def restore_retained(project,receipt,snapshot):
    project=Path(project);snapshot=Path(snapshot)
    if not project.is_dir() or project.is_symlink() or retained_receipt(project)!=receipt:return False
    if not snapshot.is_dir():raise OperationError('The verified recovery copy is missing.')
    # Keep any later writes made by the external application holding the folder.
    # Restoring never overwrites the retained original with an older snapshot.
    (project/MARKER).unlink()
    return True
