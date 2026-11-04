"""Scoring is separate from agent execution. Semantic adjudication is mandatory."""
import random
import statistics

def score(run, rubric, review=None):
    final = run['stages'][-1]
    a = final['answer']
    if a is None: return {'esr':0,'status':final['status'],'brier':None}
    findings = {f['key']: f for f in a['findings']}
    matched = all(k in findings and findings[k]['value']==v for k,v in rubric['mandatory'].items())
    verdict_ok = a['verdict'] in rubric['admissible_verdicts']
    structural = matched and verdict_ok
    # Only a documented independent human review can certify entailment.
    adjudicated = (review is not None and review.get('adjudicated') is True
                   and bool(review.get('reviewer_id')))
    esr = (int(structural and review.get('all_claims_supported') is True
               and review.get('mandatory_findings_supported') is True
               and review.get('no_material_unsupported_claims') is True) if adjudicated else None)
    label = rubric.get('unique_label')
    brier = sum((p-int(k==label))**2 for k,p in a['probabilities'].items()) if label else None
    return {'esr':esr,'status':'adjudicated' if adjudicated else 'pending_human_review',
            'mandatory_value_match':matched,'admissible_verdict':verdict_ok,'brier':brier}

def paired_bootstrap(records, left, right, draws=2000, seed=17):
    """Pair exact case/variant/model/repeat keys, average within environment,
    then resample environments. Equal-environment estimand, not case weighted.
    Input rows: arm, environment, base_case_id, variant, model, repeat, esr.
    """
    cells = {}
    for r in records:
        if r['arm'] not in {left,right}: continue
        if r['esr'] not in (0,1): raise ValueError('All scores must be adjudicated')
        key = tuple(r[k] for k in ('environment','base_case_id','variant','model','repeat'))
        if r['arm'] in cells.setdefault(key,{}): raise ValueError('Duplicate paired result')
        cells[key][r['arm']] = r['esr']
    if not cells or any(set(v)!={left,right} for v in cells.values()): raise ValueError('Missing pairs')
    groups = {}
    for key, values in cells.items(): groups.setdefault(key[0],[]).append(values[right]-values[left])
    means = [statistics.mean(v) for v in groups.values()]
    rng = random.Random(seed)
    samples = sorted(statistics.mean(rng.choices(means,k=len(means))) for _ in range(draws))
    return {'difference_right_minus_left':statistics.mean(means),
            'percentile_95': [samples[int(.025*draws)],samples[min(draws-1,int(.975*draws))]],
            'environments':len(means),'paired_runs':len(cells),
            'warning':'Few environment clusters make population uncertainty unreliable; no significance claim.'}
