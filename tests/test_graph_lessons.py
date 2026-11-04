import copy
import unittest
from beyond_retrieval.graph import HypothesisGraph
from beyond_retrieval.lessons import propose,freeze,retrieve
from beyond_retrieval.validation import http_check
from beyond_retrieval.runner import run,ScriptedProvider
from beyond_retrieval.data import digest

class GraphTests(unittest.TestCase):
    def setUp(self):
        self.g=HypothesisGraph();self.nodes=[{'id':h,'type':'hypothesis','text':h,'status':'open','evidence_ids':[]} for h in ('h1','h2')]
        self.g.update({'nodes':self.nodes},set(),0)
    def observation(self):return {'id':'o','type':'observation','text':'event','status':'open','evidence_ids':['e']}
    def test_hidden_evidence(self):
        with self.assertRaisesRegex(ValueError,'unobserved'):self.g.update({'nodes':[self.observation()]},set(),0)
        self.assertNotIn('o',self.g.nodes)
    def test_support_required(self):
        n={**self.nodes[0],'status':'supported'}
        with self.assertRaisesRegex(ValueError,'lacks'):self.g.update({'nodes':[n]},set(),0)
    def test_supported_and_history(self):
        self.g.update({'nodes':[self.observation(),{**self.nodes[0],'status':'supported'}],'edges':[{'source':'o','target':'h1','relation':'supports'}]},{'e'},1)
        self.assertEqual(self.g.nodes['h1']['status'],'supported');self.assertEqual(len(self.g.history),2)
    def test_edge_type(self):
        with self.assertRaisesRegex(ValueError,'types'):self.g.update({'edges':[{'source':'h1','target':'h2','relation':'supports'}]},set(),0)
    def test_cycle(self):
        with self.assertRaisesRegex(ValueError,'cycle'):self.g.update({'edges':[{'source':'h1','target':'h2','relation':'supersedes'},{'source':'h2','target':'h1','relation':'supersedes'}]},set(),0)
    def test_node_type_immutable(self):
        with self.assertRaisesRegex(ValueError,'change node type'):self.g.update({'nodes':[{**self.nodes[0],'type':'action'}]},set(),0)
    def test_final_needs_observed(self):
        rows=[{'id':'e','raw':'hello','source':'s','environment':'env','origin':{}}]
        a={'verdict':'benign','probabilities':{'malicious':0,'benign':1,'insufficient_evidence':0},'findings':[{'key':'x','value':1,'evidence_ids':['e']}]}
        result=run({'id':'c','environment':'env','question':'q','evidence_hash':digest(rows)},rows,{'arm':'A'},ScriptedProvider([{'kind':'final','answer':a}]))
        self.assertIsNone(result['stages'][0]['answer'])

class LessonTests(unittest.TestCase):
    def setUp(self):
        self.run={'case_id':'dev-V0','base_case_id':'dev','trace':[{'action':{'lesson_candidates':[{'trigger':'login','procedure':'Check corroboration','limitation':'No proof alone'}]}}]}
        self.c=propose(self.run,'dev');self.review={self.c[0]['id']:{'reviewer_id':'fixture','approved':True,'no_case_answers':True,'generalizable':True}}
    def test_no_test_learning(self):
        with self.assertRaises(ValueError):propose(self.run,'test')
    def test_review_required(self):
        with self.assertRaises(ValueError):freeze(self.c,{})
    def test_retrieval(self):self.assertEqual(len(retrieve(freeze(self.c,self.review),'login','test')),1)
    def test_base_case_exclusion(self):self.assertEqual(retrieve(freeze(self.c,self.review),'login','dev'),[])
    def test_bank_tamper(self):
        b=freeze(self.c,self.review);b['lessons'][0]['procedure']='changed'
        with self.assertRaises(ValueError):retrieve(b,'login','test')
    def test_http_transport(self):self.assertEqual(http_check()['status'],'passed')

if __name__=='__main__':unittest.main()

class IntegrationTests(unittest.TestCase):
    def test_graph_sample_and_retrieval(self):
        from beyond_retrieval.workflows import example_run
        from beyond_retrieval.lessons import propose,freeze
        rows=[{'id':'event','source':'auth','environment':'synthetic','raw':'failed_login','origin':{'index':1}}]
        case={'id':'dev','environment':'synthetic','question':'login investigation','evidence_hash':digest(rows)}
        result=example_run(case,rows)
        self.assertEqual(result['stages'][0]['status'],'completed')
        self.assertEqual(len([e for e in result['graph']['edges'] if e['relation']=='tests']),2)
        c=propose(result,'dev');reviews={c[0]['id']:{'reviewer_id':'test','approved':True,'generalizable':True,'no_case_answers':True}}
        bank=freeze(c,reviews)
        observed=[]
        final={'kind':'final','graph_update':{'nodes':[{'id':h,'type':'hypothesis','text':h,'status':'unresolved','evidence_ids':[]} for h in ('h1','h2')]},'answer':{'verdict':'insufficient_evidence','probabilities':{'malicious':0,'benign':0,'insufficient_evidence':1},'findings':[]}}
        def provider(messages,max_tokens,timeout):observed.extend(messages);return final,1
        result=run({**case,'id':'other'},rows,{'arm':'HS'},provider,lesson_bank=bank)
        self.assertEqual(len(result['retrieved_lessons']),1)
        self.assertIn('reviewed_procedures',str(observed))
    def test_failed_fixture_prevents_actual_execution(self):
        from unittest.mock import patch
        rows=[{'id':'e','source':'s','raw':'x','origin':{},'environment':'s'}]
        nodes=[{'id':h,'type':'hypothesis','text':h,'status':'open','evidence_ids':[]} for h in ('h1','h2')]
        action={'kind':'script','code':'pass','graph_update':{'nodes':nodes},'contract':{'question':'q','hypotheses':['a','b'],'hypothesis_ids':['h1','h2'],'predictions':['x','y']}}
        with patch('beyond_retrieval.runner.DockerScripts') as mock:
            mock.return_value.execute.return_value={'findings':['wrong']}
            r=run({'id':'c','environment':'s','question':'q','evidence_hash':digest(rows)},rows,{'arm':'HS','docker_image':'unused'},ScriptedProvider([action]),fixture={'fixtures':[{'rows':[],'expected':{'findings':[]}}]})
            self.assertEqual(mock.return_value.execute.call_count,1)
            self.assertIn('validation failed',str(r['trace']))
