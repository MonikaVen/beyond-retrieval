"""Canonical records, conservative import adapters, and evidence transformations."""
import hashlib
import json
import re
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def load_events(path):
    rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    ids = set()
    for row in rows:
        for key in ('id', 'source', 'raw', 'origin', 'environment'):
            if key not in row:
                raise ValueError(f'Missing event field: {key}')
        if row['id'] in ids:
            raise ValueError('Duplicate event ID')
        ids.add(row['id'])
    return rows


def save_events(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))


def normalize(path, dataset, environment, source, json_array=False):
    """Import ONE explicitly selected telemetry file, never recursively scan labels.

    AIT raw text is retained without inventing timestamps; OTRF/OpTC structured
    fields are preserved. Dataset-specific semantic joins require curated rules.
    """
    path = Path(path)
    if any(x.lower() in {'labels', 'ground_truth', 'groundtruth', 'answers'} for x in path.parts):
        raise ValueError('Evaluator labels cannot be imported as telemetry')
    blob = path.read_bytes()
    sha = hashlib.sha256(blob).hexdigest()
    if json_array:
        items = json.loads(blob)
        if not isinstance(items, list):
            raise ValueError('--json-array expects a JSON array')
        iterator = [(i, json.dumps(v), v) for i, v in enumerate(items, 1)]
    else:
        iterator = []
        for i, line in enumerate(blob.decode('utf-8', errors='replace').splitlines(), 1):
            if not line.strip():
                continue
            try:
                fields = json.loads(line)
                if not isinstance(fields, dict):
                    fields = {'value': fields}
            except json.JSONDecodeError:
                fields = {}
            iterator.append((i, line, fields))
    if dataset not in {'ait', 'otrf', 'optc', 'generic'}:
        raise ValueError('Unsupported dataset')
    rows = []
    for line, raw, fields in iterator:
        if not isinstance(fields, dict):
            fields = {'value': fields}
        rows.append({
            'id': digest([dataset, environment, sha, line])[:24],
            'dataset': dataset, 'environment': environment, 'source': source,
            'timestamp': fields.get('@timestamp', fields.get('timestamp')),
            'fields': fields, 'raw': raw,
            'origin': {'sha256': sha, 'index': line,
                       'index_type': 'array_item' if json_array else 'original_line'},
            'parse_status': 'structured' if fields else 'raw_only',
        })
    return rows


def transform(rows, variant, spec, extra=()):
    """Mechanical transforms only. A successful transform is NOT a validity audit."""
    rows = json.loads(json.dumps(rows))
    if variant == 'V0':
        return rows
    if variant == 'V1':
        mapping = spec['mapping']
        if not mapping or len(set(mapping.values())) != len(mapping):
            raise ValueError('Entity mapping must be nonempty and bijective')
        if any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k,v in mapping.items()):
            raise ValueError('Mapping keys and values must be nonempty strings')
        # Single-pass replacement avoids cascading A->B->C. Curator must ensure
        # identifiers are not command semantics or coincidental substrings.
        pattern = re.compile(r'(?<![\w])(' + '|'.join(re.escape(k) for k in sorted(mapping,key=len,reverse=True)) + r')(?![\w])')
        def rewrite(v):
            if isinstance(v, str):
                return pattern.sub(lambda m: mapping[m.group(0)], v)
            if isinstance(v, list): return [rewrite(x) for x in v]
            if isinstance(v, dict): return {k: rewrite(x) for k,x in v.items()}
            return v
        for r in rows:
            # Stable record IDs and original provenance are never rewritten.
            r['raw'] = rewrite(r['raw']); r['fields'] = rewrite(r.get('fields', {}))
        return rows
    if variant == 'V2':
        envs = {r['environment'] for r in rows}
        if len(envs) != 1 or any(r['environment'] not in envs for r in extra):
            raise ValueError('Distractors must come from the same environment')
        combined = rows + list(extra)
        if len({r['id'] for r in combined}) != len(combined):
            raise ValueError('Distractors duplicate existing records')
        return combined
    if variant == 'V4':
        hidden = set(spec['hide_ids'])
        if not hidden or not hidden <= {r['id'] for r in rows}:
            raise ValueError('Hidden IDs must be a nonempty subset')
        return [r for r in rows if r['id'] not in hidden]
    raise ValueError('V5 uses stage IDs in the case; V3 requires new recordings')


def case_events(case, case_path):
    root = Path(case_path).resolve().parent
    path = (root / case['events']).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Evidence file must be inside case directory')
    rows = load_events(path)
    if digest(rows) != case['evidence_hash']:
        raise ValueError('Evidence hash mismatch')
    return rows
