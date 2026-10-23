from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/eval'))
from sprint_gate import transient_gpu_failure


def test_gpu_execution_failure_can_retry_but_success_does_not(tmp_path):
    log=tmp_path/'worker.log';log.write_text('CUDNN_FE failure 11: CUDNN_BACKEND_API_FAILED')
    assert transient_gpu_failure(1,log)
    assert not transient_gpu_failure(0,log)


def test_accuracy_regression_cannot_be_retried_as_a_runtime_failure(tmp_path):
    log=tmp_path/'worker.log';log.write_text('CUDNN_FE failure')
    assert not transient_gpu_failure(3221226505,log,{'regressions':['additional incorrect pin connectivity']})


def test_unrelated_errors_are_not_classified_as_transient_gpu_failures(tmp_path):
    log=tmp_path/'worker.log';log.write_text('Source hash changed during evaluation')
    assert not transient_gpu_failure(1,log)
