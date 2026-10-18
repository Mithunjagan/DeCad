import importlib.util
from pathlib import Path
from app.assistant import template
spec=importlib.util.spec_from_file_location('vision_evaluation',Path(__file__).resolve().parents[2]/'training/evaluate.py')
evaluator=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluator)

def test_evaluation_checks_ground_and_actual_pin_groups():
 truth=template('divider');guess=truth.model_copy(deep=True)
 assert evaluator.metrics(truth,guess)['exact_graph_match']
 guess.nets[0].name='GND';guess.nets[2].name='VIN'
 result=evaluator.metrics(truth,guess)
 assert not result['exact_graph_match']
 assert result['pin_net_ground_partitions']['recall']<1

def test_component_value_error_is_not_hidden_by_net_match():
 truth=template('divider');guess=truth.model_copy(deep=True);guess.components[1].value='20k'
 result=evaluator.metrics(truth,guess)
 assert result['pin_net_ground_partitions']['f1']==1
 assert result['component_ref_value_library']['recall']<1
 assert not result['exact_graph_match']
