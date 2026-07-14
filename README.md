# emBEADings

Semantic neighborhoods for Beads—without another taxonomy to maintain.

Read-only semantic neighborhoods and freshness-review batches for
[Beads](https://github.com/gastownhall/beads).

Beads dependencies answer “what blocks this?” Semantic neighborhoods answer a different question:
“what related work might also need review after the project changes?” emBEADings is intended to
find that neighborhood without adding durable labels, changing issue state, or replacing Beads'
dependency graph.

> Status: MVP implementation. `neighbors`, synchronous `sweep`, and `batch` are available; async
> runs and agent dispatch remain future work.

## Install and try it

Python 3.11 or later and an installed `bd` CLI are required.

```bash
python -m pip install -e .
embead neighbors ISSUE_ID --include-closed
embead sweep --size 9

# Review only candidates touching active work changed after a timestamp
embead sweep --changed-since 2026-07-01T00:00:00Z

# Carry a portable review checkpoint between runs (keep it outside the repository)
embead sweep --since-checkpoint /tmp/embead-checkpoint.json \
  --write-checkpoint /tmp/embead-next-checkpoint.json

# Keep a weekly review queue to at most twelve candidates
embead sweep --weekly-review-budget 12
```

The first semantic command downloads the pinned
[`minishlab/potion-base-8M`](https://huggingface.co/minishlab/potion-base-8M) model (MIT license).
Issue text is embedded locally and is not uploaded. Vectors are cached in the platform user cache;
run reports are written to the platform user state directory. Neither is written into the analyzed
repository by default.

For a lightweight deterministic smoke test without a model download, set
`EMBEAD_PROVIDER=hashing`. That provider is intended for tests, not semantic-quality evaluation.

## Intended workflow

```text
live Beads data
      │
      ▼
incremental local embeddings
      │
      ├── nearest active and closed neighbors
      ├── duplicate/echo review candidates
      └── balanced disposable batches
                         │
                         ▼
              human or read-only agents
                         │
                         ▼
                 evidence-backed report
```

The tool discovers a Beads workspace, reads current records through the `bd` CLI, computes embeddings
locally, and emits disposable JSON and Markdown reports. A separate human or coordinator may decide
whether any tracker update is appropriate.

## Proposed commands

```bash
embead neighbors <issue-id>
embead batch [--size 9]
embead sweep [--size 9]
```

Use `--json` for machine-readable stdout. `batch` is currently an alias for the synchronous sweep.
Both commands accept mutually exclusive `--changed-since RFC3339` and `--since-checkpoint PATH`
scopes. `--write-checkpoint PATH` atomically writes a metadata-only snapshot: issue IDs, normalized
update timestamps, and one-way record fingerprints. Checkpoints must remain outside the Beads
repository; malformed, future-dated, or cross-workspace checkpoints fail closed. Records without an
update timestamp are conservatively treated as changed.
Sweeps keep their conservative similarity thresholds while allowing a narrow, corroborated exception
band. Typed dependencies, completed-work echoes, and possible overlaps have separate deterministic
budgets; dependency evidence is admitted first. Use `--exception-margin`, `--reciprocal-rank`,
`--max-candidates-per-issue`, `--max-dependency-candidates-per-issue`, `--max-candidates`, and the
three `--max-*-candidates` lane controls to tune that policy. Lower-threshold sensitivity runs
protect the candidates selected by the default
thresholds before admitting additions, so a permissive run cannot silently replace the baseline queue.
For a smaller recurring queue, `--weekly-review-budget N` (also available as `--review-budget N`)
applies a hard total candidate budget while retaining the independent dependency allowance. Selection
is deterministic: typed dependencies are considered first, followed by high-confidence completed-work
echoes and then possible overlaps. Reports record the applied budget, admitted total, and compact
per-lane omission counts. The preset composes with both incremental scope flags.

Sweeps batch only issues participating in accepted review signals. Unmatched records are summarized
as no-signal, and epics are excluded by default; pass `--include-epics` when broad container records
are intentionally part of the review population. `--size` is a hard artifact maximum. Connected
review units remain connected when a large component is split. Independent echo-only singletons are
packed into bounded, explicitly labeled agent envelopes rather than emitted as hundreds of files.
Sweep reports include deterministic component, fragmentation, envelope, and cross-batch-edge counts.

See [the product and technical specification](docs/spec.md) for the proposed contracts, safety
invariants, batch format, architecture, and milestones.

Research notes:

- [Open-source semantic search and Beads ecosystem sweep](docs/ecosystem-sweep.md)
- [Anonymized aggregate findings from the first private pilot](docs/research/private-pilot-01.md)
- [Public synthetic warm-path performance benchmark](docs/performance.md)
- [Consumer compatibility and capability contract](docs/consumer-contract.md)
- [Version 1 JSON Schemas](schemas/v1/) and [synthetic examples](examples/)

## Principles

- **Read-only means read-only.** The executable will contain no issue mutation commands.
- **Beads remains authoritative.** Read through supported `bd --json` interfaces, never a stale export.
- **Semantics complement structure.** Similarity is advisory; dependencies and lifecycle remain Beads data.
- **Disposable analysis.** Vectors, models, batches, and reports live outside application repositories.
- **Local-first and private.** The default provider sends no issue content to a network service.
- **Agent-neutral.** Core analysis does not depend on Codex, Claude, Cursor, or another runtime.

## Relationship to the ecosystem

The project follows Beads' guidance for standalone integrations and draws inspiration from:

- [Thread](https://github.com/jklenk/thread) for strict read-only analytics and agent-consumable output;
- [Mardi Gras](https://github.com/quietpublish/mardi-gras) for optional agent-runtime adapters;
- [Perles](https://github.com/zjrosen/perles) for keeping structural filtering separate from analysis;
- [BeadBoard](https://github.com/jordanhindo/beadboard) for capability-gated reviewer roles.

It is not a dashboard, issue editor, general memory system, or orchestration framework.

## License

MIT
