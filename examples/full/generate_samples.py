"""Regenerate synthetic fixtures. No downloaded real-world records or benchmark claims."""
import copy
import hashlib
from pathlib import Path
from beyond_retrieval.data import write_json,load_events,digest
from beyond_retrieval.curation import curate,CHECKS,VARIANT_CHECKS
from beyond_retrieval.workflows import example_run
from beyond_retrieval.lessons import propose,freeze
from beyond_retrieval.validation import validate,SCRIPT

root=Path(__file__).resolve().parent
# Self-authored fictional telemetry; all addresses/entities are illustrative.
records=[
 {'timestamp':'2026-01-01T00:00:00Z','host':'host-a','event':'failed_login','user':'bob'},
 {'timestamp':'2026-01-01T00:01:00Z','host':'host-a','event':'login_success','user':'bob'},
 {'timestamp':'2026-01-01T00:02:00Z','host':'host-a','event':'heartbeat'},
]
import json
telemetry=root/'auth.jsonl';telemetry.write_text(''.join(json.dumps(r)+'\n' for r in records))
ref=lambda indices:[{'source':'auth','indices':indices}]
rub={'mandatory':{'failed_login_user':'bob','successful_login_user':'bob'},
     'support':{'failed_login_user':ref([1]),'successful_login_user':ref([2])},
     'admissible_verdicts':['insufficient_evidence'],'unique_label':'insufficient_evidence'}
partial=copy.deepcopy(rub);del partial['mandatory']['successful_login_user'];del partial['support']['successful_login_user']
base={'base_case_id':'sample-login','split':'dev','scenario_group':'fictional-authentication','question':'Investigate login activity. Which outcomes are observed, and is malicious intent established?',
      'evidence':ref([1,2]),'rubric':rub}
cases=[]
for variant in ['V0','V1','V2','V4','V5']:
    c=copy.deepcopy(base);c.update(id='sample-'+variant,variant=variant)
    c['review']={'reviewer_id':'synthetic-fixture-author','review_scope':'Self-authored fictional example, not independent benchmark review',**dict.fromkeys(CHECKS+VARIANT_CHECKS.get(variant,[]),True)}
    if variant=='V1':c['transform']={'mapping':{'host-a':'host-z'}}
    if variant=='V2':c['distractors']=ref([3])
    if variant=='V4':c.update(hide=ref([2]),rubric=partial)
    if variant=='V5':c.update(initial_evidence=ref([1]),provisional_rubric=partial)
    cases.append(c)
manifest={'sources':[{'id':'auth','dataset':'generic','environment':'fictional-dev','version':'synthetic-1','license':'CC0-1.0','url':'urn:synthetic:beyond-retrieval:full-samples','path':'auth.jsonl','sha256':hashlib.sha256(telemetry.read_bytes()).hexdigest()}],'cases':cases}
write_json(root/'manifest.json',manifest)
if (root/'curated').exists():
    raise SystemExit('curated output exists; run this generator in a fresh copy without generated outputs')
curate(root/'manifest.json',root/'curated')
# The scripted demonstration has its own reduced mandatory rubric.
rows=load_events(root/'curated/public/sample-V0/events.jsonl');rows.sort(key=lambda r:r['origin']['index'])
case={'id':'lesson-development-example','base_case_id':'lesson-development-example','environment':'fictional-dev','question':base['question'],'events':'sample-events.jsonl','evidence_hash':digest(rows)}
from beyond_retrieval.data import save_events
save_events(root/'sample-events.jsonl',rows);write_json(root/'sample-case.json',case)
result=example_run(case,rows);write_json(root/'graph-run.json',result);write_json(root/'hypothesis-graph.json',result['graph'])
candidates=propose(result,'dev');write_json(root/'lesson-candidates.json',candidates)
reviews={c['id']:{'reviewer_id':'synthetic-example-author','approved':True,'generalizable':True,'no_case_answers':True,'scope':'Illustrative self-authored lesson; not a real-model discovery'} for c in candidates}
write_json(root/'lesson-reviews.json',reviews);bank=freeze(candidates,reviews);write_json(root/'lessons.json',bank)
fixtures=[]
for selection in [[],rows[:1],rows[1:]]:
    ids=[r['id'] for r in selection if 'failed_login' in r['raw']]
    fixtures.append({'rows':selection,'expected':{'findings':[{'key':'failed_logins','value':len(ids),'evidence_ids':ids}]}})
write_json(root/'script-fixtures.json',{'fixtures':fixtures})
(root/'count_failed_logins.py').write_text(SCRIPT)
write_json(root/'validation-report.json',validate(case,rows))
# Human-readable graph uses fixed labels from the fixture, not model-provided Mermaid code.
(root/'hypothesis-graph.mmd').write_text('flowchart TD\n  O["Observed failed login"] -->|supports possibility| H1["Credential attack: unresolved"]\n  O -->|supports possibility| H2["User error: unresolved"]\n')
print('Generated five curated variants, graph trace, lesson bank, script fixtures and validation report.')
