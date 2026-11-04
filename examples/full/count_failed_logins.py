import json
rows=[json.loads(line) for line in open('/evidence/events.jsonl') if line.strip()]
print(json.dumps({'findings':[{'key':'failed_logins','value':sum('failed_login' in r['raw'] for r in rows),'evidence_ids':[r['id'] for r in rows if 'failed_login' in r['raw']]}]}))
