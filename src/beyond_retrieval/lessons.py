"""Development-only lesson proposals, explicit review, frozen retrieval bank."""
import re
from .data import digest

LESSON_PROMPT='''You may include lesson_candidates in your final action, each with
trigger, procedure, limitation (strings). Generalize investigative procedures;
do not copy entity identifiers, answers or raw logs. Lessons are proposals only.
'''

def propose(run, split):
    if split not in {'train','dev'}: raise ValueError('Learning from test/external runs is forbidden')
    candidates=[]
    for record in run['trace']:
        for c in record.get('action',{}).get('lesson_candidates',[]):
            if not all(isinstance(c.get(k),str) and c[k].strip() for k in ('trigger','procedure','limitation')): raise ValueError('Incomplete lesson')
            body={k:c[k] for k in ('trigger','procedure','limitation')}
            candidates.append({**body,'id':digest(body)[:24],'source_run_hash':digest(run),
                               'source_case':run['case_id'],'source_base_case':run.get('base_case_id',run['case_id']),'split':split,'status':'proposed'})
    return candidates

def freeze(candidates, reviews):
    lessons=[]; seen=set()
    for c in candidates:
        if c['split'] not in {'train','dev'}:raise ValueError('Test lesson contamination')
        r=reviews.get(c['id'],{})
        if not (r.get('reviewer_id') and r.get('approved') is True and r.get('no_case_answers') is True and r.get('generalizable') is True):raise ValueError('Every lesson needs independent review')
        if c['id'] in seen:continue
        seen.add(c['id']);lessons.append({**c,'status':'approved','review':r})
    bank={'schema_version':1,'lessons':sorted(lessons,key=lambda c:c['id'])}
    return {**bank,'hash':digest(bank)}

def retrieve(bank, question, excluded_case, k=3):
    if digest({key:v for key,v in bank.items() if key!='hash'})!=bank['hash']:raise ValueError('Lesson bank hash mismatch')
    if type(k) is not int or not 0<=k<=10:raise ValueError('Invalid lesson limit')
    tokens=lambda s:set(re.findall(r'[a-z0-9]+',s.lower()))
    query=tokens(question); scored=[]
    for lesson in bank['lessons']:
        if lesson['split'] not in {'train','dev'} or lesson['status']!='approved':raise ValueError('Invalid frozen lesson')
        if lesson.get('source_base_case',lesson['source_case'])==excluded_case:continue
        score=len(query & tokens(lesson['trigger']))
        if score:scored.append((score,lesson['id'],{k:lesson[k] for k in ('id','trigger','procedure','limitation')}))
    return [row[2] for row in sorted(scored,key=lambda x:(-x[0],x[1]))[:k]]
