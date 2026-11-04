import tempfile
import unittest
from pathlib import Path
from beyond_retrieval.data import normalize,transform,digest
from beyond_retrieval.runner import run,ScriptedProvider,check_answer,valid_contract
from beyond_retrieval.evaluate import score,paired_bootstrap
from beyond_retrieval.tools import EvidenceTools

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        path=Path(self.tmp.name)/'logs'; path.write_text('host-a success\n\nhost-a failure\n')
        self.rows=normalize(path,'generic','env','auth')
        self.case={'id':'case','environment':'env','question':'Investigate','evidence_hash':digest(self.rows),'secret_label':'MUST_NOT_LEAK'}
        self.answer={'verdict':'insufficient_evidence','probabilities':{'malicious':0,'benign':0,'insufficient_evidence':1},'findings':[]}
    def test_original_offsets(self): self.assertEqual([r['origin']['index'] for r in self.rows],[1,3])
    def test_rename_preserves_provenance(self):
        changed=transform(self.rows,'V1',{'mapping':{'host-a':'host-b'}})
        self.assertEqual(changed[0]['id'],self.rows[0]['id']); self.assertIn('host-b',changed[0]['raw'])
    def test_hidden_records_unavailable(self):
        service=EvidenceTools(self.rows[:1])
        with self.assertRaises(ValueError): service.call('get_records',{'ids':[self.rows[1]['id']]})
    def test_v4(self): self.assertEqual(len(transform(self.rows,'V4',{'hide_ids':[self.rows[0]['id']]})),1)
    def test_environment_distractors(self):
        with self.assertRaises(ValueError): transform(self.rows,'V2',{},[{**self.rows[0],'environment':'other'}])
    def test_no_label_leak(self):
        def provider(messages,max_tokens,timeout):
            self.assertNotIn('MUST_NOT_LEAK',str(messages)); return {'kind':'final','answer':self.answer},1
        self.assertEqual(run(self.case,self.rows,{'arm':'A'},provider)['stages'][0]['status'],'completed')
    def test_hash_tamper(self):
        with self.assertRaises(ValueError): run(self.case,self.rows[:1],{'arm':'A'},None)
    def test_contract(self): self.assertFalse(valid_contract({'contract':{'question':'q','hypotheses':['x','x'],'predictions':['y','z']}}))
    def test_scripts_disabled(self):
        result=run(self.case,self.rows,{'arm':'A'},ScriptedProvider([{'kind':'script','code':'pass'},{'kind':'final','answer':self.answer}]))
        self.assertIn('Scripts disabled',str(result['trace']))
    def test_budget(self):
        result=run(self.case,self.rows,{'arm':'A','max_calls':1},ScriptedProvider([{'kind':'tool','tool':'list_sources'},{'kind':'tool','tool':'list_sources'}]))
        self.assertEqual(result['tool_calls'],1); self.assertIsNone(result['stages'][0]['answer'])
    def test_pending_review(self):
        r=run(self.case,self.rows,{'arm':'A'},ScriptedProvider([{'kind':'final','answer':self.answer}]))
        self.assertIsNone(score(r,{'mandatory':{},'admissible_verdicts':['insufficient_evidence']})['esr'])
    def test_staged_release(self):
        self.case['stages']=[[self.rows[0]['id']],[r['id'] for r in self.rows]]
        r=run(self.case,self.rows,{'arm':'A'},ScriptedProvider([{'kind':'tool','tool':'get_records','args':{'ids':[self.rows[1]['id']]}},{'kind':'final','answer':self.answer},{'kind':'tool','tool':'get_records','args':{'ids':[self.rows[1]['id']]}},{'kind':'final','answer':self.answer}]))
        self.assertTrue(any('error' in x and x['stage']==0 for x in r['trace']))
        self.assertTrue(any('result' in x and x['stage']==1 for x in r['trace']))
    def test_incomplete_pair_rejected(self):
        with self.assertRaises(ValueError): paired_bootstrap([{'arm':'A','environment':'e','base_case_id':'c','variant':'V0','model':'m','repeat':0,'esr':0}],'A','HS')
    def test_invalid_probability(self):
        self.answer['probabilities']['malicious']=float('nan')
        with self.assertRaises(ValueError): check_answer(self.answer,set())

if __name__=='__main__': unittest.main()
