# Beyond Retrieval: experiment scaffold

A dependency-free Python 3.11+ starting implementation for the public-dataset
experiment design. This is research code, not a completed reproduction of the
paper. No benchmark results, downloaded datasets, or live model runs are included.

See [FULL_WORKFLOW.md](FULL_WORKFLOW.md) for the new graph, lesson, sample-data and
integration-validation workflow, including the exact executed/blocked checks.

## Quick start

From this directory:

```bash
python -m pip install -e .
beyond-retrieval demo --output demo-output
python -m unittest discover -s tests -v
```

### Results UI (Tables 6–12)

After runs/scores, the CLI appends rows to `results/ledger.jsonl` and refreshes
`ui/results/` (open `ui/results/index.html` in a browser):

```bash
beyond-retrieval demo --output demo-output
beyond-retrieval report --ledger results/ledger.jsonl --output ui/results
```

`run` and `score` also append to the ledger and refresh the UI unless
`--no-report` is passed. Cost cells use `completion_tokens`; ESR shows
`(pending)` until human adjudication.

Without installing: prefix commands with `PYTHONPATH=src` and replace
`beyond-retrieval` with `python -m beyond_retrieval.cli`.
The deterministic demo inspects two synthetic login records and writes a case,
configuration, trace, rubric and score. Its ESR is intentionally null (pending
review). It does not measure model performance.

## Implemented and remaining work

| Component | Implementation and limit |
|---|---|
| Evidence import | Explicit text/JSONL or JSON-array file; original file SHA256 and line/item offsets. Raw AIT, OTRF and OpTC field retention; no dataset-specific event joins. |
| Shared tools | Read-only search, source listing, record lookup, aggregation, pagination and output caps. |
| A / H / AS / HS | Common runner; H-family requires alternative hypotheses and distinguishing predictions; AS-family enables container scripts; HS gates scripts on a development fixture. |
| Hypothesis graphs | Typed transactional graph, evidence provenance, action/test edges, revision history and structural validation. Semantic claims remain unverified. |
| Lessons | Model proposals from development runs, reviewed frozen bank, deterministic retrieval and same-base-case exclusion. See FULL_WORKFLOW.md. |
| V0/V1/V2/V4 | Mechanical transformations; curator approval of semantics, distractor independence and missing evidence is still required. |
| V5 | Two cumulative evidence views; equal per-stage budgets; provisional answer retained before release. |
| Common-evidence replay | `replay: true` supplies a fixed bundle and disables retrieval/scripts. Curate bundle size to fit both model contexts. |
| R (fixed retrieval) | Implemented as `arm: R` (forces `replay: true`): synthesis over a frozen evidence bundle, no adaptive tools. Requires a curated one-stage case whose full evidence fits the model context. P (playbook) and V3 are still not implemented. |
| Evaluation | Mandatory-value matching, admissible verdict, Brier score when uniquely labelled; ESR requires independent semantic adjudication. |
| Uncertainty | Exact paired-run matching and environment-cluster bootstrap of equal-environment mean differences. No significance claims with few clusters. |
| Scheduling | Stable job manifest only. Cluster execution, retries and resume orchestration remain external. |

## Dataset curation before model runs

The curation builder is now implemented. See [CURATION.md](CURATION.md) for source
manifests, split leakage checks, private rubrics, review gates and variant audits.
Run `beyond-retrieval curate examples/curation/manifest.json --output curated-demo`
then `beyond-retrieval audit-curation curated-demo`. Real dataset labels still
require explicit curator mapping.


Obtain datasets from their official releases and record version, license and source
checksums. No dataset is bundled. Public availability does not imply unrestricted
commercial use. Sources:

- AIT Log Dataset V2.1: https://doi.org/10.5281/zenodo.19483937
- OTRF Security-Datasets: https://github.com/OTRF/Security-Datasets
- OpTC: https://github.com/FiveDirections/OpTC-data

### Transfer benchmarks (hypothesis graphs / scripts)

Staged under `datasets/` with purposes recorded in
`datasets/transfer_benchmarks.json`:

| Benchmark | Purpose | Local path |
|---|---|---|
| [DiscoveryBench](https://github.com/allenai/discoverybench) | Test whether hypothesis graphs and validated scripts improve discovery from supplied datasets. | `datasets/ingested/discoverybench/` |
| [DiscoveryWorld](https://github.com/allenai/discoveryworld) | Test whether those methods improve selection of informative experiments. | `datasets/ingested/discoveryworld/` |
| [ScienceAgentBench](https://github.com/OSU-NLP-Group/ScienceAgentBench) | Test transfer to practical scientific coding tasks. | `datasets/ingested/scienceagentbench/` |

Re-stage with `python scripts/add_transfer_benchmarks.py`. ScienceAgentBench full
gold/eval programs remain SharePoint-gated (`benchmark_verified.zip`); the HF
annotation sheet (agent inputs) is stored locally. DiscoveryWorld baseline/human
trajectory dumps remain on the upstream Google Drive links.

Proposed AIT split: train `fox,harrison`; development
`russellmitchell,santos`; test `shaw,wardbeck,wheeler,wilson`. Case counts are targets,
not audited availability. Resolve scenario overlap and align labels using original
line numbers before filtering; timestamps are not inferred from arbitrary raw text.
Audit OpTC release errata and process identities before joins. OTRF technique captures
must not automatically be treated as complete incident narratives.

```bash
beyond-retrieval normalize telemetry.log curated/events.jsonl \
  --dataset ait --environment shaw --source auth
```

Create `curated/case.json` using the demo schema. Set `evidence_hash` to
`beyond_retrieval.data.digest(load_events('curated/events.jsonl'))`, not the raw file
hash. This hash commits to canonical content and order. Cases may specify
`base_case_id`, `variant`, `public_context` and `stages` (lists of accessible record
IDs). Every final citation is checked against its stage's accessible IDs; citation
checking does not certify that the model inspected or correctly interpreted a record.
Only question and public_context are passed to the model, never rubric metadata.
Audit these public fields for accidental answers. The filename check in the adapter
is only a guardrail: curators remain responsible for excluding all labels.

Keep rubrics outside the case evidence directory. Example rubric:

```json
{"mandatory":{"failed_login":"bob"},
 "admissible_verdicts":["insufficient_evidence"],
 "unique_label":"insufficient_evidence"}
```

For ambiguity, omit `unique_label`; calibration is then not computed. Rubrics for
V4/V5 stage 0 describe what evidence justifies, not omniscient incident truth.
The CLI scores the final stage; score provisional stages separately via `score`
with a one-stage run and the corresponding incomplete-evidence rubric.

## Variants

```bash
beyond-retrieval variant curated/events.jsonl curated/renamed.jsonl \
  --variant V1 --spec examples/rename.json
```

V1 uses a single-pass entity mapping on raw text and structured values, preserving
record IDs and origin. Check collisions with existing entity names, keys that encode
entities, paths and command semantics manually. V2 accepts `--extra distractors.jsonl`
and enforces same environment and unique IDs. V4 uses `{"hide_ids":[...]}`; verify
all routes to the mandatory conclusion were removed. Store each variant's spec,
source checksums and curator approval next to its case; recompute evidence_hash.
Do not infer valid variants simply because transformation code succeeds.

## Live models and scripts

Copy `examples/config.json`; set a real model revision and chat-completions endpoint.
The adapter sends JSON-mode requests with temperature zero, max_tokens and an optional
bearer token from `EXPERIMENT_API_KEY`. Exact support varies across servers. Local
llama.cpp provides an OpenAI-compatible interface:
https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
No endpoint has been tested here. Keep secrets out of config and traces.

```bash
beyond-retrieval run --case curated/case.json --config examples/config.json \
  --output results/run-001.json
```

The runner refuses to overwrite output. Record repeat and frozen model revision in
each config. Temperature-zero repeats may be identical; report that fact. Provider
usage must include completion_tokens, including any provider-accounted reasoning
usage. Confirm semantics and token caps for each backbone. Context truncation is
not automatic; curate a common context policy. Calls and generated tokens are
budgeted, not input tokens or money. Malformed actions consume a bounded model step;
failed tool attempts consume a call. Two-stage runs split budgets equally. Wall
limits are checked around calls; container teardown may exceed the nominal deadline.
Provider errors are logged; inspect traces before scoring. Capture environment,
package versions, prompts, source revision and model revision alongside each study.

AS/HS require Docker and an image pinned as `python@sha256:<actual-image-digest>`;
no host Python fallback exists. The image must contain Python. Containers have no
network, read-only mounts/root filesystem, dropped capabilities and resource caps.
This configuration is for controlled experiments, not a hardened multi-tenant
sandbox. Docker integration has not been executed in this delivery.

HS also requires `--fixture examples/full/script-fixtures.json` with a fixtures
array of rows and exact expected outputs. Every fixture executes before current
evidence; all executions count against tool budget. Freeze a meaningful suite
before paper-scale use. Tests only establish behavior on the covered fixtures. Never use test-case
labels as fixtures. AS and HS-no-validation execute without the gate. Script results
are untrusted claims and still require review. Typed graphs and reviewed lessons are now implemented; scientific validation of
the complete method still requires real datasets and live-model trials.

## Scoring and analysis

```bash
beyond-retrieval score --run results/run-001.json --rubric private/rubric.json \
  --output results/score-001.json
```

Blind human reviewers to arm/model identity using answer + evidence packets prepared
outside this prototype. After independent review and adjudication, pass `--review`
with `reviewer_id`, `adjudicated: true`, `all_claims_supported`,
`mandatory_findings_supported`, and `no_material_unsupported_claims`. Each is a
boolean except reviewer_id. Maintain a signed mapping from reviews to exact output
hashes: this prototype does not implement review authentication. Freeze criteria
and adjudication procedures before inspecting arm differences. Incomplete runs
receive ESR=0. Without review, completed runs receive ESR=null.

For paired analysis, build a JSON array of rows with `arm`, `environment`,
`base_case_id`, `variant`, `model`, `repeat`, and adjudicated `esr`:

```bash
beyond-retrieval compare results/scores.json --left A --right HS \
  --output results/comparison.json
beyond-retrieval plan examples/manifest.json --output jobs.json
```

Use balanced case/variant/model/repeat cells. The comparison rejects missing pairs;
report failures explicitly rather than deleting them. Environment means weight all
paired runs within each environment equally, then environments equally. With four
AIT test environments, bootstrap intervals are descriptive and unstable. Report
per-environment/per-variant outcomes, costs and provisional-to-final changes as well.
The plan command enumerates already curated case paths; it does not create cases or
run a benchmark. Start with a small development pilot; freeze protocol before test.

## Validation performed

42 unit/integration tests cover graphs, lessons, mock HTTP transport, curation
integrity and split/label separation, plus source offsets, provenance-preserving renaming,
withheld IDs, V4 removal, distractor boundaries, label isolation, content hashes,
contracts, script disabling, call budgets, pending human review, staged release,
missing statistical pairs and invalid probabilities. A synthetic CLI demo was run.
Real dataset validity, live model APIs, Docker execution, semantic scoring and
scientific performance have not been validated.
