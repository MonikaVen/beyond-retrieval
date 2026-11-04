"""Clean pdfplumber extracts into dashboard-ready paper tables."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'datasets' / 'paper_tables.json'
OUT = ROOT / 'datasets' / 'paper_tables_clean.json'


def collapse_row(row):
    return [(' '.join((c or '').split())).strip() for c in (row or [])]


def drop_empty_cols(rows):
    if not rows:
        return rows
    width = max(len(r) for r in rows)
    rows = [r + [''] * (width - len(r)) for r in rows]
    keep = [i for i in range(width) if any((r[i] or '').strip() for r in rows)]
    return [[r[i] for i in keep] for r in rows]


def merge_header_lines(rows, header_lines=1):
    """Merge leading mostly-empty continuation header lines into one header."""
    if len(rows) < 2:
        return rows
    # Heuristic: if row1 has few filled cells and looks like header continuation, merge.
    def filled(r):
        return [c for c in r if c]

    head = rows[0]
    i = 1
    while i < min(3, len(rows)):
        nxt = rows[i]
        # continuation if many empties and short fragments, or all values look like header fragments
        if sum(1 for c in nxt if c) <= max(3, len(filled(head)) // 2) and not any(
            re.match(r'^(V\d|H\d|E\d|A |H |AS |HS |R |P )', c) for c in filled(nxt)
        ):
            merged = []
            width = max(len(head), len(nxt))
            head = head + [''] * (width - len(head))
            nxt = nxt + [''] * (width - len(nxt))
            for a, b in zip(head, nxt):
                merged.append((a + ' ' + b).strip() if b else a)
            head = merged
            i += 1
        else:
            break
    return [head] + rows[i:]


def clean_matrix(raw_rows):
    rows = [collapse_row(r) for r in raw_rows]
    rows = [r for r in rows if any(c for c in r)]
    rows = drop_empty_cols(rows)
    rows = merge_header_lines(rows)
    rows = drop_empty_cols(rows)
    # collapse duplicate whitespace again after merges
    rows = [[re.sub(r'\s+', ' ', c).strip() for c in r] for r in rows]
    return rows


def page_text(data, page):
    marker = f'===== PAGE {page} =====\n'
    chunk = data['full_text'].split(marker, 1)
    if len(chunk) < 2:
        return ''
    rest = chunk[1]
    nxt = rest.find('\n===== PAGE ')
    return rest if nxt < 0 else rest[:nxt]


def main():
    data = json.loads(SRC.read_text(encoding='utf-8'))
    raw = data['tables']

    # Map raw indices to logical tables after cleaning/merging continuations.
    # Table 1
    t1 = clean_matrix(raw[0]['rows'])
    # Table 2
    t2 = clean_matrix(raw[1]['rows'])
    # Table 3 = page4 part + page5 continuation
    t3a = clean_matrix(raw[2]['rows'])
    t3b = clean_matrix(raw[3]['rows'])
    t3 = [t3a[0]] + t3a[1:] + t3b[1:]  # skip repeated header

    # Table 4 — messy extraction; rebuild from known structure in text if needed
    t4 = clean_matrix(raw[4]['rows'])
    # Manual cleanup for split cells in Table 4
    fixed4 = [t4[0]]
    buf = None
    for r in t4[1:]:
        cells = [c for c in r if c]
        if not cells:
            continue
        # rows that are continuation fragments
        if len(cells) == 1 and buf is not None:
            # append to previous definition column if exists
            if len(buf) >= 2:
                buf[1] = (buf[1] + ' ' + cells[0]).strip()
            continue
        if len(r) >= 3 and r[0] and not r[1] and r[2]:
            # metric in col0, definition empty, scoring in col2 — shift
            buf = [r[0], '', r[2]]
            fixed4.append(buf)
            continue
        buf = r[:]
        fixed4.append(buf)
    t4 = drop_empty_cols(fixed4)

    # Table 5 = page6 + page7 continuation
    t5a = clean_matrix(raw[5]['rows'])
    t5b = clean_matrix(raw[6]['rows'])
    # Fix H4 row fragmentation
    if len(t5b) >= 2:
        h4 = t5b[1]
        if len(t5b) > 2 and len([c for c in t5b[2] if c]) <= 1:
            # already cleaned by merge_header maybe
            pass
        # rebuild H4 from text
        t5b = [t5a[0], [
            'H4 Validation adds value',
            'HS versus HS without script validation',
            'V0 ESR on script-useful subset',
        ]]
    t5 = t5a[:1] + t5a[1:] + t5b[1:]

    t6 = clean_matrix(raw[7]['rows'])
    t7a = clean_matrix(raw[8]['rows'])
    t7b = clean_matrix(raw[9]['rows'])
    # Table 7 split across two extracts; merge body
    t7 = [t7a[0]] + t7a[1:] + t7b[1:]

    t8 = clean_matrix(raw[10]['rows'])
    t9a = clean_matrix(raw[11]['rows'])
    t9b = clean_matrix(raw[12]['rows'])
    t9 = [t9a[0]] + t9a[1:] + t9b[1:]

    t10 = clean_matrix(raw[13]['rows'])

    t11a = clean_matrix(raw[14]['rows'])
    t11b = clean_matrix(raw[15]['rows'])
    t11 = [t11a[0]] + t11a[1:] + t11b[1:]

    t12 = clean_matrix(raw[16]['rows'])

    # Appendix-like tables
    a_contract = clean_matrix(raw[17]['rows'])
    a_plan = clean_matrix(raw[18]['rows'])
    a_sources = clean_matrix(raw[19]['rows'])
    a_split = clean_matrix(raw[20]['rows'])
    a_questions = clean_matrix(raw[21]['rows'])
    # skip junk single-column fragments raw[22], raw[23]
    a_versions = clean_matrix(raw[24]['rows'])
    a_exp1 = clean_matrix(raw[25]['rows'])
    a_exp2 = clean_matrix(raw[26]['rows'])
    a_experiments = [a_exp1[0]] + a_exp1[1:] + a_exp2[1:]

    # Improve Table 4 from page text if extraction is too broken
    p6 = page_text(data, 6)
    if 'ESR' in p6 and len(t4) < 5:
        # fallback structured rows from paper semantics (still paper content)
        t4 = [
            ['Metric', 'Operational definition', 'Scoring source'],
            ['ESR ↑', 'Admissible answer, required findings, valid support, no material unsupported invention', 'Frozen evidence rubric'],
            ['CPS ↑', 'Both original and counterfactual pass ESR', 'Paired run outcomes'],
            ['Revision ↑', 'Final answer improves after withheld evidence is released', 'V5 provisional vs final'],
            ['Unsupported claims ↓', 'Material claims without valid support', 'Evidence audit'],
            ['Calls ↓', 'Tool or script invocations used', 'Run trace'],
            ['Cost / run ↓', 'Tokens, wall time, or billed cost per completed run', 'Run accounting'],
        ]

    # Fix Table 12 body fragmentation: join description continuations
    fixed12 = [t12[0]]
    current = None
    for r in t12[1:]:
        filled = [c for c in r if c]
        if len(filled) == 1 and current is not None and len(current) >= 2:
            # continuation of intervention text
            current[1] = (current[1] + ' ' + filled[0]).strip()
            continue
        current = r[:]
        # ensure 4 columns
        while len(current) < 4:
            current.append('')
        fixed12.append(current[:4])
    t12 = drop_empty_cols(fixed12)

    # Fix sources table continuations
    fixed_src = [a_sources[0]]
    cur = None
    for r in a_sources[1:]:
        filled = [c for c in r if c]
        if len(filled) == 1 and cur is not None:
            cur[-1] = (cur[-1] + ' ' + filled[0]).strip()
            continue
        cur = r[:]
        fixed_src.append(cur)
    a_sources = drop_empty_cols(fixed_src)

    # Fix questions table
    fixed_q = [a_questions[0]]
    cur = None
    for r in a_questions[1:]:
        filled = [c for c in r if c]
        if len(filled) <= 1 and cur is not None:
            cur[-1] = (cur[-1] + ' ' + ' '.join(filled)).strip()
            continue
        cur = r[:]
        fixed_q.append(cur)
    a_questions = drop_empty_cols(fixed_q)

    # Fix versions table
    fixed_v = [a_versions[0]]
    cur = None
    for r in a_versions[1:]:
        filled = [c for c in r if c]
        if len(filled) == 1 and cur is not None:
            # append to construction or validity
            if len(cur) >= 3:
                # decide which column based on heuristics
                cur[1] = (cur[1] + ' ' + filled[0]).strip()
            continue
        cur = r[:]
        fixed_v.append(cur)
    a_versions = drop_empty_cols(fixed_v)

    # Fix plan table
    fixed_p = [a_plan[0]]
    cur = None
    for r in a_plan[1:]:
        filled = [c for c in r if c]
        if len(filled) == 1 and cur is not None:
            cur[-1] = (cur[-1] + ' ' + filled[0]).strip()
            continue
        cur = r[:]
        fixed_p.append(cur)
    a_plan = drop_empty_cols(fixed_p)

    # Fix experiments
    fixed_e = [a_experiments[0]]
    cur = None
    for r in a_experiments[1:]:
        filled = [c for c in r if c]
        if len(filled) <= 1 and cur is not None:
            # likely name/outcome continuation
            if filled and not re.match(r'^E\d', filled[0]):
                # append to comparison
                if len(cur) >= 2:
                    cur[1] = (cur[1] + ' ' + filled[0]).strip()
                continue
        cur = r[:]
        fixed_e.append(cur)
    a_experiments = drop_empty_cols(fixed_e)

    tables = [
        {
            'id': 'table-1',
            'number': '1',
            'section': 'Main',
            'title': 'Positioning relative to selected prior work',
            'caption': 'Descriptions summarize scope, not an exhaustive feature audit.',
            'page': 2,
            'headers': t1[0],
            'rows': t1[1:],
        },
        {
            'id': 'table-2',
            'number': '2',
            'section': 'Main',
            'title': 'Recorded-data variants and optional regenerated counterpart',
            'caption': 'Eligibility is determined before agent runs; not every base case supports every variant.',
            'page': 4,
            'headers': t2[0],
            'rows': t2[1:],
        },
        {
            'id': 'table-3',
            'number': '3',
            'section': 'Main',
            'title': 'Condition definitions',
            'caption': 'A, H, AS, and HS comprise the core grid; R and P are secondary controls on a preregistered subset.',
            'page': 4,
            'headers': t3[0],
            'rows': t3[1:],
        },
        {
            'id': 'table-4',
            'number': '4',
            'section': 'Main',
            'title': 'Outcome definitions and scoring sources',
            'caption': 'Higher ESR/CPS/Revision and lower unsupported claims, calls, and cost are better where marked.',
            'page': 6,
            'headers': t4[0],
            'rows': t4[1:],
        },
        {
            'id': 'table-5',
            'number': '5',
            'section': 'Main',
            'title': 'Confirmatory hypotheses and contrasts',
            'caption': 'Higher ESR and CPS indicate better performance.',
            'page': 6,
            'headers': t5[0],
            'rows': t5[1:],
        },
        {
            'id': 'table-6',
            'number': '6',
            'section': 'Templates',
            'title': 'Reporting template (core V0 cohort)',
            'caption': 'Populate A, H, AS, and HS for the full V0 cohort; show R and P only on their shared secondary subset, with denominators.',
            'page': 8,
            'headers': t6[0],
            'rows': t6[1:],
        },
        {
            'id': 'table-7',
            'number': '7',
            'section': 'Templates',
            'title': 'Intervention results template',
            'caption': 'Core results cover renaming, distractors, missing evidence and delayed evidence. Counterfactual CPS is reported only where defined.',
            'page': 8,
            'headers': t7[0],
            'rows': t7[1:],
        },
        {
            'id': 'table-8',
            'number': '8',
            'section': 'Templates',
            'title': 'Common-evidence interpretation template',
            'caption': 'Each row is a paired comparison on identical observations; collector thoughts and conclusions are removed.',
            'page': 9,
            'headers': t8[0],
            'rows': t8[1:],
        },
        {
            'id': 'table-9',
            'number': '9',
            'section': 'Templates',
            'title': 'Ablation template',
            'caption': 'Match content, available tools, and budget; record actual resource differences.',
            'page': 9,
            'headers': t9[0],
            'rows': t9[1:],
        },
        {
            'id': 'table-10',
            'number': '10',
            'section': 'Templates',
            'title': 'Script evaluation template',
            'caption': 'Report conditional script statistics alongside unconditional case-level ESR.',
            'page': 10,
            'headers': t10[0],
            'rows': t10[1:],
        },
        {
            'id': 'table-11',
            'number': '11',
            'section': 'Templates',
            'title': 'Investigation graph results template',
            'caption': 'Run both common-evidence and online-construction settings; report them separately.',
            'page': 11,
            'headers': t11[0],
            'rows': t11[1:],
        },
        {
            'id': 'table-12',
            'number': '12',
            'section': 'Templates',
            'title': 'Technique comparison and results template',
            'caption': 'All methods use the same backbone and permitted evidence; dashes denote unmeasured outcomes.',
            'page': 12,
            'headers': t12[0],
            'rows': t12[1:],
        },
        {
            'id': 'appendix-contract',
            'number': 'A1',
            'section': 'Appendix',
            'title': 'Investigation-contract fields',
            'caption': 'Required fields for hypothesis-driven actions.',
            'page': 16,
            'headers': a_contract[0],
            'rows': a_contract[1:],
        },
        {
            'id': 'appendix-plan',
            'number': 'A2',
            'section': 'Appendix',
            'title': 'Planned study parameters',
            'caption': 'Frozen planning values for dataset allocation and evaluation grid.',
            'page': 17,
            'headers': a_plan[0],
            'rows': a_plan[1:],
        },
        {
            'id': 'appendix-sources',
            'number': 'A3',
            'section': 'Appendix',
            'title': 'Data sources and study role',
            'caption': 'Public datasets used for core and transfer experiments.',
            'page': 19,
            'headers': a_sources[0],
            'rows': a_sources[1:],
        },
        {
            'id': 'appendix-split',
            'number': 'A4',
            'section': 'Appendix',
            'title': 'Environment split and case targets',
            'caption': 'Proposed AIT / external partitions.',
            'page': 19,
            'headers': a_split[0],
            'rows': a_split[1:],
        },
        {
            'id': 'appendix-questions',
            'number': 'A5',
            'section': 'Appendix',
            'title': 'Candidate questions and admission rules',
            'caption': 'Question families with required evidence linkage.',
            'page': 20,
            'headers': a_questions[0],
            'rows': a_questions[1:],
        },
        {
            'id': 'appendix-versions',
            'number': 'A6',
            'section': 'Appendix',
            'title': 'Variant construction and validity checks',
            'caption': 'How V0–V5 cases are built and audited.',
            'page': 21,
            'headers': a_versions[0],
            'rows': a_versions[1:],
        },
        {
            'id': 'appendix-experiments',
            'number': 'A7',
            'section': 'Appendix',
            'title': 'Experiment schedule and target runs',
            'caption': 'E1–En comparisons with maximum planned run counts.',
            'page': 21,
            'headers': a_experiments[0],
            'rows': a_experiments[1:],
        },
    ]

    # Normalize headers/rows to equal width strings
    for t in tables:
        width = max(len(t['headers']), max((len(r) for r in t['rows']), default=0))
        t['headers'] = (t['headers'] + [''] * width)[:width]
        t['rows'] = [(r + [''] * width)[:width] for r in t['rows']]
        t['row_count'] = len(t['rows'])
        t['col_count'] = width

    payload = {
        'source': data['source'],
        'paper': 'Beyond Retrieval: Open Dataset Experiments',
        'page_count': data['page_count'],
        'table_count': len(tables),
        'tables': tables,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    for t in tables:
        print(f"{t['number']:>3} {t['title'][:48]:48} {t['row_count']}x{t['col_count']}")
    print('wrote', OUT)


if __name__ == '__main__':
    main()
