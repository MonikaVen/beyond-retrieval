"""Executable validation; distinguishes mock transport, Docker, and live model checks."""
import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from .runner import ChatProvider, run
from .tools import DockerScripts
from .data import digest

SCRIPT='''import json
rows=[json.loads(line) for line in open('/evidence/events.jsonl') if line.strip()]
print(json.dumps({'findings':[{'key':'failed_logins','value':sum('failed_login' in r['raw'] for r in rows),'evidence_ids':[r['id'] for r in rows if 'failed_login' in r['raw']]}]}))
'''

def http_check():
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            payload={'choices':[{'message':{'content':json.dumps({'kind':'tool','tool':'list_sources','args':{}})}}], 'usage':{'completion_tokens':9}}
            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(json.dumps(payload).encode())
    server=HTTPServer(('127.0.0.1',0),Handler); thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        result,tokens=ChatProvider(f'http://127.0.0.1:{server.server_port}/v1/chat/completions','mock','UNUSED_MOCK_KEY')([{'role':'user','content':'probe'}],12,3)
        assert result['tool']=='list_sources' and tokens==9 and received[0]['max_tokens']==12
        return {'status':'passed','scope':'HTTP transport against deterministic mock; not live inference'}
    finally:server.shutdown();server.server_close();thread.join()

def validate(case, rows, image=None, config=None, fixture=None, lesson_bank=None):
    report={'sample_evidence_hash':digest(rows),'mock_http':http_check()}
    if not shutil.which('docker'):report['docker']={'status':'blocked','reason':'Docker executable unavailable'}
    elif not image:report['docker']={'status':'blocked','reason':'Supply a digest-pinned --image'}
    else:
        try:
            probe=subprocess.run(['docker','info'],capture_output=True,timeout=15)
            if probe.returncode:raise RuntimeError('Docker daemon unavailable')
            executor=DockerScripts(image,timeout=15)
            result=executor.execute(SCRIPT,rows)
            expected={'findings':[{'key':'failed_logins','value':sum('failed_login' in r['raw'] for r in rows),'evidence_ids':[r['id'] for r in rows if 'failed_login' in r['raw']]}]}
            assert result==expected
            # Validate runtime configuration inside the container, not just command flags.
            isolation="""import json,os,socket
assert os.getuid()==65534
assert set(os.listdir('/sys/class/net'))=={'lo'}
try:
 open('/evidence/probe','w').write('x')
 raise AssertionError('writable evidence mount')
except OSError: pass
try:
 open('/root-probe','w').write('x')
 raise AssertionError('writable root filesystem')
except OSError: pass
print(json.dumps({'findings':[]}))
"""
            executor.execute(isolation,rows)
            report['docker']={'status':'passed','image':image,'checks':['sample result','non-root','network namespace','read-only evidence','read-only root']}
        except Exception as exc:report['docker']={'status':'failed','reason':str(exc)}
    if not config:report['live_model']={'status':'blocked','reason':'No model endpoint/config supplied'}
    else:
        try:
            result=run(case,rows,config,ChatProvider(config['endpoint'],config['model'],config.get('key_env','EXPERIMENT_API_KEY')),fixture=fixture,lesson_bank=lesson_bank)
            report['live_model']={'status':'passed' if all(x['status']=='completed' for x in result['stages']) else 'failed',
                                  'scope':'Protocol completion only; no semantic performance claim','run':result}
        except Exception as exc:report['live_model']={'status':'failed','reason':str(exc)}
    return report
