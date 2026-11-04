"""Budgeted agent runner. Rubrics are deliberately absent from this interface."""
import json
import os
import time
import urllib.request
from .data import digest
from .tools import EvidenceTools, DockerScripts
from .graph import HypothesisGraph, GRAPH_PROMPT
from .lessons import retrieve, LESSON_PROMPT

ARMS = {'A', 'H', 'AS', 'HS', 'HS-no-validation', 'R'}
VERDICTS = {'malicious', 'benign', 'insufficient_evidence'}

class ChatProvider:
    """Explicit OpenAI-compatible chat endpoint; no request is made until run()."""
    def __init__(self, endpoint, model, key_env='EXPERIMENT_API_KEY'):
        self.endpoint, self.model, self.key_env = endpoint, model, key_env
    def __call__(self, messages, max_tokens, timeout):
        payload = {'model': self.model, 'messages': messages, 'temperature': 0,
                   'max_tokens': max_tokens, 'response_format': {'type': 'json_object'}}
        headers = {'Content-Type': 'application/json'}
        if os.getenv(self.key_env): headers['Authorization'] = 'Bearer ' + os.environ[self.key_env]
        request = urllib.request.Request(self.endpoint, json.dumps(payload).encode(), headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
        tokens = result.get('usage', {}).get('completion_tokens')
        if type(tokens) is not int or tokens < 0:
            raise ValueError('Provider must report completion_tokens to enforce budgets')
        return json.loads(result['choices'][0]['message']['content']), tokens

class ScriptedProvider:
    """Offline fixture only, not an experimental model."""
    def __init__(self, replies): self.replies = iter(replies)
    def __call__(self, messages, max_tokens, timeout): return next(self.replies), 1

SYSTEM = '''You investigate the public question using only available evidence.
Return one JSON object per response. A tool action is
{"kind":"tool","tool":"search_events","args":{"contains":"text","limit":20}}.
Tools: list_sources, describe_schema, search_events (source, contains, offset,
limit), get_records (ids, offset, limit), aggregate_events (source, contains,
group_by). Use pagination when truncated. A script action is
{"kind":"script","code":"..."}; Python reads /evidence/events.jsonl and prints
JSON {"findings": [...]}. Scripts require an enabled arm.
A final response is {"kind":"final","answer":{"verdict":"malicious|benign|insufficient_evidence",
"probabilities":{"malicious":0.0,"benign":0.0,"insufficient_evidence":1.0},
"findings":[{"key":"claim_name","value":"claim_value","evidence_ids":["id"]}],
"unresolved":[]}}. Do not claim evidence you have not inspected.
For hypothesis arms each action also needs contract {"question":"...",
"hypotheses":["alternative1","alternative2"],"predictions":["outcome1","outcome2"]}
and may include graph_update {"nodes":[...],"edges":[...]}.
Graph assertions are working hypotheses, never verified facts.
'''

def valid_contract(action):
    c = action.get('contract', {})
    return (isinstance(c, dict) and isinstance(c.get('question'), str) and bool(c['question'])
            and all(isinstance(c.get(k), list) and len(c[k]) >= 2
                    and all(isinstance(v, str) and v for v in c[k])
                    and len(set(c[k])) >= 2 for k in ('hypotheses','predictions')))

def check_answer(answer, visible_ids):
    if answer.get('verdict') not in VERDICTS: raise ValueError('Invalid verdict')
    p = answer.get('probabilities', {})
    if set(p) != VERDICTS or any(type(v) not in (int,float) or not 0 <= v <= 1 for v in p.values()) or abs(sum(p.values())-1)>1e-6:
        raise ValueError('Probabilities must form a three-class distribution')
    if not isinstance(answer.get('findings'), list): raise ValueError('findings must be a list')
    for f in answer['findings']:
        if not {'key','value','evidence_ids'} <= f.keys(): raise ValueError('Incomplete finding')
        if not set(f['evidence_ids']) <= visible_ids: raise ValueError('Unavailable evidence citation')
    return answer

def run(case, rows, config, provider, fixture=None, lesson_bank=None):
    if case.get('curation', {}).get('status') == 'draft':
        raise ValueError('Draft curated case requires curator review before model execution')
    config = dict(config)
    arm = config['arm']
    if arm not in ARMS: raise ValueError('Unsupported arm')
    # R = fixed retrieval + synthesis: no adaptive queries; evidence is a frozen bundle.
    if arm == 'R':
        config['replay'] = True
    if digest(rows) != case['evidence_hash']: raise ValueError('Evidence hash mismatch')
    stages = case.get('stages', [[r['id'] for r in rows]])
    all_ids = {r['id'] for r in rows}
    if len(stages) not in (1,2) or any(not set(s) <= all_ids for s in stages): raise ValueError('Invalid stages')
    if len(stages)==2 and not set(stages[0]) <= set(stages[1]): raise ValueError('Release must be cumulative')
    if config.get('replay') and len(stages)!=1: raise ValueError('Replay requires one fixed bundle')
    calls_max = config.get('max_calls',40)//len(stages)
    tokens_max = config.get('max_tokens',30000)//len(stages)
    seconds = config.get('max_seconds',1200)/len(stages)
    if calls_max < 1 or tokens_max < 1 or seconds <= 0: raise ValueError('Invalid budgets')
    graph = HypothesisGraph() if arm in {'H','HS','HS-no-validation'} else None
    selected_lessons = retrieve(lesson_bank,case['question'],case.get('base_case_id',case['id'])) if lesson_bank and arm in {'HS','HS-no-validation'} else []
    observed = set()
    messages = [{'role':'system','content':SYSTEM + (GRAPH_PROMPT if graph else '') + LESSON_PROMPT + '\nArm: '+arm},
                {'role':'user','content':json.dumps({'question':case['question'], 'public_context':case.get('public_context',{})})}]
    if selected_lessons: messages.append({'role':'user','content':json.dumps({'reviewed_procedures':selected_lessons})})
    log, answers = [], []
    total_tokens = total_calls = 0
    for stage, ids in enumerate(stages):
        visible = [r for r in rows if r['id'] in set(ids)]
        service = EvidenceTools(visible)
        if config.get('replay'): observed.update(ids)
        messages.append({'role':'user','content':json.dumps({'stage':stage,'notice':'Evidence now available',
                         **({'fixed_bundle':visible} if config.get('replay') else {})})})
        deadline = time.monotonic()+seconds
        tokens = calls = 0
        answer = None
        status = 'budget_exhausted'
        # Model steps are separately bounded to prevent unlimited malformed actions.
        for step in range(config.get('max_steps',80)//len(stages)):
            if tokens >= tokens_max or time.monotonic() >= deadline: break
            try:
                action, used = provider(messages, tokens_max-tokens, max(.01,deadline-time.monotonic()))
                tokens += used
                log.append({'stage':stage,'action':action,'completion_tokens':used})
                if tokens > tokens_max or time.monotonic() >= deadline: break
                messages.append({'role':'assistant','content':json.dumps(action)})
                if graph:
                    graph.update(action.get('graph_update',{}),observed,stage)
                    log[-1]['graph_hash'] = digest(graph.snapshot())
                if action.get('kind') == 'final':
                    answer = check_answer(action['answer'],observed); status='completed'; break
                if calls >= calls_max: break
                calls += 1
                if config.get('replay'): raise ValueError('Replay forbids new tools')
                if arm in {'H','HS','HS-no-validation'} and not valid_contract(action):
                    raise ValueError('Action requires a distinguishing hypothesis contract')
                if graph:
                    hypothesis_ids=action['contract'].get('hypothesis_ids',[])
                    if len(hypothesis_ids)<2 or len(set(hypothesis_ids))!=len(hypothesis_ids) or any(graph.nodes.get(h,{}).get('type')!='hypothesis' for h in hypothesis_ids):
                        raise ValueError('Contract must reference at least two graph hypothesis_ids')
                    if len(action['contract']['predictions'])!=len(hypothesis_ids):
                        raise ValueError('One prediction per referenced hypothesis required')
                    action_id=f'action_s{stage}_step{step}'
                    graph.update({'nodes':[{'id':action_id,'type':'action','text':json.dumps({k:v for k,v in action.items() if k!='graph_update'}),'status':'open','evidence_ids':[]}],
                                  'edges':[{'source':action_id,'target':h,'relation':'tests'} for h in hypothesis_ids]},observed,stage)
                if action.get('kind') == 'tool':
                    result = service.call(action['tool'], action.get('args',{}))
                elif action.get('kind') == 'script':
                    if arm not in {'AS','HS','HS-no-validation'}: raise ValueError('Scripts disabled')
                    executor = DockerScripts(config['docker_image'], timeout=min(120,max(1,int(deadline-time.monotonic()))))
                    if arm == 'HS':
                        if not fixture: raise ValueError('HS requires a development fixture suite')
                        suite = fixture.get('fixtures',[fixture])
                        if not suite: raise ValueError('Empty fixture suite')
                        for item in suite:
                            if calls >= calls_max: raise ValueError('Insufficient validation budget')
                            calls += 1
                            executor.timeout = min(120,max(.01,deadline-time.monotonic()))
                            if executor.execute(action['code'],item['rows']) != item['expected']:
                                raise ValueError('Development fixture validation failed')
                            if time.monotonic() >= deadline: raise TimeoutError('Stage deadline reached')
                    executor.timeout = min(120,max(.01,deadline-time.monotonic()))
                    result = executor.execute(action['code'],visible)
                    # Only explicitly returned evidence IDs become observed.
                    for finding in result['findings']:
                        cited=set(finding.get('evidence_ids',[]))
                        if not cited <= set(ids): raise ValueError('Script cited unavailable records')
                        observed.update(cited)
                else: raise ValueError('Unknown action kind')
                if action.get('kind')=='tool':
                    observed.update(r['id'] for r in result.get('records',[]) if 'id' in r)
                log[-1]['result'] = result
                messages.append({'role':'user','content':json.dumps({'tool_result':result,**({'graph_state':graph.snapshot()} if graph else {})})})
            except (ValueError,KeyError,TypeError,TimeoutError,StopIteration,OSError) as exc:
                log.append({'stage':stage,'error':str(exc)})
                messages.append({'role':'user','content':json.dumps({'error':str(exc),**({'graph_state':graph.snapshot()} if graph else {})})})
                if isinstance(exc,(StopIteration,OSError)): status='provider_error'; break
        total_tokens += tokens; total_calls += calls
        answers.append({'stage':stage,'status':status,'answer':answer})
    return {'case_id':case['id'],'base_case_id':case.get('base_case_id',case['id']),
            'environment':case['environment'],'variant':case.get('variant','V0'),
            'evidence_hash':digest(rows),'config':config,'config_hash':digest(config),
            'graph':graph.snapshot() if graph else None,'graph_history':graph.history if graph else [],
            'lesson_bank_hash':lesson_bank.get('hash') if lesson_bank else None,'retrieved_lessons':selected_lessons,
            'completion_tokens':total_tokens,'tool_calls':total_calls,'stages':answers,'trace':log}
