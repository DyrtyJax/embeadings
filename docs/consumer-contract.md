# Consumer compatibility and capability contract

emBEADings artifacts are read-only, advisory evidence. The JSON Schemas in
[`schemas/v1`](../schemas/v1/) describe the stable machine-readable envelope for the `neighbors`,
`batch`, and `sweep` report types. The files in [`examples`](../examples/) are synthetic and contain
no tracker data.

## Version negotiation

`schema_version` is an integer compatibility boundary, independent of the emBEADings package
version.

- A version 1 producer may add optional fields anywhere in an artifact without changing
  `schema_version`.
- A version 1 consumer must ignore fields it does not understand and must not infer lifecycle truth
  from them.
- Existing required fields, their types, and the safety policy constants will not change within
  version 1.
- Removing or renaming a required field, changing its meaning or type, or weakening a safety
  invariant requires a new schema version.
- A consumer must reject an unsupported `schema_version`; silently treating it as a known version is
  unsafe.
- `report_type` selects the corresponding schema. Unknown report types are unsupported even when
  their schema version is familiar.

The schemas deliberately allow additive fields. Evidence-specific explanations, structural ranking,
batch diagnostics, and performance telemetry can therefore evolve without breaking version 1
consumers.

Current sweep producers include additive `no_signal` and `excluded` summaries. Candidate-focused
batch manifests contain only active issues participating in accepted review signals; a completed
echo target can remain in candidate evidence without becoming a batch member. `kind` distinguishes
a connected component from a `singleton-envelope`; consumers must treat each envelope `review_unit`
as an independent one-issue review, not infer relationships between envelope members. The sweep's
`batch_diagnostics` records deterministic fragmentation and cross-artifact candidate-edge counts.

Candidate evidence includes a `verification_anchor` derived locally through deterministic,
field-aware extraction into a finite safe output vocabulary. `action`/`operation`,
`entity`/`entity_class`, `outcome_or_invariant`/`category`, and `source_field` identify the normalized
contract to inspect without copying arbitrary issue terms. The paired names preserve version 1
consumer compatibility while making the structured meaning explicit. `confidence` is `high` only
when the selected field supplies both action and entity and the outcome category is corroborated;
`generic_fallback` identifies anchors that could not safely resolve both. The report-level
`anchor_metrics` summarizes confidence counts and fallback rate without examining or repeating
private content. Transferred ownership requires ownership evidence in both records. Consumers must
still treat every anchor as advisory and inspect the private source records locally before reaching
a conclusion.

Sweep `parameters.candidate_policy` also records independent `dependency`, `echo`, and `overlap`
lane caps and metrics. Consumers should use each lane's `qualified`, `admitted`, and drop counts when
explaining queue volume. `baseline_protected` identifies default-threshold candidates selected first
during a lower-threshold sensitivity run; it is evidence about ranking stability, not tracker truth.
Typed dependencies have a separate per-issue allowance, so semantic candidates cannot consume their
capacity. Qualified typed edges omitted by a per-issue, lane, or run cap remain available in
`capped_typed_dependencies` as compact structural context; these entries are not review candidates.
`reciprocal_diagnostics` counts substantive reciprocal admissions and generic-vocabulary omissions
without exposing issue text. `cap_replacements` explains the exceptional case where a threshold
change alters a bounded winner; consumers should name the governing cap instead of presenting that
candidate as newly semantically qualified.

Snapshot metadata identifies `live-beads-cli` as the authoritative acquisition source and records
the live issue count. When `.beads/issues.jsonl` is discoverable, emBEADings counts its records
without copying their contents; a count mismatch is reported through `source_warnings` and the
sweep warning list. Consumers must not substitute a stale export for the live snapshot.

Equal issue counts do not prove that an export is current. The producer also records canonical
SHA-256 state digests over issue ID, normalized status, issue type, priority, typed dependencies,
and update marker—never titles or body text. RFC 3339 update markers are converted to UTC and
rounded to whole seconds, matching the supported Beads 1.0.x JSONL-to-Dolt timestamp round trip.
Different live/export digests produce a non-content warning even when record counts match.
`source_divergence_reasons` supplies only controlled metadata categories such as `status`,
`dependency_structure`, or `record_count`; it never identifies records or includes issue text.

## Capability handshake

An optional dispatcher or UI should exchange a capability document before consuming artifacts. The
version 1 shape is defined by
[`capabilities.schema.json`](../schemas/v1/capabilities.schema.json) and demonstrated by the
[synthetic example](../examples/capabilities.json).

The handshake is transport-neutral: it may be a file, subprocess message, HTTP response, or in-memory
object. Core emBEADings does not launch a dispatcher or grant it tracker access.

```json
{
  "document_type": "embeadings-capabilities",
  "protocol_version": 1,
  "role": "consumer",
  "schema_versions": [1],
  "report_types": ["neighbors", "batch", "sweep"],
  "capabilities": ["additive-fields", "advisory-evidence", "read-only-review"],
  "required_capabilities": ["read-only-review"]
}
```

Negotiation succeeds when:

1. both sides support the same `protocol_version`;
2. they share at least one schema version and report type; and
3. every `required_capabilities` entry from either side appears in the other side's `capabilities`.

The peers select the highest shared schema version and restrict exchange to shared report types. They
must refuse the integration when any requirement is unmet. Capability names are additive strings;
unknown optional capabilities can be ignored.

The version 1 producer capabilities are:

- `additive-fields`: artifacts may contain fields newer consumers have not seen;
- `advisory-evidence`: semantic scores and explanations are evidence, not tracker truth;
- `read-only-review`: artifacts prohibit tracker mutation and batch manifests also prohibit
  implementation.

## Consumer requirements

Before acting on an artifact, a consumer must:

1. select and validate the schema using the exact pair of `schema_version` and `report_type`;
2. enforce the policy constants, especially `read_only: true` and
   `tracker_mutation_allowed: false`;
3. treat issue text, identifiers, paths, and evidence as potentially private;
4. avoid uploading artifact content unless the operator explicitly configured that behavior;
5. preserve candidate scores, structural context, counterevidence, and verification prompts without
   promoting them to conclusions; and
6. fail visibly when validation or capability negotiation fails.

Consumers may filter, visualize, or route valid artifacts. They must not reinterpret a similarity
score as a Beads dependency, status transition, duplicate decision, or authorization to edit source.

## Schema locations

| Report type | Schema | Example |
| --- | --- | --- |
| `neighbors` | [`neighbors.schema.json`](../schemas/v1/neighbors.schema.json) | [`neighbors.json`](../examples/neighbors.json) |
| `batch` | [`batch.schema.json`](../schemas/v1/batch.schema.json) | [`batch.json`](../examples/batch.json) |
| `sweep` | [`sweep.schema.json`](../schemas/v1/sweep.schema.json) | [`sweep.json`](../examples/sweep.json) |
| Incremental checkpoint | [`checkpoint.schema.json`](../schemas/v1/checkpoint.schema.json) | [`checkpoint.json`](../examples/checkpoint.json) |

Schemas use JSON Schema Draft 2020-12. Published `$id` values point to the corresponding files on the
default branch; consumers should vendor a supported schema version when deterministic offline
validation is required. Python wheel installations also include them under `embead/schemas/v1` for
offline access through `importlib.resources`.

## Incremental sweep scope

Sweep filters include an `incremental_scope` summary. `mode` is `full`, `changed-since`, or
`checkpoint`; its counts distinguish changed active records from unchanged exclusions, missing
timestamps, and records deleted since a checkpoint. An incremental candidate always touches at
least one changed active record. Its other endpoint can be unchanged context or completed work.

Checkpoints are separate portable JSON artifacts, not tracker mutations or part of the report
schema. Version 1 contains only workspace identity, creation time, issue IDs, normalized update
timestamps, and SHA-256 record fingerprints. Consumers must reject unsupported versions,
future-created checkpoints, invalid timestamps, and workspace mismatches. Issue text is never stored
in the checkpoint.
