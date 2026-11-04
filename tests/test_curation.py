import copy
import json
import tempfile
import unittest
from pathlib import Path
from beyond_retrieval.curation import curate,audit,CHECKS
from beyond_retrieval.runner import run

class CurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        example=Path(__file__).resolve().parents[1]/'examples'/'curation'
        self.spec=json.loads((example/'manifest.json').read_text())
        self.spec['sources'][0]['path']=str(example/'telemetry.jsonl')
    def build(self):
        p=self.root/'manifest.json'; p.write_text(json.dumps(self.spec))
        return curate(p,self.root/'out')
    def test_draft_is_blocked(self):
        result=self.build(); self.assertEqual(result['draft'],1)
        c=json.loads((self.root/'out/public/synthetic-v0/case.json').read_text())
        with self.assertRaisesRegex(ValueError,'Draft'): run(c,[],{'arm':'A'},None)
    def test_public_private_separation(self):
        self.build(); text=(self.root/'out/public/synthetic-v0/case.json').read_text()
        self.assertNotIn('rubric',text); self.assertNotIn('admissible_verdicts',text)
        self.assertTrue((self.root/'out/private/synthetic-v0.json').exists())
    def test_hash_mismatch(self):
        self.spec['sources'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SHA256'): self.build()
    def test_missing_offset(self):
        self.spec['cases'][0]['evidence'][0]['indices']=[99]
        with self.assertRaisesRegex(ValueError,'index missing'): self.build()
    def test_scenario_leak(self):
        c=copy.deepcopy(self.spec['cases'][0]); c.update(id='other',base_case_id='other',split='test'); self.spec['cases'].append(c)
        with self.assertRaisesRegex(ValueError,'crosses splits'): self.build()
    def test_ait_split(self):
        self.spec['sources'][0].update(dataset='ait',environment='shaw')
        with self.assertRaisesRegex(ValueError,'AIT environment'): self.build()
    def test_hidden_rubric_support(self):
        c=self.spec['cases'][0]; c.update(variant='V4',hide=[{'source':'auth','indices':[1]}])
        with self.assertRaisesRegex(ValueError,'unavailable evidence'): self.build()
    def test_approved_review(self):
        self.spec['cases'][0]['review']={'reviewer_id':'synthetic-test-reviewer',**dict.fromkeys(CHECKS,True)}
        self.assertEqual(self.build()['approved'],1)
    def test_evidence_tamper(self):
        self.build(); p=self.root/'out/public/synthetic-v0/events.jsonl'; p.write_text(p.read_text().replace('bob','eve'))
        with self.assertRaisesRegex(ValueError,'Evidence changed'): audit(self.root/'out')
    def test_rubric_tamper(self):
        self.build(); p=self.root/'out/private/synthetic-v0.json'; p.write_text(p.read_text().replace('bob','eve'))
        with self.assertRaisesRegex(ValueError,'rubric/review changed'): audit(self.root/'out')
    def test_no_overwrite(self):
        self.build()
        with self.assertRaisesRegex(ValueError,'already exists'): self.build()
    def test_v5_stage_support(self):
        c=self.spec['cases'][0]; c.update(variant='V5',initial_evidence=[{'source':'auth','indices':[2]}],provisional_rubric=copy.deepcopy(c['rubric']))
        with self.assertRaisesRegex(ValueError,'unavailable evidence'): self.build()
    def test_valid_v5(self):
        c=self.spec['cases'][0]; c.update(variant='V5',initial_evidence=[{'source':'auth','indices':[1]}],provisional_rubric=copy.deepcopy(c['rubric']))
        self.assertEqual(self.build()['integrity'],'passed')

if __name__=='__main__': unittest.main()
