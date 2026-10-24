"""Exercise launcher path selection without installing packages or starting services."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which('powershell.exe') or shutil.which('pwsh')
pytestmark = pytest.mark.skipif(os.name != 'nt' or not POWERSHELL, reason='Windows PowerShell launcher')


@pytest.mark.parametrize('explicit', [False, True])
def test_kicad_path_from_environment_file_and_process_precedence(tmp_path, explicit):
    script=tmp_path/'start-native.ps1'
    shutil.copy2(ROOT/'start-native.ps1',script)
    (tmp_path/'backend').mkdir()
    configured=tmp_path/'configured-kicad'
    override=tmp_path/'override-kicad'
    (tmp_path/'backend/.env').write_text(f'S2SDN_KICAD_DIR="{configured}"\n',encoding='utf-8')
    env=dict(os.environ)
    env.pop('S2SDN_KICAD_DIR',None)
    if explicit:env['S2SDN_KICAD_DIR']=str(override)
    result=subprocess.run([POWERSHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],
                          env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=25,
                          creationflags=0x08000000)
    assert result.returncode != 0
    assert 'KiCad not found at' in result.stderr
    assert str(override if explicit else configured) in result.stderr
    assert not (tmp_path/'backend/.venv').exists()
