"""Project lifecycle and desktop conflict checks; no models or image recognition."""
import json
import os
import time
import socket
import pytest
from app import main
from test_operations import client,create
from app import project_trash


def test_project_recovery_preserves_files_and_rejects_overwrite(client):
    create(client)
    before=client.get('/projects/Circuit/file?name=Circuit.kicad_sch').content
    deleted=client.delete('/projects/Circuit');assert deleted.status_code==200
    receipt=deleted.json()['receipt'];assert 'Circuit' not in client.get('/projects').json()
    create(client)
    assert client.post('/projects/Circuit/restore',json={'receipt':receipt}).status_code==409
    client.delete('/projects/Circuit')
    assert client.post('/projects/Circuit/restore',json={'receipt':receipt}).status_code==200
    assert client.get('/projects/Circuit/file?name=Circuit.kicad_sch').content==before
    assert client.post('/projects/Circuit/restore',json={'receipt':'../escape'}).status_code==400
    client.post('/auth/logout')
    assert client.delete('/projects/Circuit').status_code==401
    assert client.post('/projects/Circuit/restore',json={'receipt':receipt}).status_code==401


def test_open_editor_blocks_delete(client):
    create(client);project=main.ROOT/'local'/'Circuit'
    (project/'~Circuit.kicad_sch.lck').write_text('external editor')
    assert client.delete('/projects/Circuit').status_code==409
    assert 'Circuit' in client.get('/projects').json()


@pytest.mark.skipif(os.name!='nt',reason='Real Windows directory sharing lock')
def test_force_recovers_real_windows_locked_subdirectory(client):
    import ctypes as ct
    from ctypes import wintypes as wt
    create(client);project=main.ROOT/'local'/'Circuit'
    folder=project/'orcad';folder.mkdir();(folder/'watcher.txt').write_bytes(b'Directory watcher fixture; not an EDA asset.')
    expected=project_trash.signature(project)
    kernel=ct.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wt.LPCWSTR,wt.DWORD,wt.DWORD,ct.c_void_p,wt.DWORD,wt.DWORD,wt.HANDLE];kernel.CreateFileW.restype=wt.HANDLE
    kernel.CloseHandle.argtypes=[wt.HANDLE]
    handle=kernel.CreateFileW(str(folder),0x80,3,None,3,0x02000000,None)
    assert handle!=ct.c_void_p(-1).value
    try:
        assert client.delete('/projects/Circuit').status_code==409
        result=client.delete('/projects/Circuit?force=true');assert result.status_code==200,result.text
        assert result.json()['retained_original'] is True
        receipt=result.json()['receipt'];snapshot=project.parent/'.trash'/receipt
        assert project_trash.signature(snapshot)==expected
        assert 'Circuit' not in client.get('/projects').json()
        assert client.get('/projects/Circuit/files').status_code==404
        assert client.post('/projects',json={'name':'Circuit'}).status_code==409
        # An unrelated watcher/application may keep writing. Undo preserves it.
        (folder/'later.txt').write_text('Retained after delete')
        assert client.post('/projects/Circuit/restore',json={'receipt':receipt}).status_code==200
        assert 'Circuit' in client.get('/projects').json()
        assert (folder/'later.txt').read_text()=='Retained after delete'
        assert not (project/project_trash.MARKER).exists()
        assert client.post('/projects/Circuit/restore',json={'receipt':receipt}).status_code==409
    finally:kernel.CloseHandle(handle)
    assert client.delete('/projects/Circuit').status_code==200


def test_failed_recovery_copy_keeps_original_visible(client,monkeypatch):
    from pathlib import Path
    create(client);project=main.ROOT/'local'/'Circuit';before=project_trash.signature(project)
    rename=Path.rename
    def blocked(path,target):
        if path==project:raise PermissionError('simulated directory watcher')
        return rename(path,target)
    def failed(source,target,**kwargs):
        (target/'partial').write_text('partial snapshot');raise PermissionError('copy denied')
    monkeypatch.setattr(Path,'rename',blocked);monkeypatch.setattr(project_trash.shutil,'copytree',failed)
    assert client.delete('/projects/Circuit?force=true').status_code==409
    assert 'Circuit' in client.get('/projects').json()
    assert project_trash.signature(project)==before
    assert list((project.parent/'.trash').iterdir())==[]


def test_changed_recovery_copy_keeps_original_visible(client,monkeypatch):
    from pathlib import Path
    create(client);project=main.ROOT/'local'/'Circuit';rename=Path.rename;copytree=project_trash.shutil.copytree
    def blocked(path,target):
        if path==project:raise PermissionError('simulated directory watcher')
        return rename(path,target)
    def changing(source,target,*args,**kwargs):
        copytree(source,target,*args,**kwargs)
        if Path(source)==project:(project/'later.txt').write_text('concurrent update')
    monkeypatch.setattr(Path,'rename',blocked);monkeypatch.setattr(project_trash.shutil,'copytree',changing)
    result=client.delete('/projects/Circuit?force=true')
    assert result.status_code==422 and 'changed during recovery' in result.text
    assert 'Circuit' in client.get('/projects').json()
    assert not (project/project_trash.MARKER).exists()
    assert list((project.parent/'.trash').iterdir())==[]


@pytest.mark.skipif(os.name!='nt',reason='Windows desktop coordination')
def test_browser_delete_closes_only_matching_owned_desktop(client,monkeypatch):
    from app import desktop_session
    calls=[];monkeypatch.setattr(desktop_session,'close_for_delete',lambda state,project:calls.append(project))
    create(client);project=main.ROOT/'local'/'Circuit'
    assert client.delete('/projects/Circuit').status_code==200
    assert calls==[project]


def test_force_recovers_stale_local_lock_with_all_files(client,monkeypatch):
    from app import project_locks
    monkeypatch.setattr(project_locks,'running_kicad_processes',lambda:[])
    create(client);project=main.ROOT/'local'/'Circuit'
    lock=project/'~Circuit.kicad_pro.lck'
    lock.write_text(json.dumps({'hostname':socket.gethostname(),'username':'test'}))
    expected={p.relative_to(project):p.read_bytes() for p in project.rglob('*') if p.is_file()}
    assert client.delete('/projects/Circuit').status_code==409
    result=client.delete('/projects/Circuit?force=true');assert result.status_code==200,result.text
    receipt=result.json()['receipt'];trash=project.parent/'.trash'/receipt
    assert not project.exists()
    assert {p.relative_to(trash):p.read_bytes() for p in trash.rglob('*') if p.is_file()}==expected
    assert client.post('/projects/Circuit/restore',json={'receipt':receipt}).status_code==200
    assert lock.read_bytes()==expected[lock.relative_to(project)]


def test_force_does_not_bypass_running_kicad(client,monkeypatch):
    from app import project_locks
    monkeypatch.setattr(project_locks,'running_kicad_processes',lambda:[{'Name':'eeschema.exe','ProcessId':123}])
    create(client);project=main.ROOT/'local'/'Circuit'
    lock=project/'~Circuit.kicad_pro.lck';lock.write_text(json.dumps({'hostname':socket.gethostname()}))
    response=client.delete('/projects/Circuit?force=true')
    assert response.status_code==409 and 'still be using' in response.text
    assert lock.is_file() and (project/'Circuit.kicad_sch').is_file()


def test_force_preserves_other_owned_project_editor(client,monkeypatch):
    from app import project_locks
    monkeypatch.setattr(project_locks,'running_kicad_processes',lambda:[{'Name':'eeschema.exe','ProcessId':123}])
    monkeypatch.setattr(project_locks,'verified_other_editors',lambda state,project:{123})
    create(client);project=main.ROOT/'local'/'Circuit'
    (project/'~Circuit.kicad_pro.lck').write_text(json.dumps({'hostname':socket.gethostname()}))
    assert client.delete('/projects/Circuit?force=true').status_code==200


@pytest.mark.parametrize('owner',[{'hostname':'other-computer'},None])
def test_force_rejects_foreign_or_unreadable_lock(client,monkeypatch,owner):
    from app import project_locks
    monkeypatch.setattr(project_locks,'running_kicad_processes',lambda:[])
    create(client);project=main.ROOT/'local'/'Circuit'
    lock=project/'~Circuit.kicad_pro.lck';lock.write_text(json.dumps(owner) if owner else 'unreadable')
    assert client.delete('/projects/Circuit?force=true').status_code==409
    assert lock.is_file() and (project/'Circuit.kicad_sch').is_file()


def test_force_fails_closed_when_process_inspection_fails(client,monkeypatch):
    from app import project_locks
    def unavailable():raise project_locks.OperationError('Could not verify whether KiCad is still running.')
    monkeypatch.setattr(project_locks,'running_kicad_processes',unavailable)
    create(client);project=main.ROOT/'local'/'Circuit'
    lock=project/'~Circuit.kicad_pro.lck';lock.write_text(json.dumps({'hostname':socket.gethostname()}))
    assert client.delete('/projects/Circuit?force=true').status_code==409
    assert lock.is_file()


@pytest.mark.skipif(os.name!='nt',reason='Windows native desktop session guard')
def test_dead_desktop_blocks_source_write(client):
    create(client);project=main.ROOT/'local'/'Circuit';path=project/'Circuit.kicad_sch'
    before=path.read_bytes();folder=main.STATE/'native-desktop'/'test';folder.mkdir(parents=True)
    (folder/'status.json').write_text(json.dumps({'project':str(project.resolve()),'updated':time.time()-60,'closed':False}))
    response=client.put('/projects/Circuit/file?name=Circuit.kicad_sch',json={'content':before.decode()+'\n'})
    assert response.status_code==422 and 'stopped responding' in response.text
    assert path.read_bytes()==before


@pytest.mark.skipif(os.name!='nt',reason='Windows native desktop session guard')
def test_external_schematic_lock_blocks_source_write(client):
    create(client);project=main.ROOT/'local'/'Circuit';path=project/'Circuit.kicad_sch'
    before=path.read_bytes();(project/'~Circuit.kicad_sch.lck').write_text('external editor')
    response=client.put('/projects/Circuit/file?name=Circuit.kicad_sch',json={'content':before.decode()+'\n'})
    assert response.status_code==422 and path.read_bytes()==before
