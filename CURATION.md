# Dataset curation workflow

This module turns explicitly selected local telemetry into versioned case bundles.
It does not download datasets or infer incident labels. No real benchmark has been
curated in this delivery. The runnable example is synthetic and intentionally draft.

## Run the example

```bash
beyond-retrieval curate examples/curation/manifest.json --output curated-demo
beyond-retrieval audit-curation curated-demo
```

`curated-demo/public/<case-id>/` contains case.json and events.jsonl, suitable for
the runner. `curated-demo/private/` contains evaluation rubrics, review records,
source inventory and integrity manifest. Keep private/ on the evaluator side;
never mount it into model/script containers. Directory permissions are restrictive
on POSIX but are not a substitute for access control on Windows or shared storage.

The example reports one draft case. Complete the checks in the input manifest,
with a real reviewer identity, then build to a new output directory. A draft case
cannot run through the agent runner. Approval records document human assertions;
software cannot certify their truth. Do not approve real cases based only on a
successful mechanical build.

## Populate source records

For each explicitly chosen telemetry file, provide:

| Field | Meaning |
|---|---|
| id | Unique safe name used by case references |
| path | Local file, relative to the input manifest or absolute |
| dataset | ait, otrf, optc, or generic |
| environment | Stable environment identity; never reuse aliases to bypass split checks |
| version | Exact downloaded release or repository commit |
| license | License recorded from that release |
| url | Official source provenance URL |
| sha256 | SHA256 of the original file bytes |
| json_array | true for a JSON array; omit for raw text or JSONL |

The builder preserves original line numbers (including gaps from blank lines) or
one-based array item indices. It verifies the source checksum before importing.
It loads explicit source files into memory; shard very large datasets into auditable
source files before curation and preserve a separate extraction manifest that maps
shards back to release files. Streaming extraction and native label parsers are not
implemented.

For AIT, map the release's label references to original log lines first. For OTRF,
review technique metadata and distinguish recorded behavior from inferred intent.
For OpTC, reconcile release-specific process identity/time fields and errata before
mapping labels. These mappings must be supplied by a curator; selecting a dataset
name does not interpret its ground-truth format. Metadata licenses are recorded,
not automatically verified or enforced.

## Define cases and private rubrics

Each case names `id`, `base_case_id`, `split`, `scenario_group`, `variant`, `question`
and `evidence`. References use `[{"source":"auth","indices":[1,2]}]`. They always
refer to original source positions, never positions after filtering. Supply a
`public_context` object only if its content is intended for the agent.

The rubric contains `mandatory`, `admissible_verdicts` and a `support` mapping with
one source-reference list per mandatory finding. An optional `unique_label` is
allowed only for one admissible verdict. Generated private rubrics replace support
references with canonical event IDs. For insufficient-evidence cases, mandatory
findings should describe observable facts; do not require hidden incident facts.
Empty mandatory findings are allowed but should be reviewed for meaningful scoring.

The builder rejects case/base/scenario split conflicts, cross-split environments,
and reused original source records across splits. The frozen AIT environment split
is enforced in code. These are necessary checks, not a complete semantic duplicate
detector: use common scenario_group names for related recordings and manually audit
near-duplicates, attack templates and scenario families. Split names are train,
dev, test and external. OTRF/OpTC can use external. All variants of a base case must
remain in its split.

## Variant curation

| Variant | Manifest addition | Required human check |
|---|---|---|
| V0 | None | Labels and mandatory claims have valid support |
| V1 | `transform: {"mapping":{"host-a":"host-b"}}` | Renaming preserves command semantics, entity consistency and question/rubric alignment |
| V2 | `distractors` source references | Extra records are unrelated and from the same environment |
| V4 | `hide` source references | All support routes to the removed conclusion are absent; remaining task is well-defined |
| V5 | `initial_evidence` and `provisional_rubric` | Same release policy across arms; both epistemic rubrics correct |

V1 does not rewrite question or rubric values automatically: supply the already
renamed question/context/rubric. Provenance and IDs are kept stable. V4 requires a
rubric for what remaining evidence justifies; hidden support is rejected. V5
requires a nonempty strict subset initially and checks provisional rubric support
against that subset. Final rubric support is checked against the full bundle.
V3 is rejected because it requires new recordings.

## Review and integrity

All cases require reviewer_id plus true values for telemetry_only, label_alignment,
public_prompt_no_answers, scenario_independence and rubric_support.
Additional keys are:

- V1: renaming_preserves_semantics
- V2: distractors_unrelated
- V4: all_support_routes_removed, ambiguity_reviewed
- V5: release_schedule_shared, stage_rubrics_reviewed

Missing/false checks produce draft cases. These are curation reviews, distinct from
blind post-run answer adjudication. Private files include hashes of public cases,
evidence and review/rubric content. `audit-curation` detects post-build changes;
these are checksums, not signatures against a malicious editor. Protect or sign the
private manifest in the study's archival workflow. Re-curate rather than modifying
generated cases. The runner checks its evidence hash and draft status; run the
full curation audit before scheduling a batch because the runner does not receive
the private integrity manifest. Legacy cases without curation metadata remain
compatible and are not implicitly certified.

## Run a reviewed case

```bash
beyond-retrieval audit-curation curated-reviewed
beyond-retrieval run --case curated-reviewed/public/CASE_ID/case.json \
  --config examples/config.json --output results/run-001.json
```

Private case files wrap the scorer-compatible rubric in `rubric` (and optionally
`provisional_rubric`). Export the desired object into a separate evaluator file
before passing it to `score --rubric`; do not pass the entire private case object.
Feed public case paths into the existing plan manifest. No model calls, dataset
network downloads or real-case approvals are performed by the curation commands.
