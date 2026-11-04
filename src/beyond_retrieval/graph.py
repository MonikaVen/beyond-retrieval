"""Typed, transactional investigation graph; semantics remain agent assertions."""
import copy
from .data import digest

TYPES={'hypothesis','observation','action','conclusion'}
RELATIONS={'supports','contradicts','tests','derived_from','supersedes'}
GRAPH_PROMPT='''For H/HS arms, use graph_update on actions and final answers:
{"nodes":[{"id":"h1","type":"hypothesis","text":"Claim","status":"open","evidence_ids":[]}],
"edges":[{"source":"o1","target":"h1","relation":"supports"}]}.
Node types: hypothesis, observation, action, conclusion. Hypothesis statuses:
open, supported, refuted, unresolved. Other nodes use status open.
Observation/conclusion nodes require evidence_ids from records already retrieved.
Supports/contradicts edges run observation->hypothesis. Tests edges run action->hypothesis.
Derived_from runs conclusion->observation. Supersedes links same-type nodes.
Contracts must also include hypothesis_ids (at least two distinct existing IDs)
and one prediction per ID, in matching order. Action nodes and tests edges are
recorded automatically by the runner. Keep at least two hypotheses before tools and at final. Supported/refuted hypotheses
need matching support/contradiction edges. Updates may change status/text but cannot
change type. Graph state is structurally validated, not semantically proven.
'''

class HypothesisGraph:
    def __init__(self): self.nodes={}; self.edges=[]; self.history=[]
    def update(self, patch, observed, stage):
        if not isinstance(patch,dict): raise ValueError('graph_update must be an object')
        nodes=copy.deepcopy(self.nodes); edges=copy.deepcopy(self.edges)
        for n in patch.get('nodes',[]):
            if not isinstance(n,dict) or not all(k in n for k in ('id','type','text','status','evidence_ids')): raise ValueError('Incomplete graph node')
            if not isinstance(n['id'],str) or not n['id'] or n['type'] not in TYPES or not isinstance(n['text'],str) or not n['text']: raise ValueError('Invalid graph node')
            allowed={'open','supported','refuted','unresolved'} if n['type']=='hypothesis' else {'open'}
            if n['status'] not in allowed: raise ValueError('Invalid node status')
            if not isinstance(n['evidence_ids'],list) or not set(n['evidence_ids'])<=observed: raise ValueError('Graph references unobserved evidence')
            if n['type'] in {'observation','conclusion'} and not n['evidence_ids']: raise ValueError('Observation/conclusion needs provenance')
            if n['id'] in nodes and nodes[n['id']]['type']!=n['type']: raise ValueError('Cannot change node type')
            nodes[n['id']]=copy.deepcopy(n)
        for e in patch.get('edges',[]):
            if e.get('relation') not in RELATIONS or e.get('source') not in nodes or e.get('target') not in nodes: raise ValueError('Invalid graph edge')
            a,b=nodes[e['source']],nodes[e['target']]; rel=e['relation']
            expected={'supports':('observation','hypothesis'),'contradicts':('observation','hypothesis'),'tests':('action','hypothesis'),'derived_from':('conclusion','observation')}
            if e['source']==e['target'] or (rel in expected and (a['type'],b['type'])!=expected[rel]) or (rel=='supersedes' and a['type']!=b['type']): raise ValueError('Invalid edge types')
            if e not in edges: edges.append(copy.deepcopy(e))
        # Supersession must remain acyclic; contradictory evidence may coexist.
        adjacency={k:[] for k in nodes}
        for e in edges:
            if e['relation']=='supersedes': adjacency[e['source']].append(e['target'])
        visiting=set(); done=set()
        def visit(k):
            if k in visiting: raise ValueError('Supersession cycle')
            if k in done:return
            visiting.add(k)
            for v in adjacency[k]:visit(v)
            visiting.remove(k);done.add(k)
        for k in nodes:visit(k)
        for n in nodes.values():
            relation={'supported':'supports','refuted':'contradicts'}.get(n['status'])
            if relation and not any(e['target']==n['id'] and e['relation']==relation for e in edges): raise ValueError('Hypothesis status lacks evidence edge')
        if sum(n['type']=='hypothesis' for n in nodes.values())<2: raise ValueError('At least two hypotheses required')
        self.nodes,self.edges=nodes,edges
        self.history.append({'stage':stage,'patch':copy.deepcopy(patch),'state_hash':digest(self.snapshot())})
    def snapshot(self): return {'nodes':list(self.nodes.values()),'edges':self.edges,'semantic_status':'unverified_agent_assertions'}
