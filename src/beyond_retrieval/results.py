"""Aggregate experiment ledger rows into paper Tables 6–12 for the results UI.

Unavailable metrics stay null and render as em dashes in the UI. ESR cells use
adjudicated values when present; otherwise a structural proxy is shown as pending.
Cost uses completion_tokens until currency accounting exists.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

DASH = '—'

TABLE6_CONDITIONS = [
    ('R', 'R Fixed retrieval'),
    ('A', 'A Standard agent'),
    ('P', 'P Fixed playbook'),
    ('H', 'H Hypothesis agent'),
    ('AS', 'AS Agent + scripts'),
    ('HS', 'HS Full method'),
]

TABLE7_CONDITIONS = [
    ('A', 'A Standard agent'),
    ('P', 'P Fixed playbook'),
    ('H', 'H Hypothesis agent'),
    ('AS', 'AS Agent + scripts'),
    ('HS', 'HS Full method'),
]

TABLE9_VARIANTS = [
    ('full', 'Full method'),
    ('flat_memory', 'Flat memory with same content'),
    ('no_predictions', 'No pre-action predictions'),
    ('no_contradiction', 'No contradiction check'),
    ('no_script_validation', 'No script validation'),
    ('HS-no-validation', 'No script validation'),
    ('no_lessons', 'No experience lessons'),
    ('fixed_lessons', 'Fixed procedural lessons'),
    ('matched_reflection', 'Matched-budget reflection baseline'),
]

TABLE10_CONDITIONS = [
    ('AS', 'AS Standard scripts'),
    ('HS-no-validation', 'HS without validation'),
    ('HS', 'HS Full method'),
]

TABLE11_REPS = [
    ('chronological', 'Chronological evidence ledger'),
    ('flat_relations', 'Flat list of identical relations'),
    ('entity_temporal', 'Entity and temporal graph'),
    ('support_contradiction', 'Support and contradiction graph'),
    ('full_graph', 'Full graph with provenance and gaps'),
]

TABLE12_TECHNIQUES = [
    ('hypothesis_tree', 'Hypothesis tree',
     'At most three branches; evidence-based pruning and backtracking'),
    ('independent_critique', 'Independent critique',
     'Fresh-context reviewer challenges evidence support'),
    ('retrieval_guided', 'Retrieval-guided planning',
     'Retrieve frozen training lessons by current evidence gap'),
    ('adaptive_replanning', 'Adaptive replanning',
     'Revise the plan after contradiction, failed action, or no progress'),
    ('independent_candidates', 'Independent candidates',
     'Three proposals on the same evidence; evidence-based selection'),
    ('matched_self_review', 'Matched self-review',
     'Single agent revisits its answer using equivalent budget'),
]

TABLE8_SOURCES = [
    ('independent', 'Independent fixed collector'),
    ('a_collected', 'A-collected bundle'),
    ('hs_collected', 'HS-collected bundle'),
    ('oracle', 'Oracle decisive bundle'),
]


def _mean(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return statistics.mean(values) if values else None


def _fmt(value, pending=False, digits=3):
    if value is None:
        return DASH
    if isinstance(value, bool):
        text = '1' if value else '0'
    elif isinstance(value, float):
        text = f'{value:.{digits}f}'.rstrip('0').rstrip('.')
    else:
        text = str(value)
    return f'{text} (pending)' if pending else text


def _script_stats(run):
    trace = run.get('trace') or []
    script_actions = [e for e in trace if isinstance(e.get('action'), dict) and e['action'].get('kind') == 'script']
    used = 1.0 if script_actions else 0.0
    successes = 0
    failures = 0
    verified = 0
    false_findings = 0
    validation_pass = None
    for entry in trace:
        if entry.get('error') and 'fixture validation failed' in str(entry.get('error', '')).lower():
            validation_pass = 0.0
        action = entry.get('action') or {}
        if action.get('kind') != 'script':
            continue
        result = entry.get('result')
        if result is None and entry.get('error'):
            failures += 1
            continue
        if isinstance(result, dict):
            successes += 1
            findings = result.get('findings') or []
            verified += len(findings)
            # Untrusted script claims: without adjudication count as unverified, not false.
        if run.get('config', {}).get('arm') == 'HS' and validation_pass is None and result is not None:
            validation_pass = 1.0
    total = successes + failures
    return {
        'used_script': used,
        'execution_success': (successes / total) if total else None,
        'validation_pass': validation_pass,
        'verified_findings': verified if script_actions else None,
        'false_findings': false_findings if script_actions else None,
    }


def _infer_dataset(run, case=None, rows=None, meta=None):
    meta = meta or {}
    if meta.get('dataset'):
        return meta['dataset']
    if case and case.get('dataset'):
        return case['dataset']
    if rows:
        datasets = sorted({r.get('dataset') for r in rows if r.get('dataset')})
        if len(datasets) == 1:
            return datasets[0]
        if datasets:
            return '+'.join(datasets)
    cfg = run.get('config') or {}
    return cfg.get('dataset') or run.get('dataset')


def record_from_run(run, score=None, case=None, rows=None, **meta):
    """Normalize a run (+ optional score) into one ledger row."""
    config = run.get('config') or {}
    arm = config.get('arm') or meta.get('arm')
    scripts = _script_stats(run)
    structural = None
    esr = None
    esr_status = 'missing'
    if score:
        if score.get('status') == 'adjudicated' and score.get('esr') in (0, 1):
            esr = float(score['esr'])
            esr_status = 'adjudicated'
        if 'mandatory_value_match' in score and 'admissible_verdict' in score:
            structural = 1.0 if (
                score.get('mandatory_value_match') and score.get('admissible_verdict')
            ) else 0.0
        if esr is None and structural is not None:
            esr_status = 'pending'
        elif esr is None and score.get('status') == 'pending_human_review':
            esr_status = 'pending'
    environment = (
        run.get('environment')
        or (case or {}).get('environment')
        or meta.get('environment')
    )
    row = {
        'run_id': meta.get('run_id') or run.get('case_id'),
        'case_id': run.get('case_id') or (case or {}).get('id'),
        'base_case_id': run.get('base_case_id') or (case or {}).get('base_case_id'),
        'environment': environment,
        'dataset': _infer_dataset(run, case, rows, meta),
        'variant': run.get('variant') or (case or {}).get('variant', 'V0'),
        'arm': arm,
        'model': config.get('model') or meta.get('model'),
        'repeat': config.get('repeat', meta.get('repeat', 0)),
        'ablation': config.get('ablation') or meta.get('ablation'),
        'representation': config.get('representation') or meta.get('representation'),
        'technique': config.get('technique') or meta.get('technique'),
        'evidence_source': config.get('evidence_source') or meta.get('evidence_source'),
        'evidence_hash': run.get('evidence_hash') or (case or {}).get('evidence_hash'),
        'replay': bool(config.get('replay')) or arm == 'R',
        'tool_calls': run.get('tool_calls'),
        'completion_tokens': run.get('completion_tokens'),
        'status': (run.get('stages') or [{}])[-1].get('status'),
        'has_graph': run.get('graph') is not None,
        'esr': esr,
        'esr_status': esr_status,
        'structural_success': structural,
        'cps': meta.get('cps', (score or {}).get('cps')),
        'unsupported_claims': meta.get('unsupported_claims', (score or {}).get('unsupported_claims')),
        'revision': meta.get('revision', (score or {}).get('revision')),
        'relation_precision': meta.get('relation_precision'),
        'pair_metric': meta.get('pair_metric'),  # rename|distractor|counterfact|missing
        'pair_success': meta.get('pair_success'),
        'standard_esr': meta.get('standard_esr'),
        'structured_esr': meta.get('structured_esr'),
        **scripts,
    }
    return row


def study_scope(records):
    """Summarize which models and datasets appear in the ledger."""
    def uniq(key):
        return sorted({r[key] for r in records if r.get(key) not in (None, '')})

    return {
        'models': uniq('model'),
        'datasets': uniq('dataset'),
        'environments': uniq('environment'),
        'cases': uniq('case_id'),
        'base_cases': uniq('base_case_id'),
        'variants': uniq('variant'),
        'arms': uniq('arm'),
    }


def scope_for_records(records):
    scope = study_scope(records)
    models = ', '.join(scope['models']) or DASH
    data_bits = []
    if scope['datasets']:
        data_bits.append('datasets: ' + ', '.join(scope['datasets']))
    if scope['environments']:
        data_bits.append('environments: ' + ', '.join(scope['environments']))
    if scope['cases']:
        data_bits.append('cases: ' + ', '.join(scope['cases'][:12])
                         + ('…' if len(scope['cases']) > 12 else ''))
    return {
        'models_label': models,
        'data_label': '; '.join(data_bits) if data_bits else DASH,
        'scope': scope,
    }


def append_ledger(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    return path


def load_ledger(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _group(records, key_fn):
    groups = {}
    for r in records:
        key = key_fn(r)
        if key is None:
            continue
        groups.setdefault(key, []).append(r)
    return groups


def _cell(value, n=0, pending=False, status=None, digits=3):
    return {
        'value': value,
        'n': n,
        'pending': pending,
        'status': status,
        'display': _fmt(value, pending=pending, digits=digits),
    }


def _arm_rows(records, arm):
    return [r for r in records if r.get('arm') == arm]


def aggregate_table6(records):
    headers = ['Condition', 'ESR ↑', 'CPS ↑', 'Unsupported claims ↓', 'Calls ↓', 'Cost / run ↓']
    rows_display = []
    cells = []
    # Paper Table 6 is the core V0 cohort.
    v0 = [r for r in records if r.get('variant', 'V0') == 'V0']
    for arm, label in TABLE6_CONDITIONS:
        subset = _arm_rows(v0, arm)
        esr_vals = []
        esr_pending = False
        for r in subset:
            if r.get('esr') is not None and r.get('esr_status') == 'adjudicated':
                esr_vals.append(r['esr'])
            elif r.get('structural_success') is not None:
                esr_vals.append(r['structural_success'])
                esr_pending = True
            elif r.get('esr') is not None:
                esr_vals.append(r['esr'])
                esr_pending = True
        esr = _mean(esr_vals)
        cps = _mean([r['cps'] for r in subset if r.get('cps') is not None])
        unsupported = _mean([r['unsupported_claims'] for r in subset if r.get('unsupported_claims') is not None])
        calls = _mean([r['tool_calls'] for r in subset if r.get('tool_calls') is not None])
        cost = _mean([r['completion_tokens'] for r in subset if r.get('completion_tokens') is not None])
        n = len(subset)
        row_cells = [
            _cell(esr, n, pending=esr_pending and esr is not None),
            _cell(cps, n),
            _cell(unsupported, n),
            _cell(calls, n, digits=2),
            _cell(cost, n, digits=1),
        ]
        cells.append({'arm': arm, 'label': label, 'cells': row_cells, 'n': n})
        rows_display.append([label] + [c['display'] for c in row_cells])
    out = {
        'id': '6',
        'title': 'Reporting template (core V0 cohort)',
        'caption': 'Populate A, H, AS, and HS for the full V0 cohort; show R and P only on their shared secondary subset. Cost is completion_tokens. R requires a frozen evidence bundle (arm=R forces replay).',
        'headers': headers,
        'rows': rows_display,
        'cells': cells,
    }
    out.update(scope_for_records(v0))
    return out


def aggregate_table7(records):
    headers = ['Condition', 'Rename pair ↑', 'Distractor pair ↑', 'Counterfact. pair ↑', 'Missing ESR ↑', 'Revision ESR ↑']
    rows_display, cells = [], []
    metric_map = {
        'rename': 'V1',
        'distractor': 'V2',
        'counterfact': 'V3',
        'missing': 'V4',
    }
    for arm, label in TABLE7_CONDITIONS:
        subset = _arm_rows(records, arm)
        values = {}
        for metric, variant in metric_map.items():
            tagged = [r['pair_success'] for r in subset
                      if r.get('pair_metric') == metric and r.get('pair_success') is not None]
            if not tagged:
                tagged = [r['structural_success'] for r in subset
                          if r.get('variant') == variant and r.get('structural_success') is not None]
            values[metric] = _mean(tagged)
        revision = _mean([r['revision'] for r in subset
                          if r.get('variant') == 'V5' and r.get('revision') is not None]
                         or [r['structural_success'] for r in subset
                             if r.get('variant') == 'V5' and r.get('structural_success') is not None])
        row_cells = [
            _cell(values['rename'], pending=values['rename'] is not None),
            _cell(values['distractor'], pending=values['distractor'] is not None),
            _cell(values['counterfact'], pending=values['counterfact'] is not None),
            _cell(values['missing'], pending=values['missing'] is not None),
            _cell(revision, pending=revision is not None),
        ]
        # Only mark pending when using structural proxy without adjudication
        for i, metric in enumerate(['rename', 'distractor', 'counterfact', 'missing']):
            adjudicated = any(
                r.get('pair_metric') == metric and r.get('esr_status') == 'adjudicated'
                for r in subset
            )
            if row_cells[i]['value'] is not None and not adjudicated:
                row_cells[i]['pending'] = True
                row_cells[i]['display'] = _fmt(row_cells[i]['value'], pending=True)
            elif adjudicated:
                row_cells[i]['pending'] = False
                row_cells[i]['display'] = _fmt(row_cells[i]['value'])
        cells.append({'arm': arm, 'label': label, 'cells': row_cells})
        rows_display.append([label] + [c['display'] for c in row_cells])
    out = {
        'id': '7',
        'title': 'Intervention results template',
        'caption': 'Paired variant outcomes by condition. Unmeasured cells stay blank.',
        'headers': headers,
        'rows': rows_display,
        'cells': cells,
    }
    out.update(scope_for_records(records))
    return out


def aggregate_table8(records):
    headers = ['Evidence source', 'Standard ESR', 'Structured ESR', 'Paired Δ [95% CI]']
    rows_display, cells = [], []
    for key, label in TABLE8_SOURCES:
        subset = [r for r in records if r.get('evidence_source') == key or (
            key == 'independent' and r.get('replay') and r.get('evidence_source') in (None, 'independent')
        )]
        # Fallback: replay runs without evidence_source tag count as independent
        if key == 'independent' and not any(r.get('evidence_source') == key for r in records):
            subset = [r for r in records if r.get('replay')]
        std = _mean([r.get('standard_esr', r.get('esr') if r.get('arm') in {'A', 'AS', 'R', 'P'} else None)
                     for r in subset])
        # Prefer explicit fields
        std = _mean([r['standard_esr'] for r in subset if r.get('standard_esr') is not None])
        if std is None:
            std = _mean([
                r['esr'] if r.get('esr') is not None else r.get('structural_success')
                for r in subset if r.get('arm') in {'A', 'AS', 'R', 'P'}
            ])
        structured = _mean([r['structured_esr'] for r in subset if r.get('structured_esr') is not None])
        if structured is None:
            structured = _mean([
                r['esr'] if r.get('esr') is not None else r.get('structural_success')
                for r in subset if r.get('arm') in {'H', 'HS', 'HS-no-validation'}
            ])
        delta = None
        if std is not None and structured is not None:
            delta = structured - std
        row_cells = [_cell(std, pending=True if std is not None else False),
                     _cell(structured, pending=True if structured is not None else False),
                     _cell(delta, pending=True if delta is not None else False)]
        # Clear pending if adjudicated present
        if any(r.get('esr_status') == 'adjudicated' for r in subset):
            for c in row_cells:
                if c['value'] is not None:
                    c['pending'] = False
                    c['display'] = _fmt(c['value'])
        cells.append({'key': key, 'label': label, 'cells': row_cells})
        rows_display.append([label] + [c['display'] for c in row_cells])
    out = {
        'id': '8',
        'title': 'Common-evidence interpretation template',
        'caption': 'Paired comparisons on identical observations when evidence_source/replay tags are present.',
        'headers': headers,
        'rows': rows_display,
        'cells': cells,
    }
    out.update(scope_for_records(records))
    return out


def aggregate_table9(records):
    headers = ['HS variant', 'ESR ↑', 'CPS ↑', 'Revision ↑', 'Cost ↓']
    rows_display, cells = [], []
    # Deduplicate display labels while keeping lookup keys
    seen_labels = []
    label_keys = {}
    for key, label in TABLE9_VARIANTS:
        if label not in label_keys:
            label_keys[label] = []
            seen_labels.append(label)
        label_keys[label].append(key)

    for label in seen_labels:
        keys = label_keys[label]
        subset = []
        for r in records:
            abl = r.get('ablation')
            arm = r.get('arm')
            if label == 'Full method' and arm == 'HS' and not abl:
                subset.append(r)
            elif abl in keys or arm in keys:
                subset.append(r)
        esr = _mean([
            r['esr'] if r.get('esr_status') == 'adjudicated' else r.get('structural_success')
            for r in subset
            if r.get('esr') is not None or r.get('structural_success') is not None
        ])
        pending = bool(subset) and not any(r.get('esr_status') == 'adjudicated' for r in subset) and esr is not None
        cps = _mean([r['cps'] for r in subset if r.get('cps') is not None])
        revision = _mean([r['revision'] for r in subset if r.get('revision') is not None])
        cost = _mean([r['completion_tokens'] for r in subset if r.get('completion_tokens') is not None])
        row_cells = [
            _cell(esr, len(subset), pending=pending),
            _cell(cps, len(subset)),
            _cell(revision, len(subset)),
            _cell(cost, len(subset), digits=1),
        ]
        cells.append({'label': label, 'cells': row_cells, 'n': len(subset)})
        rows_display.append([label] + [c['display'] for c in row_cells])
    out = {
        'id': '9',
        'title': 'Ablation template',
        'caption': 'HS variants via config.ablation or HS-no-validation arm.',
        'headers': headers,
        'rows': rows_display,
        'cells': cells,
    }
    out.update(scope_for_records(records))
    return out


def aggregate_table10(records):
    headers = ['Condition', 'Runs using scripts', 'Execution success', 'Validation pass',
               'Verified findings/run', 'False findings/run']
    rows_display, cells = [], []
    for arm, label in TABLE10_CONDITIONS:
        subset = _arm_rows(records, arm)
        used = _mean([r['used_script'] for r in subset if r.get('used_script') is not None])
        exe = _mean([r['execution_success'] for r in subset if r.get('execution_success') is not None])
        if arm == 'AS' or arm == 'HS-no-validation':
            val_display = 'N/A'
            val_cell = _cell(None)
            val_cell['display'] = 'N/A'
        else:
            val = _mean([r['validation_pass'] for r in subset if r.get('validation_pass') is not None])
            val_cell = _cell(val, len(subset))
            val_display = val_cell['display']
        verified = _mean([r['verified_findings'] for r in subset if r.get('verified_findings') is not None])
        false_f = _mean([r['false_findings'] for r in subset if r.get('false_findings') is not None])
        row_cells = [
            _cell(used, len(subset)),
            _cell(exe, len(subset)),
            val_cell,
            _cell(verified, len(subset), digits=2),
            _cell(false_f, len(subset), digits=2),
        ]
        cells.append({'arm': arm, 'label': label, 'cells': row_cells, 'n': len(subset)})
        rows_display.append([label, row_cells[0]['display'], row_cells[1]['display'],
                             val_display, row_cells[3]['display'], row_cells[4]['display']])
    out = {
        'id': '10',
        'title': 'Script evaluation template',
        'caption': 'Script usage derived from run traces for AS/HS arms.',
        'headers': headers,
        'rows': rows_display,
        'cells': cells,
    }
    out.update(scope_for_records(records))
    return out


def aggregate_table11(records):
    headers = ['Representation', 'ESR ↑', 'CPS ↑', 'Relation precision ↑', 'Token cost ↓']
    rows_display, cells = [], []
    for key, label in TABLE11_REPS:
        subset = [r for r in records if r.get('representation') == key]
        if key == 'full_graph' and not subset:
            subset = [r for r in records if r.get('has_graph') and r.get('arm') in {'H', 'HS', 'HS-no-validation'}
                      and not r.get('representation')]
        esr = _mean([
            r['esr'] if r.get('esr_status') == 'adjudicated' else r.get('structural_success')
            for r in subset
            if r.get('esr') is not None or r.get('structural_success') is not None
        ])
        pending = bool(subset) and esr is not None and not any(r.get('esr_status') == 'adjudicated' for r in subset)
        cps = _mean([r['cps'] for r in subset if r.get('cps') is not None])
        rel = _mean([r['relation_precision'] for r in subset if r.get('relation_precision') is not None])
        cost = _mean([r['completion_tokens'] for r in subset if r.get('completion_tokens') is not None])
        row_cells = [
            _cell(esr, len(subset), pending=pending),
            _cell(cps, len(subset)),
            _cell(rel, len(subset)),
            _cell(cost, len(subset), digits=1),
        ]
        cells.append({'key': key, 'label': label, 'cells': row_cells, 'n': len(subset)})
        rows_display.append([label] + [c['display'] for c in row_cells])
    out = {
        'id': '11',
        'title': 'Investigation graph results template',
        'caption': 'Graph runs without representation tag map to full_graph.',
        'headers': headers,
        'rows': rows_display,
        'cells': cells,
    }
    out.update(scope_for_records(records))
    return out


def aggregate_table12(records):
    headers = ['Technique', 'Controlled intervention', 'ESR ↑', 'CPS ↑', 'Cost ↓']
    rows_display, cells = [], []
    for key, title, intervention in TABLE12_TECHNIQUES:
        subset = [r for r in records if r.get('technique') == key]
        esr = _mean([
            r['esr'] if r.get('esr_status') == 'adjudicated' else r.get('structural_success')
            for r in subset
            if r.get('esr') is not None or r.get('structural_success') is not None
        ])
        pending = bool(subset) and esr is not None and not any(r.get('esr_status') == 'adjudicated' for r in subset)
        cps = _mean([r['cps'] for r in subset if r.get('cps') is not None])
        cost = _mean([r['completion_tokens'] for r in subset if r.get('completion_tokens') is not None])
        row_cells = [
            _cell(esr, len(subset), pending=pending),
            _cell(cps, len(subset)),
            _cell(cost, len(subset), digits=1),
        ]
        cells.append({'key': key, 'label': title, 'cells': row_cells, 'n': len(subset)})
        rows_display.append([title, intervention] + [c['display'] for c in row_cells])
    out = {
        'id': '12',
        'title': 'Technique comparison and results template',
        'caption': 'Filled when ledger rows set technique=…; otherwise blank.',
        'headers': headers,
        'rows': rows_display,
        'cells': cells,
    }
    out.update(scope_for_records(records))
    return out


def aggregate_tables(records):
    tables = {
        '6': aggregate_table6(records),
        '7': aggregate_table7(records),
        '8': aggregate_table8(records),
        '9': aggregate_table9(records),
        '10': aggregate_table10(records),
        '11': aggregate_table11(records),
        '12': aggregate_table12(records),
    }
    study = scope_for_records(records)
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'run_count': len(records),
        'paper': 'Beyond Retrieval: Open Dataset Experiments',
        'note': 'Em dashes mean unmeasured. "(pending)" marks structural proxies before human ESR adjudication. Cost is completion_tokens. Fixed retrieval (R) uses a frozen evidence bundle with replay (no adaptive tools).',
        'models_label': study['models_label'],
        'data_label': study['data_label'],
        'study': study['scope'],
        'tables': tables,
    }


def write_report(records, output_dir, template_html=None):
    """Write data.json, data.js, and index.html under output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = aggregate_tables(records)
    data_path = output_dir / 'data.json'
    data_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (output_dir / 'data.js').write_text(
        'window.RESULTS = ' + json.dumps(payload, ensure_ascii=False) + ';\n',
        encoding='utf-8',
    )
    html_path = output_dir / 'index.html'
    if template_html is None:
        template_html = Path(__file__).with_name('results_ui.html')
    template_html = Path(template_html)
    if template_html.exists():
        html_path.write_text(template_html.read_text(encoding='utf-8'), encoding='utf-8')
    elif not html_path.exists():
        raise FileNotFoundError(f'Missing results UI template: {template_html}')
    return payload


def seed_demo_ledger(records=None):
    """Synthetic multi-arm rows so the UI opens with filled cells."""
    if records is None:
        records = []
    base = {
        'base_case_id': 'demo',
        'environment': 'synthetic',
        'dataset': 'generic',
        'model': 'scripted-fixture',
        'repeat': 0,
        'status': 'completed',
        'false_findings': 0,
    }
    demo = [
        {**base, 'run_id': 'demo-R-V0', 'case_id': 'demo-V0', 'variant': 'V0', 'arm': 'R',
         'replay': True, 'tool_calls': 0, 'completion_tokens': 25, 'structural_success': 0.5,
         'esr_status': 'pending', 'used_script': 0.0},
        {**base, 'run_id': 'demo-A-V0', 'case_id': 'demo-V0', 'variant': 'V0', 'arm': 'A',
         'tool_calls': 2, 'completion_tokens': 40, 'structural_success': 1.0, 'esr_status': 'pending',
         'used_script': 0.0, 'execution_success': None, 'validation_pass': None, 'verified_findings': None},
        {**base, 'run_id': 'demo-H-V0', 'case_id': 'demo-V0', 'variant': 'V0', 'arm': 'H',
         'tool_calls': 3, 'completion_tokens': 80, 'structural_success': 1.0, 'esr_status': 'pending',
         'has_graph': True, 'used_script': 0.0},
        {**base, 'run_id': 'demo-AS-V0', 'case_id': 'demo-V0', 'variant': 'V0', 'arm': 'AS',
         'tool_calls': 4, 'completion_tokens': 120, 'structural_success': 1.0, 'esr_status': 'pending',
         'used_script': 1.0, 'execution_success': 1.0, 'validation_pass': None, 'verified_findings': 1},
        {**base, 'run_id': 'demo-HS-V0', 'case_id': 'demo-V0', 'variant': 'V0', 'arm': 'HS',
         'tool_calls': 5, 'completion_tokens': 160, 'structural_success': 1.0, 'esr': 1.0,
         'esr_status': 'adjudicated', 'has_graph': True, 'used_script': 1.0,
         'execution_success': 1.0, 'validation_pass': 1.0, 'verified_findings': 2, 'cps': 1.0},
        {**base, 'run_id': 'demo-HS-noval', 'case_id': 'demo-V0', 'variant': 'V0', 'arm': 'HS-no-validation',
         'ablation': 'no_script_validation', 'tool_calls': 5, 'completion_tokens': 150,
         'structural_success': 0.0, 'esr_status': 'pending', 'has_graph': True,
         'used_script': 1.0, 'execution_success': 1.0, 'verified_findings': 1},
        {**base, 'run_id': 'demo-A-V1', 'case_id': 'demo-V1', 'variant': 'V1', 'arm': 'A',
         'tool_calls': 2, 'completion_tokens': 42, 'structural_success': 1.0, 'esr_status': 'pending',
         'pair_metric': 'rename', 'pair_success': 1.0},
        {**base, 'run_id': 'demo-HS-V4', 'case_id': 'demo-V4', 'variant': 'V4', 'arm': 'HS',
         'tool_calls': 4, 'completion_tokens': 140, 'structural_success': 1.0, 'esr_status': 'pending',
         'has_graph': True, 'pair_metric': 'missing', 'pair_success': 1.0},
        {**base, 'run_id': 'demo-HS-V5', 'case_id': 'demo-V5', 'variant': 'V5', 'arm': 'HS',
         'tool_calls': 6, 'completion_tokens': 200, 'structural_success': 1.0, 'esr_status': 'pending',
         'has_graph': True, 'revision': 1.0},
        {**base, 'run_id': 'demo-replay-A', 'case_id': 'demo-V0', 'variant': 'V0', 'arm': 'A',
         'replay': True, 'evidence_source': 'independent', 'tool_calls': 0, 'completion_tokens': 30,
         'standard_esr': 0.5, 'structural_success': 0.5, 'esr_status': 'pending'},
        {**base, 'run_id': 'demo-replay-H', 'case_id': 'demo-V0', 'variant': 'V0', 'arm': 'H',
         'replay': True, 'evidence_source': 'independent', 'tool_calls': 0, 'completion_tokens': 45,
         'structured_esr': 0.8, 'structural_success': 0.8, 'esr_status': 'pending', 'has_graph': True},
    ]
    # Ensure any real records passed in also carry dataset when missing.
    enriched = []
    for r in records:
        row = dict(r)
        row.setdefault('dataset', 'generic')
        enriched.append(row)
    return enriched + demo
