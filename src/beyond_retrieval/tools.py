"""Read-only evidence interface and optional container-isolated scripts."""
from collections import Counter
import json
import re
import subprocess
import tempfile
from pathlib import Path
from .data import save_events


class EvidenceTools:
    def __init__(self, rows, page_limit=200, char_limit=12000):
        self.rows = sorted(rows, key=lambda r: r['id'])
        self.page_limit, self.char_limit = page_limit, char_limit
        self.ids = {r['id'] for r in rows}

    def call(self, name, args):
        if name == 'list_sources':
            return {'sources': sorted({r['source'] for r in self.rows})}
        if name == 'describe_schema':
            return {'columns': ['id','source','timestamp','raw','fields','origin','environment'],
                    'note': 'timestamp may be null; origin links to immutable source index'}
        if name == 'get_records':
            ids = args['ids']
            if not isinstance(ids, list) or len(ids)>200:
                raise ValueError('ids must be a list of at most 200 IDs')
            if not set(ids) <= self.ids:
                raise ValueError('Requested record unavailable in current evidence view')
            return self.page([r for r in self.rows if r['id'] in ids], args)
        if name in {'search_events','aggregate_events'}:
            source, query = args.get('source'), args.get('contains', '')
            if not isinstance(query, str): raise ValueError('contains must be a string')
            rows = [r for r in self.rows if (source is None or r['source']==source)
                    and query.casefold() in r['raw'].casefold()]
            if name == 'search_events': return self.page(rows, args)
            group = args.get('group_by','source')
            if group not in {'source','environment','timestamp'}:
                raise ValueError('Only source/environment/timestamp grouping is supported')
            counts = Counter(str(r.get(group)) for r in rows)
            # A cap prevents an aggregate from bypassing the evidence output budget.
            values = [{'group':k,'count':v} for k,v in sorted(counts.items())]
            return self.page(values,args)
        raise ValueError('Unknown or disabled tool: '+name)

    def page(self, rows, args):
        offset, limit = args.get('offset',0), args.get('limit',self.page_limit)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=self.page_limit:
            raise ValueError('Invalid pagination')
        out, size = [], 0
        for r in rows[offset:offset+limit]:
            n = len(json.dumps(r,ensure_ascii=False))
            if not out and n>self.char_limit:
                return {'error':'record_exceeds_page_limit','offset':offset,
                        'record_id':r.get('id'), 'truncated':True,
                        'note':'Curator must provide audited chunking before evaluation.'}
            if size+n>self.char_limit: break
            out.append(r); size+=n
        end=offset+len(out)
        return {'records':out,'total':len(rows),'truncated':end<len(rows),
                'next_offset':end if end<len(rows) else None}


class DockerScripts:
    """No host execution fallback. Docker is required; pin image by digest.

    This is isolation for controlled experiments, not a claim of a hardened
    multi-tenant sandbox. Only evidence and generated script enter the container.
    """
    def __init__(self, image, timeout=120):
        if not re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}',image):
            raise ValueError('Docker image must be pinned using @sha256:<64 hex>')
        self.image, self.timeout = image, timeout

    def execute(self, code, rows):
        if len(code)>100000: raise ValueError('Script too large')
        with tempfile.TemporaryDirectory(prefix='beyond-') as td:
            root=Path(td); ev=root/'evidence'; work=root/'work'
            ev.mkdir(); work.mkdir(); save_events(ev/'events.jsonl',rows)
            (work/'main.py').write_text(code)
            cmd=['docker','run','--rm','--network=none','--read-only',
                 '--cap-drop=ALL','--security-opt=no-new-privileges',
                 '--pids-limit=64','--memory=512m','--cpus=1',
                 '--ulimit','cpu=120:120','--ulimit','fsize=1048576:1048576',
                 '--user','65534:65534','--tmpfs','/tmp:rw,noexec,nosuid,size=64m',
                 '--mount',f'type=bind,src={ev},dst=/evidence,readonly',
                 '--mount',f'type=bind,src={work},dst=/work,readonly',
                 self.image,'python','-I','/work/main.py']
            # File-backed bounded stdout avoids unbounded host RAM allocation.
            # Explicit container name permits cleanup after timeout.
            import uuid
            name='beyond-'+uuid.uuid4().hex
            cmd[2:2]=['--name',name]
            output=root/'stdout'; errors=root/'stderr'
            try:
                with output.open('wb') as stdout, errors.open('wb') as stderr:
                    proc=subprocess.Popen(cmd,stdout=stdout,stderr=stderr)
                    import time
                    start=time.monotonic()
                    while proc.poll() is None:
                        if time.monotonic()-start>self.timeout or output.stat().st_size+errors.stat().st_size>1_000_000:
                            subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
                            proc.kill(); proc.wait(); raise TimeoutError('Script time/output cap reached')
                        time.sleep(.05)
                if output.stat().st_size+errors.stat().st_size>1_000_000:
                    raise ValueError('Script output cap exceeded')
                if proc.returncode:
                    raise ValueError('Container script failed: '+errors.read_text(errors='replace')[:1000])
                value=json.loads(output.read_text())
                if not isinstance(value,dict) or not isinstance(value.get('findings'),list):
                    raise ValueError('Script must print {"findings": [...]} JSON')
                return value
            finally:
                subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
