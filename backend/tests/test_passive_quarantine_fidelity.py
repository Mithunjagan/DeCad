"""Cross-surface checks on an audited real-source observation excerpt."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from app.faculty_xml import from_circuit,serialize
from app.ingestion import Circuit
from app.local_recovery import recover_locally


FIXTURE=Path(__file__).parent/'fixtures/passive-quarantine-real.json'


def test_quarantine_reaches_canonical_inventory_and_independent_xml_reader():
    graph=json.loads(FIXTURE.read_text())['graph']
    circuit=Circuit.from_image_graph(recover_locally(graph))
    assert {(p.ref,p.pin) for p in circuit.physical_pins}=={('R1','1'),('R1','2')}
    nodes=ET.fromstring(serialize(from_circuit(circuit))).findall('./NetList/Nodes/Node')
    assert {n.attrib['NodeName'] for n in nodes}=={'R1_1','R1_2'}
    # Abstain from supplying the missing literal source label LORA_RST.
    assert next(n for n in circuit.nets if any(p.pin=='1' for p in n.nodes)).name=='N00063'
    assert next(n for n in circuit.nets if any(p.pin=='2' for p in n.nodes)).name=='+3V3'


def test_rejected_observations_and_source_regions_survive_review_serialization():
    graph=json.loads(FIXTURE.read_text())['graph']
    circuit=Circuit.from_image_graph(recover_locally(graph))
    restored=Circuit.model_validate_json(circuit.model_dump_json())
    rejected=restored.image_metadata['rejected_pin_observations']
    assert {r['node']['pin'] for r in rejected}=={'4','55'}
    assert all(r['net'] and r['anchor']['wire'] is not None for r in rejected)
    assert {'4','55'} <= {h.pin for h in restored.review_hotspots}
    assert all(not h.reviewed for h in restored.review_hotspots)
    assert any('R1.4' in w and 'R1.55' in w for w in restored.warnings)
