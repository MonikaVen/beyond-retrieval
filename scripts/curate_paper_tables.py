"""Hand-curate paper tables from PDF extracts into dashboard-ready JSON."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'datasets' / 'paper_tables_dashboard.json'
SOURCE = r'C:\Users\monik\Downloads\Beyond_Retrieval_Open_Dataset_Experiments (1).pdf'

TABLES = [
    {
        'id': 'table-1', 'number': '1', 'section': 'Main', 'page': 2,
        'title': 'Positioning relative to selected prior work',
        'caption': 'Descriptions summarize scope, not an exhaustive feature audit.',
        'headers': ['Work', 'Primary emphasis', 'Role in this study'],
        'rows': [
            ['ReAct and Reflexion [1, 2]', 'Action loops and feedback', 'Agent and reflection baselines'],
            ['Agentic Reasoning [3]', 'Tools and structured memory', 'Graph-memory motivation'],
            ['ReSearch and ARTIST [4, 5]', 'Learning search and tool policies', 'Future training direction'],
            ['ExpeL [6]', 'Experience-derived guidance', 'Conditional lesson memory'],
            ['DiscoveryWorld [7]', 'Scientific discovery cycles', 'Intervention-based task design'],
            ['ExCyTIn and CFA-Bench [11, 12]', 'Cybersecurity investigations', 'Domain evaluation context'],
        ],
    },
    {
        'id': 'table-2', 'number': '2', 'section': 'Main', 'page': 4,
        'title': 'Recorded-data variants and optional regenerated counterpart',
        'caption': 'Eligibility is determined before agent runs; not every base case supports every variant.',
        'headers': ['Version', 'Controlled change', 'Expected response'],
        'rows': [
            ['V0 Original', 'Original public records; frozen case scope', 'Evidence-supported resolution'],
            ['V1 Renaming', 'Consistent opaque entity identifiers across all sources', 'Same answer after mapping'],
            ['V2 Distractors', 'Additional unrelated activity from same recording', 'Stable supported conclusion'],
            ['V3 Regenerated (optional)', 'Mechanism changed in a new paired testbed run', 'Correct alternative explanation'],
            ['V4 Missing evidence', 'All access paths to a mandatory finding removed', 'Explicitly qualified answer'],
            ['V5 Delayed evidence', 'Shared incomplete bundle, then decisive release', 'Appropriate revision or resolution'],
        ],
    },
    {
        'id': 'table-3', 'number': '3', 'section': 'Main', 'page': 4,
        'title': 'Condition definitions',
        'caption': 'A, H, AS, and HS comprise the core grid; R and P are secondary controls on a preregistered subset.',
        'headers': ['ID', 'Condition', 'Adaptive queries', 'Custom scripts', 'Guidance'],
        'rows': [
            ['R', 'Fixed retrieval plus synthesis', 'No', 'No', 'Common domain facts'],
            ['A', 'Standard tool-using agent', 'Yes', 'No', 'Common domain facts'],
            ['P', 'Agent with fixed playbook', 'Yes', 'No', 'Same facts in ordered steps'],
            ['H', 'Hypothesis-driven agent', 'Yes', 'No', 'Graph and action contracts'],
            ['AS', 'Standard agent with scripts', 'Yes', 'Yes', 'Common domain facts'],
            ['HS', 'Full hypothesis-driven agent', 'Yes', 'Validated', 'Graph, contracts, lessons'],
        ],
    },
    {
        'id': 'table-4', 'number': '4', 'section': 'Main', 'page': 6,
        'title': 'Outcome definitions and scoring sources',
        'caption': 'Arrows indicate preferred direction.',
        'headers': ['Metric', 'Operational definition', 'Scoring source'],
        'rows': [
            ['ESR ↑', 'Admissible answer, required findings, valid support, no material invention', 'Frozen evidence rubric'],
            ['CPS ↑', 'Both original and counterfactual pass ESR', 'Paired run outcomes'],
            ['Revision ↑', 'Post-release ESR; report provisional state and direction of update', 'Shared evidence checkpoint'],
            ['Finding precision / recall ↑', 'Correct unique claims / asserted claims; recovered / required facts', 'Atomic claim audit'],
            ['Unsupported claims ↓', 'Unsupported material claims per run; also fraction of all claims', 'Blinded adjudication'],
            ['Calibration ↓', 'Three-class Brier score on evaluable answer labels', 'Recorded probabilities'],
            ['Valid script yield ↑', 'Unique verified findings contributed by validated scripts per run', 'Fixtures and record checks'],
            ['Cost ↓', 'Calls, tokens, latency, CPU seconds, currency cost', 'Execution traces'],
        ],
    },
    {
        'id': 'table-5', 'number': '5', 'section': 'Main', 'page': 6,
        'title': 'Confirmatory hypotheses and contrasts',
        'caption': 'Higher ESR and CPS indicate better performance.',
        'headers': ['Hypothesis', 'Contrast', 'Primary endpoint'],
        'rows': [
            ['H1 Structure aids investigation', 'H versus A', 'V0 ESR'],
            ['H2 Structure aids interpretation', 'H-style versus A-style synthesis on fixed bundles', 'ESR'],
            ['H3 Full method exceeds equal tool access', 'HS versus AS', 'ESR'],
            ['H4 Validation adds value', 'HS versus HS without script validation', 'V0 ESR on script-useful subset'],
        ],
    },
    {
        'id': 'table-6', 'number': '6', 'section': 'Templates', 'page': 8,
        'title': 'Reporting template (core V0 cohort)',
        'caption': 'Populate A, H, AS, and HS for the full V0 cohort; show R and P only on their shared secondary subset, with denominators.',
        'headers': ['Condition', 'ESR ↑', 'CPS ↑', 'Unsupported claims ↓', 'Calls ↓', 'Cost / run ↓'],
        'rows': [
            ['R Fixed retrieval', '—', '—', '—', '—', '—'],
            ['A Standard agent', '—', '—', '—', '—', '—'],
            ['P Fixed playbook', '—', '—', '—', '—', '—'],
            ['H Hypothesis agent', '—', '—', '—', '—', '—'],
            ['AS Agent + scripts', '—', '—', '—', '—', '—'],
            ['HS Full method', '—', '—', '—', '—', '—'],
        ],
    },
    {
        'id': 'table-7', 'number': '7', 'section': 'Templates', 'page': 8,
        'title': 'Intervention results template',
        'caption': 'Core results cover renaming, distractors, missing evidence and delayed evidence. Counterfactual CPS is reported only where defined.',
        'headers': ['Condition', 'Rename pair ↑', 'Distractor pair ↑', 'Counterfact. pair ↑', 'Missing ESR ↑', 'Revision ESR ↑'],
        'rows': [
            ['A Standard agent', '—', '—', '—', '—', '—'],
            ['P Fixed playbook', '—', '—', '—', '—', '—'],
            ['H Hypothesis agent', '—', '—', '—', '—', '—'],
            ['AS Agent + scripts', '—', '—', '—', '—', '—'],
            ['HS Full method', '—', '—', '—', '—', '—'],
        ],
    },
    {
        'id': 'table-8', 'number': '8', 'section': 'Templates', 'page': 9,
        'title': 'Common-evidence interpretation template',
        'caption': 'Each row is a paired comparison on identical observations; collector thoughts and conclusions are removed.',
        'headers': ['Evidence source', 'Standard ESR', 'Structured ESR', 'Paired Δ [95% CI]'],
        'rows': [
            ['Independent fixed collector', '—', '—', '—'],
            ['A-collected bundle', '—', '—', '—'],
            ['HS-collected bundle', '—', '—', '—'],
            ['Oracle decisive bundle', '—', '—', '—'],
        ],
    },
    {
        'id': 'table-9', 'number': '9', 'section': 'Templates', 'page': 9,
        'title': 'Ablation template',
        'caption': 'Match content, available tools, and budget; record actual resource differences.',
        'headers': ['HS variant', 'ESR ↑', 'CPS ↑', 'Revision ↑', 'Cost ↓'],
        'rows': [
            ['Full method', '—', '—', '—', '—'],
            ['Flat memory with same content', '—', '—', '—', '—'],
            ['No pre-action predictions', '—', '—', '—', '—'],
            ['No contradiction check', '—', '—', '—', '—'],
            ['No script validation', '—', '—', '—', '—'],
            ['No experience lessons', '—', '—', '—', '—'],
            ['Fixed procedural lessons', '—', '—', '—', '—'],
            ['Matched-budget reflection baseline', '—', '—', '—', '—'],
        ],
    },
    {
        'id': 'table-10', 'number': '10', 'section': 'Templates', 'page': 10,
        'title': 'Script evaluation template',
        'caption': 'Report conditional script statistics alongside unconditional case-level ESR.',
        'headers': ['Condition', 'Runs using scripts', 'Execution success', 'Validation pass', 'Verified findings/run', 'False findings/run'],
        'rows': [
            ['AS Standard scripts', '—', '—', 'N/A', '—', '—'],
            ['HS without validation', '—', '—', 'N/A', '—', '—'],
            ['HS Full method', '—', '—', '—', '—', '—'],
        ],
    },
    {
        'id': 'table-11', 'number': '11', 'section': 'Templates', 'page': 11,
        'title': 'Investigation graph results template',
        'caption': 'Run both common-evidence and online-construction settings; report them separately.',
        'headers': ['Representation', 'ESR ↑', 'CPS ↑', 'Relation precision ↑', 'Token cost ↓'],
        'rows': [
            ['Chronological evidence ledger', '—', '—', '—', '—'],
            ['Flat list of identical relations', '—', '—', '—', '—'],
            ['Entity and temporal graph', '—', '—', '—', '—'],
            ['Support and contradiction graph', '—', '—', '—', '—'],
            ['Full graph with provenance and gaps', '—', '—', '—', '—'],
        ],
    },
    {
        'id': 'table-12', 'number': '12', 'section': 'Templates', 'page': 12,
        'title': 'Technique comparison and results template',
        'caption': 'All methods use the same backbone and permitted evidence; dashes denote unmeasured outcomes.',
        'headers': ['Technique', 'Controlled intervention', 'ESR ↑', 'CPS ↑', 'Cost ↓'],
        'rows': [
            ['Hypothesis tree', 'At most three branches; evidence-based pruning and backtracking', '—', '—', '—'],
            ['Independent critique', 'Fresh-context reviewer challenges evidence support', '—', '—', '—'],
            ['Retrieval-guided planning', 'Retrieve frozen training lessons by current evidence gap', '—', '—', '—'],
            ['Adaptive replanning', 'Revise the plan after contradiction, failed action, or no progress', '—', '—', '—'],
            ['Independent candidates', 'Three proposals on the same evidence; evidence-based selection', '—', '—', '—'],
            ['Matched self-review', 'Single agent revisits its answer using equivalent budget', '—', '—', '—'],
        ],
    },
    {
        'id': 'appendix-contract', 'number': 'A1', 'section': 'Appendix', 'page': 16,
        'title': 'Investigation-contract fields',
        'caption': 'Required fields for hypothesis-driven actions.',
        'headers': ['Field', 'Required content'],
        'rows': [
            ['Hypotheses', 'IDs, descriptions, unresolved alternatives, and current status'],
            ['Question', 'Specific uncertainty that affects the final answer'],
            ['Predictions', 'Different expected observations under competing explanations'],
            ['Action', 'Tool, parameters, scope, and resource estimate'],
            ['Observation', 'Status, immutable source IDs, content hash, and timestamps'],
            ['Update', 'Supported changes, contradictions, and remaining gaps'],
            ['Script artifact', 'Version, inputs, assumptions, validation outcome, and output IDs'],
            ['Final answer', 'Verdict probabilities, required findings, citations, and limitations'],
        ],
    },
    {
        'id': 'appendix-plan', 'number': 'A2', 'section': 'Appendix', 'page': 17,
        'title': 'Planned study parameters',
        'caption': 'Frozen planning values for dataset allocation and evaluation grid.',
        'headers': ['Field', 'Planned value or required entry'],
        'rows': [
            ['Dataset allocation', 'AIT: 40 train / 40 development / up to 80 test cases across 2 / 2 / 4 whole environments; OTRF and OpTC: up to 24 external cases each.'],
            ['Primary test grid', 'Up to 80 × 5 eligible versions × 4 conditions × 2 backbones × 3 repeats = 9,600 core runs.'],
            ['Backbone identifiers', '[Exact provider/model version and release identifier]'],
            ['Inference settings', '[Temperature, top-p, reasoning effort, context and output caps]'],
            ['Initial run caps', '40 tool calls; 30,000 generated tokens; 20 minutes wall clock'],
            ['Script execution', '120 CPU seconds per call; [memory cap and package lock hash]'],
            ['Evidence policy', '[Snapshot hashes, tool schemas, pagination, truncation rules]'],
            ['Guidance content', '[Common reference, playbook and frozen lesson-set hashes]'],
            ['Evaluation', '[Rubric version, reviewer protocol, metric implementation hash]'],
            ['Randomization', '[Case order, paired run-index scheme, environment seeds]'],
            ['Power decision', '[Development-only simulation, final sample size and rationale]'],
            ['Registration', '[Timestamped protocol URL and deviations log]'],
        ],
    },
    {
        'id': 'appendix-sources', 'number': 'A3', 'section': 'Appendix', 'page': 19,
        'title': 'Data sources and study role',
        'caption': 'Public datasets used for core and transfer experiments.',
        'headers': ['Source', 'Study role', 'Evidence and qualification'],
        'rows': [
            ['AIT LDS V2.1 [16]', 'Core experiments', 'Multi-host logs, simulated normal activity, separate attack labels. Use no-PCAP archives first. CC BY-NC-SA 4.0.'],
            ['OTRF Security Datasets [18]', 'External transfer', 'Windows technique recordings. Admit only questions supported by actual source coverage. MIT at repository level.'],
            ['DARPA OpTC [19]', 'External transfer', 'Structured endpoint provenance and red-team ground truth. Apply documented errata; public-domain release.'],
            ['LANL cyber1 [20]', 'Optional scale study', 'Authentication, process, DNS and flow records. Red-team events are positive annotations, not exhaustive benign labels.'],
            ['Splunk BOTSv3 [21]', 'Optional replication', 'CC0 repository; pre-indexed distribution requires a verified extraction path. Not a core dependency.'],
        ],
    },
    {
        'id': 'appendix-split', 'number': 'A4', 'section': 'Appendix', 'page': 19,
        'title': 'Environment split and case targets',
        'caption': 'Proposed AIT / external partitions.',
        'headers': ['Partition', 'Source environments', 'Target base cases'],
        'rows': [
            ['Training', 'AIT fox and harrison', '40 total; up to 20 each'],
            ['Development', 'AIT russellmitchell and santos', '40 total; up to 20 each'],
            ['Core test', 'AIT shaw, wardbeck, wheeler and wilson', '80 total; up to 20 each'],
            ['External test', 'OTRF and OpTC; no lesson learning', '24 each; distinct source clusters where feasible'],
        ],
    },
    {
        'id': 'appendix-questions', 'number': 'A5', 'section': 'Appendix', 'page': 20,
        'title': 'Candidate questions and admission rules',
        'caption': 'Question families with required evidence linkage.',
        'headers': ['Candidate question', 'Candidate evidence', 'Admission rule'],
        'rows': [
            ['Did a web request lead to server-side execution?', 'Web access/error records plus host audit/process evidence', 'The linking identifiers or timestamps must distinguish execution from a failed or ordinary request.'],
            ['Which identity and host account for remote access?', 'VPN/session records, authentication and host events', 'Identity and session links must be observable; do not infer authorization from success alone.'],
            ['Is unusual DNS activity consistent with data transfer?', 'DNS records plus endpoint activity; optional PCAP', 'Without process or content evidence, limit the conclusion to the observable pattern.'],
            ['Was a privilege change followed by execution?', 'Authentication, audit and process events', 'Require ordered evidence of the change and affected process, not an attack label.'],
        ],
    },
    {
        'id': 'appendix-versions', 'number': 'A6', 'section': 'Appendix', 'page': 21,
        'title': 'Variant construction and validity checks',
        'caption': 'How V0–V5 cases are built and audited.',
        'headers': ['Version', 'Construction', 'Validity check'],
        'rows': [
            ['V0', 'Full permitted case snapshot', 'Mandatory findings have a visible support path.'],
            ['V1', 'Bijective renaming of users, hosts, IPs and non-semantic identifiers across all sources', 'Preserve relations, subnet roles and operationally meaningful values; audit embedded strings.'],
            ['V2', 'Expose additional unrelated same-environment records; target twice the original record count', 'No causal or evidential link to the focal question; unchanged correct findings.'],
            ['V4', 'Hide a decisive source or event set and all redundant routes to the selected mandatory finding', 'Two plausible answers remain consistent with every accessible tool result.'],
            ['V5', 'Expose common incomplete bundle, elicit answer, release fixed decisive evidence', 'Release resolves a pre-specified uncertainty; no fabricated log records.'],
        ],
    },
    {
        'id': 'appendix-experiments', 'number': 'A7', 'section': 'Appendix', 'page': 21,
        'title': 'Experiment schedule and target runs',
        'caption': 'E1–E4 comparisons with maximum planned run counts.',
        'headers': ['Experiment', 'Comparison and outcome', 'Target runs'],
        'rows': [
            ['E1 Core investigation', 'A, H, AS, HS; V0 ESR primary, V1/V2/V4/V5 secondary', '80 × 5 × 4 × 2 × 3 = 9,600 maximum'],
            ['E2 Common evidence', 'A-style vs H-style synthesis; independently collected V0 bundles; ESR', '80 × 2 × 2 × 3 = 960'],
            ['E3 Script validation', 'HS vs HS without validation on 40 script-useful V0 cases; ESR', '240 new runs; reuse 240 matched HS runs from E1'],
            ['E4 External transfer', 'A, H, AS, HS on 24 OTRF + 24 OpTC V0 cases; source-specific ESR', '48 × 4 × 2 × 3 = 1,152'],
            ['Total planned ceiling', 'Excludes pilots, collectors, optional controls and regeneration', '11,952 agent/synthesis runs'],
        ],
    },
]


def main() -> None:
    for t in TABLES:
        t['row_count'] = len(t['rows'])
        t['col_count'] = len(t['headers'])
    payload = {
        'source': SOURCE,
        'paper': 'Beyond Retrieval: Open Dataset Experiments',
        'page_count': 23,
        'table_count': len(TABLES),
        'note': 'Result templates (Tables 6–12) use em dashes for not-yet-populated numerical cells, matching the paper.',
        'tables': TABLES,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'wrote {OUT} ({len(TABLES)} tables)')


if __name__ == '__main__':
    main()
