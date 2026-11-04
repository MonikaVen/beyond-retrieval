import json
import tempfile
import unittest
from pathlib import Path

from beyond_retrieval.data import digest, normalize
from beyond_retrieval.evaluate import score
from beyond_retrieval.results import (
    DASH, aggregate_tables, append_ledger, load_ledger, record_from_run,
    seed_demo_ledger, write_report,
)
from beyond_retrieval.runner import ScriptedProvider, run, ARMS


class ResultsTests(unittest.TestCase):
    def test_empty_ledger_uses_dashes(self):
        payload = aggregate_tables([])
        self.assertEqual(payload['run_count'], 0)
        # Metric columns (skip labels / technique descriptions)
        metric_slices = {
            '6': slice(1, None),
            '7': slice(1, None),
            '8': slice(1, None),
            '9': slice(1, None),
            '10': slice(1, None),
            '11': slice(1, None),
            '12': slice(2, None),
        }
        for key, sl in metric_slices.items():
            table = payload['tables'][key]
            self.assertTrue(table['rows'])
            for row in table['rows']:
                for cell in row[sl]:
                    self.assertIn(cell, {DASH, 'N/A'})

    def test_demo_seed_fills_table6_arms(self):
        records = seed_demo_ledger()
        payload = aggregate_tables(records)
        self.assertIn('scripted-fixture', payload['models_label'])
        self.assertIn('generic', payload['data_label'])
        t6 = payload['tables']['6']
        self.assertEqual(t6['models_label'], 'scripted-fixture')
        self.assertIn('datasets: generic', t6['data_label'])
        by_label = {row[0]: row for row in t6['rows']}
        for label in ('R Fixed retrieval', 'A Standard agent', 'H Hypothesis agent', 'AS Agent + scripts', 'HS Full method'):
            row = by_label[label]
            self.assertNotEqual(row[5], DASH)  # cost tokens
        hs = by_label['HS Full method']
        self.assertEqual(hs[1], '1')  # adjudicated ESR
        self.assertEqual(by_label['R Fixed retrieval'][4], '0')  # no adaptive calls

    def test_script_arm_populates_table10(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'logs'
        path.write_text('host-a success\nhost-a failure\n')
        rows = normalize(path, 'generic', 'env', 'auth')
        case = {
            'id': 'case', 'base_case_id': 'case', 'environment': 'env', 'variant': 'V0',
            'question': 'Investigate', 'evidence_hash': digest(rows),
        }
        answer = {
            'verdict': 'insufficient_evidence',
            'probabilities': {'malicious': 0, 'benign': 0, 'insufficient_evidence': 1},
            'findings': [],
        }
        # AS with a script attempt that fails (no docker) then final — still records script attempt
        result = run(
            case, rows,
            {'arm': 'AS', 'model': 'x', 'max_calls': 4, 'docker_image': 'python@sha256:dead'},
            ScriptedProvider([
                {'kind': 'script', 'code': 'print(1)'},
                {'kind': 'final', 'answer': answer},
            ]),
        )
        row = record_from_run(result)
        self.assertEqual(row['arm'], 'AS')
        self.assertEqual(row['used_script'], 1.0)
        payload = aggregate_tables([row])
        t10 = {r[0]: r for r in payload['tables']['10']['rows']}
        self.assertEqual(t10['AS Standard scripts'][1], '1')
        self.assertEqual(t10['AS Standard scripts'][3], 'N/A')

    def test_write_report_emits_ui_files(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / 'ui'
        payload = write_report(seed_demo_ledger(), out)
        self.assertTrue((out / 'data.json').exists())
        self.assertTrue((out / 'data.js').exists())
        self.assertTrue((out / 'index.html').exists())
        data = json.loads((out / 'data.json').read_text(encoding='utf-8'))
        self.assertEqual(data['run_count'], payload['run_count'])
        js = (out / 'data.js').read_text(encoding='utf-8')
        self.assertTrue(js.startswith('window.RESULTS = '))

    def test_fixed_retrieval_arm_forces_replay(self):
        self.assertIn('R', ARMS)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'logs'
        path.write_text('host-a success\nhost-a failure\n')
        rows = normalize(path, 'generic', 'env', 'auth')
        case = {
            'id': 'case', 'environment': 'env', 'dataset': 'generic', 'variant': 'V0',
            'question': 'Investigate', 'evidence_hash': digest(rows),
        }
        answer = {
            'verdict': 'insufficient_evidence',
            'probabilities': {'malicious': 0, 'benign': 0, 'insufficient_evidence': 1},
            'findings': [],
        }
        result = run(case, rows, {'arm': 'R', 'model': 'scripted-fixture'}, ScriptedProvider([
            {'kind': 'final', 'answer': answer},
        ]))
        self.assertTrue(result['config']['replay'])
        self.assertEqual(result['stages'][-1]['status'], 'completed')
        self.assertEqual(result['tool_calls'], 0)
        row = record_from_run(result, case=case, rows=rows)
        self.assertEqual(row['arm'], 'R')
        self.assertEqual(row['dataset'], 'generic')
        self.assertEqual(row['model'], 'scripted-fixture')

    def test_ledger_roundtrip(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ledger = Path(tmp.name) / 'ledger.jsonl'
        append_ledger(ledger, {'arm': 'A', 'tool_calls': 2})
        append_ledger(ledger, {'arm': 'H', 'tool_calls': 3})
        rows = load_ledger(ledger)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['arm'], 'H')

    def test_record_from_run_score_pending(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'logs'
        path.write_text('host-a success\nhost-a failure\n')
        rows = normalize(path, 'generic', 'env', 'auth')
        case = {
            'id': 'case', 'environment': 'env', 'variant': 'V0',
            'question': 'Investigate', 'evidence_hash': digest(rows),
        }
        answer = {
            'verdict': 'insufficient_evidence',
            'probabilities': {'malicious': 0, 'benign': 0, 'insufficient_evidence': 1},
            'findings': [{'key': 'failed_login', 'value': 'bob', 'evidence_ids': [rows[1]['id']]}],
        }
        result = run(case, rows, {'arm': 'A', 'max_calls': 4}, ScriptedProvider([
            {'kind': 'tool', 'tool': 'get_records', 'args': {'ids': [rows[1]['id']]}},
            {'kind': 'final', 'answer': answer},
        ]))
        self.assertEqual(result['stages'][-1]['status'], 'completed')
        scored = score(result, {
            'mandatory': {'failed_login': 'bob'},
            'admissible_verdicts': ['insufficient_evidence'],
        })
        self.assertEqual(scored['status'], 'pending_human_review')
        row = record_from_run(result, scored)
        self.assertEqual(row['esr_status'], 'pending')
        self.assertEqual(row['structural_success'], 1.0)
        self.assertIsNone(row['esr'])


if __name__ == '__main__':
    unittest.main()
