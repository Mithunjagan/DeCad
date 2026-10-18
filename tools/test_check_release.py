import json,tempfile,unittest
from pathlib import Path
from check_release import check,REQUIRED

class ReleaseChecks(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
 def write(self,name,data):
  p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data))
 def evidence(self):
  self.write('evidence/native.json',{'fixture':'test double only'})
  self.write('release-evidence.json',{n:{'status':'passed','artifact':'evidence/native.json','reviewer':'test','date':'2026-10-11'} for n in REQUIRED})
  self.write('checkpoints/circuit-lora/training-report.json',{'status':'trained_not_release_approved','training_pairs':100})
  self.write('checkpoints/circuit-lora/adapter/adapter_config.json',{})
  (self.root/'checkpoints/circuit-lora/adapter/adapter_model.safetensors').write_bytes(b'fixture')
  self.write('vision-evaluation.json',{'samples':100,'failed':0,'exact_graph_match_rate':1,'checks':[{'sample_id':str(i),'metrics':{'exact_graph_match':True}} for i in range(100)]})
  self.write('live-acceptance.json',{'passed':12,'checks':[{'passed':True} for _ in range(12)]})
 def test_missing_evidence_blocks_release(self):
  self.assertFalse(check(self.root)['ready_for_release_review'])
 def test_complete_recorded_evidence_allows_review_only(self):
  self.evidence();self.assertTrue(check(self.root)['ready_for_release_review'])
 def test_outside_artifact_cannot_satisfy_acceptance(self):
  self.evidence();self.write('release-evidence.json',{n:{'status':'passed','artifact':'../outside','reviewer':'test','date':'2026-10-11'} for n in REQUIRED})
  self.assertFalse(check(self.root)['ready_for_release_review'])
 def test_duplicate_evaluation_rows_block_release(self):
  self.evidence();self.write('vision-evaluation.json',{'samples':100,'failed':0,'exact_graph_match_rate':1,'checks':[{'sample_id':'same'} for _ in range(100)]})
  self.assertFalse(check(self.root)['ready_for_release_review'])

if __name__=='__main__':unittest.main()
