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
echo target can remain in candidate evidence without becoming a batch member.

Candidate evidence may include a `verification_anchor` derived locally from a fixed safe vocabulary.
Its category, operation, entity class, and source-field label make review prompts more concrete
without copying arbitrary issue terms. Consumers must still treat the anchor as advisory and must
inspect the private source records locally before reaching a conclusion.

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

Schemas use JSON Schema Draft 2020-12. Published `$id` values point to the corresponding files on the
default branch; consumers should vendor a supported schema version when deterministic offline
validation is required. Python wheel installations also include them under `embead/schemas/v1` for
offline access through `importlib.resources`.
