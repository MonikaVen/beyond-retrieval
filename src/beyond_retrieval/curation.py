"""Reproducible, explicit case curation. No automatic inference of ground truth."""
import hashlib
import re
import tempfile
import shutil
from pathlib import Path
from .data import normalize, digest, read_json, write_json, save_events, load_events, transform
from .runner import VERDICTS

AIT_SPLITS = {'fox':'train','harrison':'train','russellmitchell':'dev','santos':'dev',
              'shaw':'test','wardbeck':'test','wheeler':'test','wilson':'test'}
CHECKS = ['telemetry_only','label_alignment','public_prompt_no_answers','scenario_independence','rubric_support']
VARIANT_CHECKS = {'V1':['renaming_preserves_semantics'], 'V2':['distractors_unrelated'],
                  'V4':['all_support_routes_removed','ambiguity_reviewed'],
                  'V5':['release_schedule_shared','stage_rubrics_reviewed']}

def require(condition, message):
    if not condition: raise ValueError(message)

def safe_id(value):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',value) is not None, 'Unsafe identifier')
    return value

def references(refs, pools):
    """Explicit original line/item references, never positions after filtering."""
    require(isinstance(refs,list), 'references must be a list')
    selected=[]
    for ref in refs:
        source=ref['source']; require(source in pools,'Unknown source reference')
        indices=ref['indices']; require(isinstance(indices,list) and indices and all(type(i) is int and i>0 for i in indices),'Invalid original indices')
        require(len(indices)==len(set(indices)),'Duplicate original indices')
        lookup={r['origin']['index']:r for r in pools[source]}
        require(set(indices)<=lookup.keys(),'Original index missing (blank lines are not records)')
        selected.extend(lookup[i] for i in indices)
    require(len({r['id'] for r in selected})==len(selected),'Duplicate evidence references')
    return sorted(selected,key=lambda r:r['id'])

def rubric(value, pools, ids):
    require(isinstance(value.get('mandatory'),dict),'mandatory must be an object')
    admissible=value.get('admissible_verdicts')
    require(isinstance(admissible,list) and admissible and set(admissible)<=VERDICTS,'Invalid admissible verdicts')
    unique=value.get('unique_label')
    require(unique is None or (len(set(admissible))==1 and unique==admissible[0]),'unique_label requires a single admissible verdict')
    support={}
    for key in value['mandatory']:
        require(key in value.get('support',{}),'Each mandatory finding needs explicit support')
        selected=references(value['support'][key],pools)
        require(selected and {r['id'] for r in selected}<=ids,'Rubric cites unavailable evidence')
        support[key]=[r['id'] for r in selected]
    return {**value,'support':support}

def curate(manifest_path, output):
    """Build public/ and private/ atomically; no overwrite of an existing dataset."""
    manifest_path=Path(manifest_path).resolve(); spec=read_json(manifest_path)
    output=Path(output).resolve(); require(not output.exists(),'Output already exists')
    pools={}; inventory=[]; source_specs={}
    for source in spec['sources']:
        sid=safe_id(source['id']); require(sid not in pools,'Duplicate source ID')
        require(all(isinstance(source.get(k),str) and source[k] for k in ('dataset','environment','version','license','url','sha256','path')),'Source metadata incomplete')
        path=(manifest_path.parent/source['path']).resolve()
        require(path.is_file(),'Source file missing')
        checksum=hashlib.sha256(path.read_bytes()).hexdigest()
        require(checksum==source['sha256'],'Source SHA256 mismatch: '+sid)
        pools[sid]=normalize(path,source['dataset'],source['environment'],sid,source.get('json_array',False))
        source_specs[sid]=source
        inventory.append({k:v for k,v in source.items() if k!='path'})
    cases=[]; ids=set(); base_splits={}; group_splits={}; record_splits={}; environment_splits={}
    for c in spec['cases']:
        cid=safe_id(c['id']); require(cid not in ids,'Duplicate case ID'); ids.add(cid)
        base=safe_id(c.get('base_case_id',cid)); split=c['split']; variant=c.get('variant','V0')
        require(split in {'train','dev','test','external'},'Unknown split')
        require(variant in {'V0','V1','V2','V4','V5'},'Unsupported variant')
        group=c['scenario_group']; require(isinstance(group,str) and group,'scenario_group required')
        for mapping,key in ((base_splits,base),(group_splits,group)):
            require(mapping.setdefault(key,split)==split,'Base case or scenario group crosses splits')
        rows=references(c['evidence'],pools); require(rows,'Empty case evidence')
        extra=references(c.get('distractors',[]),pools)
        original=rows+extra
        envs={r['environment'] for r in original}; require(len(envs)==1,'Case must have one environment')
        env=next(iter(envs))
        for r in original:
            dataset=r['dataset']
            if dataset=='ait': require(AIT_SPLITS.get(env)==split,'AIT environment violates frozen split')
            require(environment_splits.setdefault((dataset,env),split)==split,'Environment crosses splits')
            # Content origin detects duplicate imports under different source names.
            origin=(r['origin']['sha256'],r['origin']['index'])
            require(record_splits.setdefault(origin,split)==split,'Source record crosses splits')
        require(not extra or variant=='V2','Distractors only valid for V2')
        transform_spec=c.get('transform',{})
        if variant=='V4': transform_spec={'hide_ids':[r['id'] for r in references(c['hide'],pools)]}
        if variant in {'V0','V1','V2','V4'}: rows=transform(rows,variant,transform_spec,extra)
        require(rows,'Variant has no evidence')
        available={r['id'] for r in rows}
        stages=None
        if variant=='V5':
            initial=references(c['initial_evidence'],pools)
            require(initial and {r['id'] for r in initial}<available,'V5 needs a nonempty strict initial subset')
            stages=[[r['id'] for r in initial],sorted(available)]
        rub=rubric(c['rubric'],pools,available)
        provisional=rubric(c['provisional_rubric'],pools,set(stages[0])) if stages else None
        review=c.get('review',{}); checks=CHECKS+VARIANT_CHECKS.get(variant,[])
        approved=bool(review.get('reviewer_id')) and all(review.get(k) is True for k in checks)
        public={'id':cid,'base_case_id':base,'environment':env,'variant':variant,
                'question':c['question'],'public_context':c.get('public_context',{}),
                'events':'events.jsonl','evidence_hash':digest(rows),
                'curation':{'status':'approved' if approved else 'draft'}}
        require(isinstance(c['question'],str) and bool(c['question']),'Question required')
        if stages: public['stages']=stages
        private={'case_id':cid,'split':split,'scenario_group':group,'rubric':rub,
                 'provisional_rubric':provisional,'review':review,'required_checks':checks,
                 'evidence_hash':digest(rows),'case_hash':digest(public)}
        cases.append((cid,public,private,rows))
    require(cases,'No cases supplied')
    output.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='curation-',dir=output.parent))
    try:
        (temp/'private').mkdir(mode=0o700)
        manifest={'schema_version':1,'input_manifest_hash':digest(spec),'sources':inventory,'cases':[]}
        for cid,public,private,rows in cases:
            save_events(temp/'public'/cid/'events.jsonl',rows)
            write_json(temp/'public'/cid/'case.json',public)
            write_json(temp/'private'/(cid+'.json'),private)
            manifest['cases'].append({'id':cid,'split':private['split'],'status':public['curation']['status'],
                                     'case_hash':digest(public),'private_hash':digest(private),'records':len(rows)})
        write_json(temp/'private'/'manifest.json',manifest)
        temp.rename(output)
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True); raise
    return audit(output)

def audit(root):
    root=Path(root); manifest=read_json(root/'private'/'manifest.json'); results=[]
    for entry in manifest['cases']:
        cid=safe_id(entry['id']); c=read_json(root/'public'/cid/'case.json')
        p=read_json(root/'private'/(cid+'.json')); rows=load_events(root/'public'/cid/'events.jsonl')
        require(digest(c)==entry['case_hash']==p['case_hash'],'Case changed since curation')
        require(digest(p)==entry['private_hash'],'Private rubric/review changed since curation')
        require(digest(rows)==c['evidence_hash']==p['evidence_hash'],'Evidence changed since curation')
        results.append({'id':cid,'split':entry['split'],'status':c['curation']['status'],'records':len(rows)})
    return {'cases':results,'approved':sum(c['status']=='approved' for c in results),
            'draft':sum(c['status']=='draft' for c in results),'integrity':'passed'}
