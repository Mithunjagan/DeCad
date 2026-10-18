"""Local desktop editor coordination. No network listener or foreign process control."""
import json
import os
import time
import uuid
from pathlib import Path
from .engine import OperationError, atomic_text


def sessions(state, project):
    project=str(Path(project).resolve())
    for path in (Path(state)/'native-desktop').glob('*/status.json'):
        try:
            status=json.loads(path.read_text())
            if status.get('project')==project and not status.get('closed'):
                yield path.parent,status
        except (OSError,ValueError):continue


def request(folder, status, action, timeout=22):
    if time.time()-status.get('updated',0)>6:
        raise OperationError('The desktop editor stopped responding. Close its KiCad window before editing this project.')
    key=uuid.uuid4().hex;folder=Path(folder)
    command=folder/(key+'.request.json');reply=folder/(key+'.reply.json')
    atomic_text(command,json.dumps({'id':key,'action':action,'created':time.time(),'project':status['project']}))
    deadline=time.monotonic()+timeout
    try:
        while time.monotonic()<deadline:
            if reply.exists():
                result=json.loads(reply.read_text())
                if not result.get('ok'):raise OperationError(result.get('error','Desktop editor operation failed.'))
                return result
            time.sleep(.06)
        raise OperationError('Finish or cancel the dialog in KiCad, then retry. The app has not changed your schematic.')
    finally:
        command.unlink(missing_ok=True);reply.unlink(missing_ok=True)


def suspend(state, project):
    matches=list(sessions(state,project))
    for folder,status in matches:request(folder,status,'suspend')
    if not matches and any(Path(project).glob('~*.kicad_sch.lck')):
        raise OperationError('This project is open in another KiCad window. Save and close that editor before changing it in DeCad.')
    return bool(matches)


def resume(state, project):
    for folder,status in sessions(state,project):request(folder,status,'resume')


def close_for_delete(state,project):
    # Browser windows do not own the desktop bridge. Coordinate in the backend
    # so deleting there still saves/closes the matching native editor first.
    for folder,status in sessions(state,project):request(folder,status,'release')

