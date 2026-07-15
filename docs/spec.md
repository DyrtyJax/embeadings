# Product and technical specification

## 1. Summary

emBEADings is a standalone, read-only companion CLI for Beads. It incrementally embeds issue
text, retrieves semantically related records, identifies active work that resembles completed work,
and partitions a review population into small disposable neighborhoods suitable for humans or
read-only reviewer agents.

The output is evidence-discovery material, not tracker truth. Similarity must never directly close,
defer, reprioritize, relabel, or rewrite an issue.

## 2. Problem

Dependency graphs encode explicit ordering and blocking relationships. They do not reliably reveal:

- parallel issues that became stale after the same architectural change;
- active records whose outcomes may already have shipped elsewhere;
- deferred work adjacent to an active implementation boundary;
- duplicate or overlapping scope written with different vocabulary;
- a review population that is too large for one agent context.

Keyword search helps only when authors use the same words. Durable semantic labels create another
taxonomy that must itself be maintained. The tool should instead compute local, disposable semantic
relationships from current issue text.

## 3. Goals

1. Read the live Beads tracker through supported machine-readable CLI interfaces.
2. Embed new or changed records incrementally using a content-addressed cache.
3. Return nearest active and completed neighbors for an issue.
4. Surface high-similarity active/completed pairs as review candidates.
5. Produce deterministic, balanced review batches with a configurable target size.
6. Emit stable JSON for tools and concise Markdown for people and agents.
7. Support non-blocking background runs with explicit queued/running/complete/failed state.
8. Keep all models, vectors, logs, and reports out of the analyzed repository by default.
9. Make privacy, offline operation, and non-mutation testable invariants.

## 4. Non-goals

- Replacing Beads search, dependencies, readiness, labels, or lifecycle.
- Persisting clusters or semantic labels into Beads.
- Automatically applying review findings.
- Acting as an issue editor, dashboard, kanban board, or project-management system.
- Hosting a daemon, vector database service, or general-purpose memory layer.
- Requiring a particular coding-agent runtime.
- Sending issue content to a hosted embedding API by default.
- Reading `.beads/issues.jsonl` as tracker truth.

## 5. User stories

### Maintainer

As a maintainer, I can run a weekly sweep and receive small related batches so reviewers examine
parallel stale work without interrupting normal development.

### Reviewer

As a reviewer, I receive issue IDs, current metadata, semantic neighbors, and a bounded evidence
rubric. I can inspect source control and project documentation, but the review process cannot mutate
the tracker.

### Tool author

As a tool author, I can consume versioned JSON manifests and supply an optional dispatcher without
depending on internal embedding implementation details.

## 6. CLI contract

### `neighbors`

```bash
embead neighbors ISSUE_ID [--limit N] [--include-closed]
```

Returns the nearest records with similarity scores and structural context. Human output must label
scores as advisory. JSON output includes the embedding model and index generation.

### `batch`

```bash
embead batch [FILTERS] [--size 9] [--output PATH] [--format json|markdown|both]
```

Builds deterministic, balanced semantic neighborhoods from a candidate population. Filters select
the population structurally before embeddings are applied. The first release should support status,
priority, label, parent, ready, and explicit issue-ID inputs by translating them to supported Beads
CLI operations.

### `sweep`

```bash
embead sweep [FILTERS] [--size 9] [--async]
```

Generates an analysis report plus one manifest per batch. `--async` returns a run ID immediately and
writes status transitions atomically.

### `status`

```bash
embead status RUN_ID [--json]
```

Returns `queued`, `running`, `complete`, or `failed`, timestamps, output locations, and a bounded error
message when failed.

## 7. Data acquisition

The default adapter invokes the installed `bd` binary with read-only and JSON flags. It must:

- discover the workspace using supported Beads context commands;
- request all fields needed for canonical text, lifecycle, parentage, labels, and dependencies;
- capture the Beads version and workspace identity in report metadata;
- fail closed if JSON is malformed or the installed version lacks required read-only behavior;
- never import, export, sync, update, create, close, reopen, label, or modify dependencies.

The core consumes an internal `IssueRecord` schema so future adapters can be added without coupling
the semantic algorithms to one Beads output version.

## 8. Canonical semantic text

The initial canonical representation should include:

- title, with modest extra weight;
- current description;
- acceptance criteria;
- design/current notes when present.

Identifiers, timestamps, actors, comments, audit history, and labels should not be embedded by
default. They remain available as structural/report metadata. Very long fields are truncated with a
documented, deterministic policy so historical notes cannot overwhelm current intent.

The content hash includes:

```text
schema version + canonicalization version + model ID + model revision + canonical text
```

Any change to these inputs invalidates only affected vectors.

## 9. Embedding provider

The provider interface accepts a batch of strings and returns normalized, fixed-dimension vectors
plus model metadata.

The default release should use a compact local CPU model with a pinned revision and a permissive
license. Hosted providers may be added behind explicit configuration and an unavoidable warning that
issue content will leave the machine.

The package manager installs Python dependencies. The program must not create a nested virtual
environment or run a package installer at runtime.

## 10. Cache and state

Use platform-standard user directories:

- cache: model artifacts and content-addressed vectors;
- state: run status, logs, manifests, and reports;
- config: optional user-level provider and output preferences.

Workspace state is namespaced by a stable hash of the canonical workspace identity, not its display
name. No model or vector file is written inside the analyzed repository unless the user explicitly
chooses an output path.

Cache writes must be atomic. Cross-process locking must work on macOS, Linux, and Windows; a
POSIX-only lock is insufficient. Corrupt, non-finite, wrong-dimension, or wrong-model vectors are
discarded and recomputed.

## 11. Similarity analysis

### Neighbors

Use cosine similarity over normalized vectors. Stable tie-breaking uses issue ID. Thresholds are
configuration, not universal truth, and every report records the effective values.

### Completed-work echoes

An active record whose closest completed neighbor exceeds a configured threshold is a review
candidate. The report says “verify against current project state,” never “close.”

### Deferred-work proximity

Semantic proximity alone is insufficient to recommend reconsidering deferred work. A candidate must
also have structural support, such as a shared parent, explicit dependency/relation, or direct textual
cross-reference. Explicit later-phase or trigger language is surfaced to reviewers as counterevidence.

### Duplicate candidates

High similarity may indicate duplication, shared context, or a broad parent/child relationship. The
tool reports candidates and structural differences; it does not merge them.

### Candidate ranking and volume

Default thresholds provide a conservative high-signal baseline. Lower-scoring pairs may enter the
review queue only when corroborated by structural evidence such as shared parentage, an explicit
dependency/relation, or reciprocal-neighbor rank. Reports record why the exception applied.

Candidate volume must be bounded through a deterministic per-issue cap or equivalent global budget.
Lowering a global threshold without a volume control is not an acceptable substitute for ranking.
The synchronous CLI defaults to a `0.08` exception margin, reciprocal rank `5`, three candidates per
issue, and 250 candidates per run. Candidates are assigned to typed-dependency, completed-work echo,
and overlap lanes with independent budgets. Typed dependencies are admitted before semantic lanes;
within the overlap lane, reciprocal exceptions rank behind stronger semantic signals.
Direct parent/child structure is reported as counterevidence and does not enable a below-threshold
exception on its own.

Reciprocal rank is corroboration, not sufficient evidence by itself. A below-threshold reciprocal
pair must also have corpus-discriminative, field-aligned local evidence: a rare title token aligned
with the other record (including CamelCase entities), or a rare multi-token phrase in the same
substantive field. A single long-form token outside a title is intentionally
insufficient. When either record has no substantive body, a shared non-function title token provides
a narrow sparse-record fallback. Frequency is derived deterministically from the local snapshot.
Reports expose only bounded evidence categories and counts, never matched terms or source text.

For recurring maintenance, `--weekly-review-budget N` is an opinionated hard total budget layered on
the existing lane and per-issue allowances. It selects typed dependencies first, high-confidence
completed-work echoes second, and possible overlaps third. The budget is applied after incremental
eligibility filtering, so unchanged records remain context without consuming the queue. Sweep reports
record the effective limit, admitted total, deterministic priority policy, and compact per-lane counts
for candidates omitted by the total budget.

Every sweep also emits a privacy-safe typed-dependency funnel. It counts non-parent typed edges,
edges inactive for the selected review scope (including closed-only structure), edges below the
bounded structural qualification floor, eligible edges, admitted edges, and omissions attributed
exclusively to the dependency per-issue allowance, dependency lane cap, or run cap. The producer
enforces both conservation equations: total equals inactive plus below-floor plus eligible, and
eligible equals admitted plus the three cap-omission counts. Funnel diagnostics contain counts only;
endpoint identifiers remain limited to admitted candidates and the existing capped-edge summaries.

When either threshold is lowered below its default, selection first reproduces the default-threshold
queue under the same lane, endpoint, and run caps. Only remaining capacity is offered to permissive
additions. Reports expose qualified, admitted, baseline-protected, and cap-drop counts for every lane,
making sensitivity runs monotonic with respect to the bounded default queue.
If a stricter threshold changes which candidate survives a one-per-record, per-issue, lane, or run
cap, the report emits a deterministic `cap_replacements` entry. It contains candidate IDs, the
governing cap, displaced candidate IDs, and a nonempty causal chain from removed qualification
through each consumed or freed endpoint, echo, lane, or run slot. This makes cross-lane and cascading
bounded-queue replacements distinguishable from new semantic qualifications without exposing text.

### Evidence-specific explanations

Every candidate explains the evidence that caused it to surface. Explanations should identify the
strongest contributing canonical fields, lifecycle contrast, structural relationships, and relevant
counterevidence. Generic class-level prompts may supplement this evidence but cannot be the only
explanation.

Anchor extraction confidence, verification specificity, and candidate relationship uncertainty are
separate signals. Reports retain finite-vocabulary anchors and label specificity as a concrete check,
category check, or generic. Concrete checks require an explicit local contract, artifact, invariant,
test, or corroborated ownership-boundary type; the mere presence of acceptance criteria does not
qualify. Safe action/entity pairs remain category checks, while only failed extraction becomes
generic. Candidate evidence identifies semantic-only pairs with no structural
corroboration and preserves direct-threshold, reciprocal, shared-parent, and typed-dependency
admission paths. Neither semantic similarity nor an exception path may assert a shared contract or
completed outcome.

### Similarity performance

Providers return validated normalized vectors. Analysis must avoid renormalizing the same vector for
each comparison and must reuse pairwise scores within a run. A vectorized similarity matrix or an
equivalent bounded score cache is preferred for populations that fit comfortably in memory.

## 12. Candidate-focused disposable batching

Batching operates on issues participating in review signals after structural filtering, ranking,
thresholds, and candidate caps have been applied. It does not force every active issue into a semantic
neighborhood merely because every vector has a nearest neighbor. Records without a qualifying signal
are reported separately as `no signal`.

Broad container records such as epics are excluded from the default review population unless selected
explicitly. Parent/child similarity is structural context and potential counterevidence, not sufficient
evidence of overlap by itself.

Given a candidate graph and configured hard maximum `t`:

1. Find deterministic connected components over active candidate endpoints.
2. Emit components of at most `t` as connected review units.
3. Split larger components by growing a connected unit from a deterministic boundary seed, preferring
   nodes that keep the most candidate edges inside the unit; recursively process connected remainder
   components. This avoids cutting transitive bridge chains near their middle.
4. Pack independent singleton components into bounded agent envelopes, retaining each singleton as
   an explicit one-issue review unit rather than presenting the envelope as a semantic cluster.
5. Report component counts, fragmented components, singleton envelopes, maximum observed size, and
   candidate edges crossing artifacts.

No artifact may exceed `t`. Every multi-issue review unit has a connected induced candidate graph.
The implementation remains deterministic, candidate-only, and advisory; closed echo targets remain
evidence rather than artifact members.

## 13. Batch manifest

Each batch manifest is versioned JSON containing:

```json
{
  "schema_version": 1,
  "run_id": "...",
  "batch": 1,
  "kind": "connected-component",
  "review_units": [{"issue_ids": ["bd-1", "bd-2"]}],
  "snapshot": {
    "workspace_id": "...",
    "beads_version": "...",
    "source_revision": null
  },
  "policy": {
    "read_only": true,
    "implementation_allowed": false,
    "tracker_mutation_allowed": false
  },
  "issues": [],
  "neighbor_evidence": [],
  "review_rubric": []
}
```

`source_revision` is optional because Beads can operate without Git. Project-specific dispatchers may
add repository context separately without changing the core manifest.

## 14. Agent integration

Agent dispatch is an optional adapter consuming batch manifests. The core CLI stops after producing
manifests and reports.

A reviewer adapter must:

- give reviewers read-only tracker instructions;
- prohibit implementation and tracker mutation;
- request evidence for every proposed correction;
- preserve each batch's raw report;
- make partial failures visible;
- avoid requiring durable issues for disposable audit work.

The initial public interface should be a command template or subprocess protocol rather than a
runtime-specific SDK. First-party adapters may later support multiple coding-agent CLIs.

## 15. Safety and privacy invariants

Automated tests must prove:

1. No executable path contains or invokes Beads mutation commands.
2. Tracker content is identical before and after every core command.
3. The default embedding provider performs no content-bearing network request.
4. First-run model downloads are pinned, disclosed, and separate from issue text.
5. Logs do not contain full issue bodies unless verbose output is explicitly requested.
6. Cache and report directories cannot be mistaken for Beads source data.
7. Concurrent runs cannot corrupt cache or status state.
8. Failed runs transition to `failed` and retain diagnostic context.
9. Reports identify their tracker snapshot and embedding model.
10. Fixtures and documentation contain only synthetic public examples.

## 16. Configuration

Configuration precedence:

1. command-line flags;
2. environment variables;
3. user configuration directory;
4. built-in defaults.

No project-local configuration is required for the common path. Optional project configuration may
select structural filters or context-document discovery, but it must never contain vectors or model
artifacts and must not be needed merely to use Beads.

## 17. Output and observability

Every run records:

- start/end timestamps and duration;
- record counts by lifecycle;
- cache hits and misses;
- embedding model and revision;
- effective filters, thresholds, and target batch size;
- warnings and failures;
- paths to JSON and Markdown artifacts.

Machine output is stable and versioned. Human output favors short outcome language and links to the
full evidence. The CLI never treats a similarity score as a lifecycle verdict.

## 18. Packaging and support

- Python 3.11 or later.
- Installable as a normal package and user-level CLI with `uv tool`, `pipx`, or `pip`.
- Supported on current macOS, Linux, and Windows.
- MIT licensed.
- Reproducible locked dependencies for development and release.
- Model and dependency licenses documented in release artifacts.

## 19. Validation strategy

Use synthetic Beads workspaces to test:

- unchanged, changed, new, closed, deferred, and deleted records;
- parent/child and dependency relationships;
- semantic duplicates with different vocabulary;
- related records that must not be classified as duplicates;
- malformed CLI JSON and unsupported Beads versions;
- cold, warm, and one-record incremental runs;
- concurrent and interrupted async sweeps;
- deterministic batch membership and size bounds;
- candidate caps and structurally corroborated threshold exceptions;
- candidate-focused batching with explicit no-signal records and sparse tails;
- evidence-specific explanations and parent/child counterevidence;
- Windows-compatible cache locking;
- tracker hashes before and after commands.

Performance targets should be established on public synthetic corpora. Private project measurements
must not be published as fixtures, snapshots, logs, or examples; anonymized aggregate findings may be
retained with the repository owner's approval. The warm path for a public synthetic corpus of 1,000
records should complete within five seconds on a documented reference CPU, with similarity scoring and
batching measured separately from Beads acquisition.

## 20. Milestones

### M0 — public contract

- Review this specification with Beads users and maintainers.
- Comment on the upstream vector-search discussion with the proposed scope.
- Confirm the synthetic evaluation corpus and initial quality metrics.

### M1 — local semantic core

- Package skeleton, Beads read adapter, canonicalization, local provider, cache, and `neighbors`.
- Cross-platform locking and privacy tests.

### M2 — review batches

- Structural filters, balanced batching, completed-work echoes, deferred-work proximity, and reports.
- Stable manifest schema and async status.

### M3 — optional agent adapters

- Runtime-neutral subprocess contract.
- One reference read-only reviewer adapter and adversarial mutation tests.

### M4 — ecosystem release

- Test against multiple public Beads repositories.
- Publish package and checksums.
- Submit to the Beads community-tools catalog.

## 21. Open decisions

1. Default local embedding model and upgrade policy.
2. Whether reports default to the user state directory or a temporary directory.
3. Whether project context-document discovery belongs in core or only in reviewer adapters.
4. Whether historical Dolt signals should be accepted from companion analytics tools.
5. Minimum supported Beads version and the exact read-only CLI contract.
