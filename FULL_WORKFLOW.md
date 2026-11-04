# Graphs, learned lessons, curated samples, and integration validation

Version 0.2 adds executable typed graphs, action-to-hypothesis links, graph revision
history, lesson proposal/review/freeze/retrieval, five curated synthetic variants,
and a validation harness. It remains research software, not a validated reproduction
of the paper. No real-model performance result is included.

## Delivered verification

| Check | Result in this environment |
|---|---|
| 42 unit/integration tests | Passed |
| Five synthetic curated variants (V0, V1, V2, V4, V5) | Built and audited |
| Graph-bearing scripted investigation | Completed |
| Lesson proposal, freeze, exclusion and retrieval | Passed with scripted fixtures |
| Model adapter HTTP request/response | Passed against a local mock server |
| Docker execution and isolation probes | Blocked: Docker executable absent |
| Live model inference | Blocked: no endpoint/model configuration supplied |

`examples/full/validation-report.json` records the checks actually performed.
Synthetic fixtures are fictional authentication records, released here as CC0.
The supplied graph and lesson proposals are deterministic authored examples, not
scientific discoveries by a live model. Approval metadata for these fictional
fixtures is illustrative and does not substitute for independent benchmark review.

## Start

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
beyond-retrieval audit-curation examples/full/curated
python -m beyond_retrieval.workflows sample-run \
  --case examples/full/sample-case.json --output my-graph-run.json
```

Inspect `examples/full/hypothesis-graph.json`, `graph-run.json`, and the optional
Mermaid file `hypothesis-graph.mmd`. The JSON graph includes hypotheses,
observations, tool action nodes, evidence provenance and labelled links.
The Mermaid file is a compact explanatory view, not the complete action history.
The existing curate command handles local AIT/OTRF/OpTC telemetry as documented in
CURATION.md; native label interpretation remains a curator task.

## Graph protocol

H, HS and HS-no-validation now require at least two typed hypotheses. Each tool
or script action has a contract with hypothesis_ids, question, hypotheses and one
prediction per referenced ID. The runner automatically records the action and
its tests edges. Agents send graph_update on any step; the final action may update
hypothesis statuses and observations. Nodes have id, type, text, status, evidence_ids.

| Relationship | Allowed source → target |
|---|---|
| supports / contradicts | observation → hypothesis |
| tests | action → hypothesis |
| derived_from | conclusion → observation |
| supersedes | same type → same type; acyclic |

Observation and conclusion nodes need evidence already exposed by tool results,
script citations, or the fixed replay bundle. A supported/refuted hypothesis needs
the corresponding evidence edge. Updates commit transactionally; invalid updates
leave the graph unchanged. Both supporting and contradicting evidence may remain
in the graph. Status and edges are agent assertions: structural validity is not
semantic entailment. All answer citations now also require previously observed IDs.
Graph histories record patches, stage indices and state hashes. Histories preserve
prior versions; text/status may be revised, but node type cannot change.

No probabilities are automatically inferred from graph topology. Semantic validity,
alternative adequacy, whether predictions truly distinguish hypotheses, and the
final answer still require independent evaluation.

## Learned lesson lifecycle

During a development run, the model may emit lesson_candidates with trigger,
procedure and limitation. Proposal extraction is deterministic; induction is the
model's job. Test/external runs cannot be used in propose-lessons. Record the true
source split from the private curation manifest; the caller-supplied split is not
authenticated by this CLI.

```bash
python -m beyond_retrieval.workflows propose-lessons development-run.json \
  --split dev --output candidates.json
python -m beyond_retrieval.workflows freeze-lessons candidates.json reviews.json \
  --output frozen-lessons.json
```

Reviews map candidate IDs to reviewer_id, approved, no_case_answers and generalizable.
The three checks must be true. Review procedures for leaked answers/entity names
and validity must be followed by a person. The bank stores source run hashes,
case/base-case IDs, reviews and a content hash. It is immutable during run(); no test
run writes lessons back. HS/HS-no-validation retrieve up to three procedures using
deterministic trigger-token overlap. A/H/AS receive none. Same-base-case lessons are
excluded; curators must also prevent broader scenario-family contamination.

```bash
beyond-retrieval run --case curated/public/CASE_ID/case.json \
  --config examples/config.json --lessons frozen-lessons.json \
  --output results/run.json
```

Set the config arm to HS to enable lesson use. Always report lesson_bank_hash and
whether any lessons were retrieved. Freeze the same bank for every comparable run.
For a lesson ablation, compare HS with and without --lessons under the same graph,
script and model settings. These experimental settings must be preregistered.

## Script validation fixtures

`examples/full/count_failed_logins.py` reads the mounted evidence and returns counts
plus provenance IDs. `script-fixtures.json` includes empty, positive and negative
fixtures. HS executes every fixture and requires exact expected JSON equality
before current evidence execution. AS and HS-no-validation omit this gate.
Failed tests stop that script invocation. Every fixture execution consumes a tool
call; current evidence execution also consumes a call. Each execution has a CPU
cap and the remaining stage wall-time bound. Exact fixtures test only their covered
behavior; they are not a general correctness guarantee.

Generated programs execute only through Docker. The code never falls back to host
execution. The controlled-experiment sandbox disables networking, uses a non-root
UID, read-only root and evidence mounts, and resource caps. It is not asserted to
be hardened for multi-tenant execution.

## Actual Docker check on your machine

Docker must be installed and its daemon running. Obtain an image with Python,
resolve its real repository digest, and set IMAGE to that digest-pinned reference.
The harness does not choose or download an arbitrary model or substitute a fake
image digest.

```bash
export IMAGE='python@sha256:REPLACE_WITH_REAL_64_HEX_DIGEST'
python -m beyond_retrieval.workflows validate \
  --case examples/full/sample-case.json --image "$IMAGE" \
  --output docker-validation.json
```

The harness compares the sample result and checks the container UID, isolated
network namespace and write failures on evidence/root mounts. Missing dependencies
are blocked; runtime failures are failed; only executed successful probes are passed.
The Docker check covers the known sample script and listed isolation properties,
not every possible generated program or a sandbox security certification.

## Actual live-model check

Start a compatible chat-completions server or supply an authorized hosted endpoint.
Copy examples/config.json and set endpoint and exact model ID/revision. An API key,
when required, is read from EXPERIMENT_API_KEY or the configured key_env. Do not put
keys in JSON files. Confirm that your server supports response_format=json_object,
max_tokens and completion_tokens usage. A supplied endpoint receives sample evidence
and prompts, and may incur provider charges.

```bash
python -m beyond_retrieval.workflows validate \
  --case examples/full/sample-case.json --config my-model.json \
  --output live-model-validation.json
```

Start with arm A; then use arm H to exercise graph production. For the full HS path,
set docker_image in the model configuration to the same actual digest and use:

```bash
python -m beyond_retrieval.workflows validate \
  --case examples/full/sample-case.json --config my-hs-model.json \
  --image "$IMAGE" --fixture examples/full/script-fixtures.json \
  --lessons examples/full/lessons.json --output full-validation.json
```

The example lesson source case equals sample-case.json, so retrieval deliberately
excludes it there. Use a distinct held-out case for lesson-transfer validation,
and retain meaningful scenario independence. A completed live run means its
protocol and citations passed structural checks; it is not a passing semantic
benchmark score. Review traces to confirm which tools/scripts/lessons were actually
used. Separately executed Docker probes do not imply the live agent selected a script.

## Data preparation and publication

Use `examples/full/manifest.json` as a complete curation example. Its five variants
share a base case and split. V4 removes the success event and adapts its rubric;
V5 releases it only in stage two with separate provisional/final rubrics. Provenance,
source checksums and review metadata are preserved. Keep private/ away from models.

Real datasets are not bundled. The code accepts explicit local raw/JSONL/JSON-array
sources and original-index mappings; large-scale extraction, dataset-native label
parsers and semantic scenario review are not automated. Do not claim the synthetic
examples are AIT, OTRF or OpTC records. Before reporting paper results, curate real
cases, freeze prompts/model versions/lessons, validate the actual serving backend
and Docker environment, and complete blind answer adjudication.
