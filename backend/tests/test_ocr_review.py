import pytest
from app.vision_local import ocr_candidates
from app.engine import OperationError
from test_operations import client
HEADER='level\tleft\ttop\twidth\theight\tconf\ttext\n'
def test_spatial_ocr_ignores_net_labels_and_distant_values():
 circuit=ocr_candidates(HEADER+'5\t100\t100\t30\t20\t95\tR1\n5\t100\t135\t40\t20\t95\t10k\n5\t500\t100\t30\t20\t99\tC4\n5\t500\t135\t50\t20\t99\tGND\n')
 assert [(c.ref,c.value) for c in circuit.components]==[('R1','10k')]
 assert not circuit.nets and 'incomplete or wrong' in circuit.warnings[0]

def test_ocr_ambiguity_does_not_guess_references():
 with pytest.raises(OperationError):ocr_candidates(HEADER+'5\t100\t100\t30\t20\t99\tRt\n5\t100\t135\t40\t20\t95\t10k\n')

@pytest.mark.parametrize('ref',['R1','C4','U2'])
def test_text_only_ocr_never_invents_missing_values(ref):
 with pytest.raises(OperationError,match='reference/value pairs'):
  ocr_candidates(HEADER+f'5\t100\t100\t30\t20\t99\t{ref}\n5\t100\t135\t40\t20\t99\tGND\n')

def test_status_reports_actual_ocr_mode(client,monkeypatch):
 from app import main
 monkeypatch.setenv('IMAGE_MODE','ocr')
 monkeypatch.setattr(main.shutil,'which',lambda name:'/usr/bin/tesseract' if name=='tesseract' else None)
 result=client.get('/vision/status').json()
 assert result['mode']=='ocr' and result['ready']
 assert result['connectivity_verified'] is False and result['model'] is None
