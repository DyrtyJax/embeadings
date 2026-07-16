# emBEADings

Semantic neighborhoods for engineering work—without another taxonomy to maintain.

Read-only semantic neighborhoods, coordination review batches, and code-surface collision leads for
[Beads](https://github.com/gastownhall/beads) and Linear.

Beads dependencies answer “what blocks this?” Semantic neighborhoods answer a different question:
“what related work might also need review after the project changes?” emBEADings is intended to
find that neighborhood without adding durable labels, changing issue state, or replacing Beads'
dependency graph.

> Status: v0.3 implementation. `neighbors`, synchronous `sweep`, `batch`, and local code-surface
> `collisions` are available for Beads and a selected Linear team; async runs and agent dispatch
> remain future work.

## Install and try it

Python 3.11 or later is required. The default Beads source also requires an installed `bd` CLI.

```bash
python -m pip install -e .
embead doctor
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

# Experimental retrieve-verify evaluation: separate semantic novelty from known structure
embead sweep --objective overlap --objective echo --semantic-view fields

# Audit typed tracker relationships without spending the semantic novelty budget
embead sweep --objective structure
```

### Use a Linear team

Create a personal API key in Linear's Security & access settings, keep it out of shell history, and
pass only the team ID, key, or exact name on the command line:

```bash
export LINEAR_API_KEY="..."

embead --source linear --linear-team ENG neighbors ENG-123 --include-closed
embead --source linear --linear-team ENG sweep --code-surfaces
embead --source linear --linear-team ENG collisions
```

`LINEAR_ACCESS_TOKEN` accepts an OAuth access token instead; set only one credential. `LINEAR_TEAM`
and `EMBEAD_SOURCE=linear` can supply the repeated source arguments. The standalone CLI does not
reuse credentials held by an MCP host.

The Linear adapter issues GraphQL queries only. A canonical team UUID is resolved directly; a key or
exact name uses the paginated team lookup. The adapter then pages the selected team's issues and the
visible workspace relation collection, canonicalizes reciprocal or multi-typed pairs, and omits
external endpoints without fetching their records. Every omission is surfaced both as a
human-readable warning and in `snapshot.relation_diagnostics`, including direction and relation-type
counts at the selected-team boundary. This avoids per-issue detail requests and preserves the
structural ranking conservation invariant. Linear's suggested branch name is not treated as an
observed edit; only real local Git worktree changes can supply observed code-surface evidence. See
[the Linear adapter contract](docs/linear.md) for the field mapping and privacy boundary.

The first semantic command downloads the pinned
[`minishlab/potion-base-8M`](https://huggingface.co/minishlab/potion-base-8M) model (MIT license).
Issue text is embedded locally and is not uploaded. Vectors are cached in the platform user cache;
run reports are written to the platform user state directory. Neither is written into the analyzed
repository by default.

For a lightweight deterministic smoke test without a model download, set
`EMBEAD_PROVIDER=hashing`. That provider is intended for tests, not semantic-quality evaluation.

## Agent plugin preview

The repository includes a thin dual-host plugin under
[`plugins/embeadings`](plugins/embeadings/README.md) for Codex and Claude Code. It packages shared
`triage`, `collisions`, and `evaluate` skills around the installed `embead` CLI; it does not contain
a second ranking engine or grant tracker-write authority.

For local Claude Code development:

```bash
claude --plugin-dir ./plugins/embeadings
```

The Codex and Claude manifests live separately while sharing the same skills and guarded CLI
launcher. The cross-platform Python launcher requires emBEADings 0.3.0 or newer, forces schema-v1
JSON, rejects explicit report/checkpoint paths, and verifies the report's read-only policy. Semantic
sweeps may still use the external platform cache and run-state directories described above; they do
not write into the analyzed repository by default.

This is a local plugin foundation, not yet a marketplace release. Marketplace metadata, a public
package tag, and observed-to-observed collision validation remain gated on the corresponding Beads
work and private evaluation.

## Intended workflow

```text
Beads or Linear data
      │
      ├── tracker structure and lifecycle
      ├── explicit and observed code surfaces
      └── whole-record and field-local semantics
                         │
                         ▼
              bounded candidate union
                         │
                         ▼
        objective-specific review and abstention
                         │
                         ▼
           evidence receipt + disposable batches
```

The tool discovers a Beads workspace or queries one selected Linear team, computes embeddings locally,
and emits disposable JSON and Markdown reports. A separate human or coordinator may decide whether
any tracker update is appropriate.

## Code-surface collision evidence

The optional code-surface layer addresses a narrower coordination question: “which active work may
touch the same implementation boundary?” It extracts conservative repository-relative path and
`path::symbol` references from Beads and observes changed paths in associated local Git worktrees.
Worktrees are associated automatically when the branch contains the full Bead ID or an unambiguous
`bead-N` suffix; `--worktree-map ISSUE_ID=PATH` supplies an explicit association when needed.
Explicit mappings must name an active record in the evaluated population and a registered worktree;
an excluded epic, closed record, or record filtered out by the current status scope fails with a
corrective error instead of silently supplying evidence.

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

Observed evidence is intended to describe current implementation, not all changes since an arbitrary
historical point. If `--base-ref` produces more than 250 eligible committed code paths for an
associated worktree, emBEADings excludes that committed diff and emits a warning. Current tracked and
untracked working-tree paths remain eligible. Choose a current base reference to restore committed
change evidence; do not accept a large pointer count as proof that worktree coverage improved. This
is a volume circuit breaker, not proof that a base reference is current; the evaluator must still
verify the intended integration base.

Explicit-only paths or modules referenced by more than five active records are treated as hub
surfaces: they are summarized once and cannot create an all-pairs warning fan-out on their own. A
second non-hub surface or a shared `path::symbol` can still qualify the pair. Exact paths observed in
an active worktree are never suppressed by this guard. Use `--max-hub-surface-issues` to tune the
record-count boundary for a corpus.

This MVP intentionally does not index the whole codebase or add a vector database. In the first
three-repository public pilot, the hub guard reduced 119 explicit-pointer leads to a bounded queue of
26, but only 30.2% of active records contained an extractable pointer. The first private code-surface
pilot validated exact-file evidence while exposing stale-checkout provenance and very low precision
for explicit-only module matches. Those blockers are fixed in source, but a public package tag remains
gated on a repeat run with at least two associated active worktrees. The first corrected preflight
found only one genuinely active implementation worktree and stopped without fabricating evidence. A
separate single-worktree diagnostic passed provenance, module suppression, determinism, and safety,
but 11 of 21 explicit-only exact-file leads were reference-for-inspection noise. Semantic code
retrieval, AST symbols, Git-history inference, and MCP integration belong behind a future optional
evidence-provider interface only if they measurably improve collision recall without producing an
impractical queue.

## Commands

```bash
embead neighbors <issue-id>
embead batch [--size 9]
embead sweep [--size 9]
embead collisions [--worktree-map ISSUE_ID=PATH]
embead doctor [--offline]
embead capabilities [--json]
```

Use `--json` for machine-readable stdout. `batch` is currently an alias for the synchronous sweep.
Both commands accept mutually exclusive `--changed-since RFC3339` and `--since-checkpoint PATH`
scopes. `--write-checkpoint PATH` atomically writes a metadata-only snapshot: issue IDs, normalized
update timestamps, and one-way record fingerprints. Checkpoints must remain outside the Beads
repository; malformed, future-dated, or cross-workspace checkpoints fail closed. Records without an
update timestamp are conservatively treated as changed.
Sweeps keep their conservative similarity thresholds while allowing a narrow, corroborated exception
band. Typed dependencies, completed-work echoes, and possible overlaps have separate deterministic
budgets. Use `--exception-margin`, `--reciprocal-rank`,
`--max-candidates-per-issue`, `--max-dependency-candidates-per-issue`, `--max-candidates`, and the
three `--max-*-candidates` lane controls to tune that policy. Lower-threshold sensitivity runs
protect the candidates selected by the default
thresholds before admitting additions, so a permissive run cannot silently replace the baseline queue.
Reciprocal exceptions additionally require corpus-discriminative, field-aligned local evidence;
reports expose bounded reason categories without copying matched terms. Stricter-threshold cap
replacements include complete deterministic causal chains, including cross-lane endpoint cascades.
For a smaller recurring queue, `--weekly-review-budget N` (also available as `--review-budget N`)
applies a hard total candidate budget and reserves access for every differentiated lane before the
normal dependency → echo → overlap priority pass. For budgets of three or more, approximately 60% is
reserved for typed dependencies, 20% for completed-work echoes, and 20% for no-edge overlaps. Unused
reservations return to the common queue; they are minimum access, not quotas. A budget of one reserves
the slot for overlap, and a budget of two reserves one dependency and one overlap. Reports record the
reservation, admission-to-reservation, unused, and omitted counts per lane. Code-surface collision
leads are reported separately and do not consume the semantic candidate budget. The preset composes
with both incremental scope flags.

### Experimental objective and field-aware retrieval

Omitting `--objective` retains the legacy lane semantics. Passing one or more `--objective` flags
enables the retrieve–verify evaluation contract:

- `overlap` searches active work for semantic scope overlap;
- `echo` searches active work against completed work;
- `structure` audits typed tracker relationships in its own lane;
- `collision` enables the existing local code-surface analysis outside the semantic budget.

When `structure` is omitted, a typed dependency may annotate an overlap or echo but cannot take the
dependency lane or admit a below-threshold pair. This prevents known graph edges from consuming a
novel-discovery budget. Explicit `overlap` reviews also exclude direct parent/child pairs: the known
hierarchy remains tracker context, but does not consume a semantic-discovery slot.

Completed-work echoes admit at most two candidates pointing to the same closed record by default.
Use `--max-echoes-per-target` to tune that deterministic diversity cap. When a target reaches the
cap, the selector considers the next qualified completed record for the active issue; JSON and
Markdown enforce `qualified = admitted + omitted` for each repeated target and itemize omissions by
target, active-record, per-issue, lane, and run limits. When a target-cap omission is followed by an
admitted fallback, `echo_backfills` records both candidate IDs and scores without issue text. A
backfill increases completed-target coverage; it is not a claim that the fallback is more relevant.
At most three qualified fallback echoes are retained per active issue by default; tune that bounded
pool with `--max-echo-alternatives-per-active`.

`--semantic-view fields` is experimental: it retains the whole-record
vector and adds separate title, description, acceptance-criteria, and design vectors. Notes remain in
the whole-record representation but are excluded from field-local retrieval. Candidate JSON and
Markdown record the selected objective, every contributing channel, its pair score, both directional
ranks, and whether structural evidence was selected or merely contextual.

The current field union uses the maximum available semantic-view score deliberately. It is an
auditable research baseline, not a calibrated probability or final fusion policy. Run the public
hard-negative benchmark before comparing model or ranking changes:

```bash
python scripts/evaluate_semantic_fixture.py
python scripts/evaluate_semantic_fixture.py --provider model2vec
```

The fixture contains sanitized same-token/different-intent, shared-subsystem, completed-invariant,
reference-versus-edit, direct-hierarchy, and repeated-closed-target hub cases. Generic embedding
benchmarks are insufficient release evidence.

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
- [Aggregate findings from the first private Linear evaluation](docs/research/linear-private-pilot-01.md)
- [Privacy-preserving private code-surface evaluation protocol](docs/evaluation-code-surfaces.md)
- [Privacy-preserving Linear regression protocol](docs/evaluation-linear.md)
- [Public synthetic warm-path performance benchmark](docs/performance.md)
- [Safe offline evaluation and readiness checks](docs/evaluation.md)
- [Retrieve–verify research synthesis](docs/research/retrieve-verify-context-2026.md)
- [First retrieve–verify public regression](docs/research/retrieve-verify-public-regression-01.md)
- [Second retrieve–verify private regression](docs/research/retrieve-verify-private-regression-02.md)
- [Third retrieve–verify private regression](docs/research/retrieve-verify-private-regression-03.md)
- [Consumer compatibility and capability contract](docs/consumer-contract.md)
- [Version 1 JSON Schemas](schemas/v1/) and [synthetic examples](examples/)

## Principles

- **Read-only means read-only.** Tracker adapters contain no issue mutation operations.
- **The tracker remains authoritative.** Read through supported live Beads or Linear interfaces.
- **Semantics complement structure.** Similarity is advisory; dependencies and lifecycle remain tracker data.
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
