"""Graph/lesson/sample/validation CLI: python -m beyond_retrieval.workflows."""
import argparse
from pathlib import Path
from .data import read_json,write_json,case_events,digest,load_events
from .lessons import propose,freeze
from .runner import run,ScriptedProvider
from .validation import validate

def example_run(case,rows):
    nodes=[{'id':'h1','type':'hypothesis','text':'Credential attack','status':'open','evidence_ids':[]},
           {'id':'h2','type':'hypothesis','text':'User error','status':'open','evidence_ids':[]}]
    contract={'hypothesis_ids':['h1','h2'],'question':'Which login events are observed?','hypotheses':['Credential attack','User error'],
              'predictions':['Repeated failures followed by suspicious actions','Isolated failures without corroboration']}
    final_nodes=[{**n,'status':'unresolved'} for n in nodes]
    final_nodes.append({'id':'o1','type':'observation','text':'A failed login is recorded','status':'open','evidence_ids':[rows[0]['id']]})
    replies=[{'kind':'tool','tool':'search_events','args':{'contains':'failed_login'},'contract':contract,'graph_update':{'nodes':nodes,'edges':[]}},
             {'kind':'final','graph_update':{'nodes':final_nodes,'edges':[{'source':'o1','target':'h1','relation':'supports'},{'source':'o1','target':'h2','relation':'supports'}]},
              'answer':{'verdict':'insufficient_evidence','probabilities':{'malicious':.2,'benign':.2,'insufficient_evidence':.6},
                        'findings':[{'key':'failed_login','value':True,'evidence_ids':[rows[0]['id']]}],'unresolved':['Intent unknown']},
              'lesson_candidates':[{'trigger':'Investigate login activity and failed login',
                                    'procedure':'Retrieve authentication outcomes and seek independent corroborating activity before attributing malicious intent.',
                                    'limitation':'A failed login alone does not distinguish error from attack.'}]}]
    return run(case,rows,{'arm':'HS','model':'scripted-synthetic-fixture','max_calls':8,'max_tokens':100,'max_seconds':10},ScriptedProvider(replies))

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('propose-lessons');q.add_argument('run');q.add_argument('--split',required=True,choices=['train','dev']);q.add_argument('--output',required=True)
    q=sub.add_parser('freeze-lessons');q.add_argument('candidates');q.add_argument('reviews');q.add_argument('--output',required=True)
    q=sub.add_parser('validate');q.add_argument('--case',required=True);q.add_argument('--image');q.add_argument('--config');q.add_argument('--fixture');q.add_argument('--lessons');q.add_argument('--output',required=True)
    q=sub.add_parser('sample-run');q.add_argument('--case',required=True);q.add_argument('--output',required=True)
    a=p.parse_args()
    if Path(a.output).exists():raise SystemExit('Output exists; choose a new path')
    if a.command=='propose-lessons':value=propose(read_json(a.run),a.split)
    elif a.command=='freeze-lessons':value=freeze(read_json(a.candidates),read_json(a.reviews))
    else:
        case=read_json(a.case);rows=case_events(case,a.case)
        if a.command=='sample-run':
            # Sorted canonical IDs do not imply chronological order.
            rows=sorted(rows,key=lambda r:r['origin']['index'])
            case['evidence_hash']=digest(rows)
            value=example_run(case,rows)
        else:value=validate(case,rows,a.image,read_json(a.config) if a.config else None,read_json(a.fixture) if a.fixture else None,read_json(a.lessons) if a.lessons else None)
    write_json(a.output,value)
    print(a.output)

if __name__=='__main__':main()
