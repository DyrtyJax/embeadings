# emBEADings

Semantic neighborhoods for Beads—without another taxonomy to maintain.

Read-only semantic neighborhoods and freshness-review batches for
[Beads](https://github.com/gastownhall/beads).

Beads dependencies answer “what blocks this?” Semantic neighborhoods answer a different question:
“what related work might also need review after the project changes?” emBEADings is intended to
find that neighborhood without adding durable labels, changing issue state, or replacing Beads'
dependency graph.

> Status: MVP implementation. `neighbors`, synchronous `sweep`, `batch`, and local code-surface
> `collisions` are available; async runs and agent dispatch remain future work.

## Install and try it

Python 3.11 or later and an installed `bd` CLI are required.

```bash
python -m pip install -e .
embead neighbors ISSUE_ID --include-closed
embead sweep --size 9

# Find active work pointing at the same files or implementation modules
embead collisions

# Associate a worktree when its branch does not contain the Bead's numeric suffix
embead collisions --worktree-map embead-3ur.49=../embead-code-surface

# Include the same collision evidence in a semantic sweep report
embead sweep --code-surfaces

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

## Code-surface collision evidence

The optional code-surface layer addresses a narrower coordination question: “which active work may
touch the same implementation boundary?” It extracts conservative repository-relative path and
`path::symbol` references from Beads and observes changed paths in associated local Git worktrees.
Worktrees are associated automatically when the branch contains the full Bead ID or an unambiguous
`bead-N` suffix; `--worktree-map ISSUE_ID=PATH` supplies an explicit association when needed.

`embead collisions` does not load an embedding model. It reports exact-file leads and shared-module
leads backed by at least one observed active-worktree pointer, together with evidence source,
confidence, and revision relation. Explicit-only shared-module pairs are counted but omitted from the
primary queue because the private pilot found only 1 of 22 useful. The report contains pointers rather
than source snippets, invokes only read-only Git commands, and never writes inferred surfaces back
into Beads. Shared paths are coordination evidence, not proof that two tasks have conflicting intent.

Repository provenance prefers the worktree from which `embead` is invoked when it shares the same Git
common directory as the tracker checkout. An invocation outside Git or from an unrelated repository
falls back explicitly and emits a warning instead of silently attributing the analysis to that
checkout.

Explicit-only paths or modules referenced by more than five active records are treated as hub
surfaces: they are summarized once and cannot create an all-pairs warning fan-out on their own. A
second non-hub surface or a shared `path::symbol` can still qualify the pair. Exact paths observed in
an active worktree are never suppressed by this guard. Use `--max-hub-surface-issues` to tune the
record-count boundary for a corpus.

This MVP intentionally does not index the whole codebase or add a vector database. In the first
three-repository public pilot, the hub guard reduced 119 explicit-pointer leads to a bounded queue of
26, but only 30.2% of active records contained an extractable pointer. The first private code-surface
pilot validated exact-file evidence while exposing stale-checkout provenance and very low precision
for explicit-only module matches. Those blockers are fixed in source, but a public 0.2.0 tag remains
gated on a repeat run with at least two associated active worktrees. The first corrected preflight
found only one genuinely active implementation worktree and stopped without fabricating evidence. A
separate single-worktree diagnostic passed provenance, module suppression, determinism, and safety,
but 11 of 21 explicit-only exact-file leads were reference-for-inspection noise. Semantic code
retrieval, AST symbols, Git-history inference, and MCP integration belong behind a future optional
evidence-provider interface only if they measurably improve collision recall without producing an
impractical queue.

## Proposed commands

```bash
embead neighbors <issue-id>
embead batch [--size 9]
embead sweep [--size 9]
embead collisions [--worktree-map ISSUE_ID=PATH]
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
Reciprocal exceptions additionally require corpus-discriminative, field-aligned local evidence;
reports expose bounded reason categories without copying matched terms. Stricter-threshold cap
replacements include complete deterministic causal chains, including cross-lane endpoint cascades.
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
- [Aggregate findings from the first public code-surface pilot](docs/research/code-surface-public-eval-01.md)
- [Aggregate findings from the private code-surface release gate](docs/research/code-surface-private-pilot-02.md)
- [Privacy-preserving private code-surface evaluation protocol](docs/evaluation-code-surfaces.md)
- [Public synthetic warm-path performance benchmark](docs/performance.md)
- [Safe offline evaluation and readiness checks](docs/evaluation.md)
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
