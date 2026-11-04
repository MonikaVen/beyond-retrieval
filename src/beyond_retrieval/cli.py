import argparse
from pathlib import Path
from .data import read_json,write_json,normalize,save_events,case_events,digest,transform,load_events
from .runner import run,ChatProvider,ScriptedProvider
from .evaluate import score,paired_bootstrap
from .curation import curate,audit
from .results import (
    append_ledger, load_ledger, record_from_run, write_report, seed_demo_ledger,
)

DEFAULT_LEDGER = Path('results/ledger.jsonl')
DEFAULT_UI = Path('ui/results')


def _refresh_report(ledger=DEFAULT_LEDGER, output=DEFAULT_UI):
    records = load_ledger(ledger)
    return write_report(records, output)


def demo(directory):
    root=Path(directory); root.mkdir(parents=True,exist_ok=True)
    raw=root/'telemetry.log'; raw.write_text('host-a login accepted user=alice\nhost-a login failed user=bob\n')
    rows=normalize(raw,'generic','synthetic','auth')
    save_events(root/'events.jsonl',rows)
    case={'id':'demo-V0','base_case_id':'demo','environment':'synthetic','dataset':'generic','variant':'V0',
          'events':'events.jsonl','evidence_hash':digest(rows),'question':'Does this bundle establish malicious activity?'}
    config={'arm':'A','model':'scripted-fixture','max_calls':4,'max_tokens':100,'max_seconds':10}
    answer={'verdict':'insufficient_evidence','probabilities':{'malicious':0.1,'benign':0.1,'insufficient_evidence':0.8},
            'findings':[{'key':'failed_login','value':'bob','evidence_ids':[rows[1]['id']]}],'unresolved':['Intent is not established.']}
    replies=[{'kind':'tool','tool':'search_events','args':{'contains':'failed'}},{'kind':'final','answer':answer}]
    result=run(case,rows,config,ScriptedProvider(replies))
    rubric={'mandatory':{'failed_login':'bob'},'admissible_verdicts':['insufficient_evidence'],'unique_label':'insufficient_evidence'}
    scored=score(result,rubric)
    for name,value in [('case',case),('config',config),('run',result),('rubric',rubric),('score',scored)]:
        write_json(root/(name+'.json'),value)

    ledger=DEFAULT_LEDGER
    if ledger.exists():
        ledger.unlink()
    # Seed multi-arm synthetic study rows for Tables 6–12, plus the real demo run.
    for row in seed_demo_ledger([record_from_run(result, scored, case=case, rows=rows, run_id='demo-scripted-A')]):
        append_ledger(ledger, row)
    report=_refresh_report(ledger, DEFAULT_UI)
    print('Synthetic demo completed. ESR remains pending human review. Output:',root.resolve())
    print('Results UI:', DEFAULT_UI.resolve(), f'({report["run_count"]} ledger runs)')


def main():
    p=argparse.ArgumentParser(description='Beyond Retrieval experimental scaffold')
    sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('demo'); d.add_argument('--output',default='demo-output')
    n=sub.add_parser('normalize'); n.add_argument('input'); n.add_argument('output'); n.add_argument('--dataset',required=True,choices=['ait','otrf','optc','generic']); n.add_argument('--environment',required=True); n.add_argument('--source',required=True); n.add_argument('--json-array',action='store_true')
    v=sub.add_parser('variant'); v.add_argument('input'); v.add_argument('output'); v.add_argument('--variant',required=True,choices=['V0','V1','V2','V4']); v.add_argument('--spec',required=True); v.add_argument('--extra')
    r=sub.add_parser('run'); r.add_argument('--case',required=True); r.add_argument('--config',required=True); r.add_argument('--output',required=True); r.add_argument('--fixture'); r.add_argument('--lessons'); r.add_argument('--ledger',default=str(DEFAULT_LEDGER)); r.add_argument('--no-report',action='store_true')
    s=sub.add_parser('score'); s.add_argument('--run',required=True); s.add_argument('--rubric',required=True); s.add_argument('--review'); s.add_argument('--output',required=True); s.add_argument('--ledger',default=str(DEFAULT_LEDGER)); s.add_argument('--no-report',action='store_true')
    b=sub.add_parser('compare'); b.add_argument('records'); b.add_argument('--left',default='A'); b.add_argument('--right',default='HS'); b.add_argument('--output',required=True)
    g=sub.add_parser('plan'); g.add_argument('manifest'); g.add_argument('--output',required=True)
    cu=sub.add_parser('curate'); cu.add_argument('manifest'); cu.add_argument('--output',required=True)
    au=sub.add_parser('audit-curation'); au.add_argument('directory')
    rp=sub.add_parser('report'); rp.add_argument('--ledger',default=str(DEFAULT_LEDGER)); rp.add_argument('--output',default=str(DEFAULT_UI))
    a=p.parse_args()
    if a.command=='curate': print(__import__('json').dumps(curate(a.manifest,a.output),indent=2))
    elif a.command=='audit-curation': print(__import__('json').dumps(audit(a.directory),indent=2))
    elif a.command=='demo': demo(a.output)
    elif a.command=='normalize': save_events(a.output,normalize(a.input,a.dataset,a.environment,a.source,a.json_array))
    elif a.command=='variant': save_events(a.output,transform(load_events(a.input),a.variant,read_json(a.spec),load_events(a.extra) if a.extra else []))
    elif a.command=='run':
        if Path(a.output).exists(): raise SystemExit('Output exists; choose a new run path')
        case,config=read_json(a.case),read_json(a.config)
        provider=ChatProvider(config['endpoint'],config['model'],config.get('key_env','EXPERIMENT_API_KEY'))
        rows=case_events(case,a.case)
        result=run(case,rows,config,provider,read_json(a.fixture) if a.fixture else None,read_json(a.lessons) if a.lessons else None)
        write_json(a.output,result)
        append_ledger(a.ledger, record_from_run(result, case=case, rows=rows, run_id=Path(a.output).stem))
        if not a.no_report:
            report=_refresh_report(a.ledger, DEFAULT_UI)
            print('Appended ledger row; UI runs:', report['run_count'])
    elif a.command=='score':
        run_obj=read_json(a.run)
        scored=score(run_obj,read_json(a.rubric),read_json(a.review) if a.review else None)
        write_json(a.output,scored)
        append_ledger(a.ledger, record_from_run(run_obj, scored, run_id=Path(a.run).stem+'-score'))
        if not a.no_report:
            report=_refresh_report(a.ledger, DEFAULT_UI)
            print('Appended scored ledger row; UI runs:', report['run_count'])
    elif a.command=='compare': write_json(a.output,paired_bootstrap(read_json(a.records),a.left,a.right))
    elif a.command=='plan':
        m=read_json(a.manifest); jobs=[]
        for case in m['cases']:
            for arm in m['arms']:
                for model in m['models']:
                    for repeat in range(m.get('repeats',3)):
                        job={'case':case,'arm':arm,'model':model,'repeat':repeat}; job['run_id']=digest(job)[:20]; jobs.append(job)
        write_json(a.output,jobs); print(len(jobs),'planned jobs; no model calls made')
    elif a.command=='report':
        report=_refresh_report(a.ledger, a.output)
        print(f'Wrote Tables 6–12 to {Path(a.output).resolve()} ({report["run_count"]} runs)')

if __name__=='__main__': main()
