# Fresh-session agent plugin evaluation

This protocol compares emBEADings with direct agent judgment without sending private tracker or
repository content back to this project. Run it once in a fresh Codex task and once in a fresh Claude
Code session against the same immutable tracker snapshot. One run per host is a product diagnostic,
not a statistically significant model comparison.

The question is operational: does a bounded, deterministic queue help an agent find and act on
coordination risks faster than a direct review?

## Boundaries and common setup

The repository owner should prepare both sessions identically:

1. Pin the emBEADings commit and installed version. Record the agent host/model, Beads or Linear
   version, repository revision, active/closed counts, and genuine active-worktree count. Install
   the exact release persistently with `uv tool install 'embeadings==VERSION'` or
   `pipx install 'embeadings==VERSION'` so the plugin can discover `embead`; record
   `embead --version`. A direct `uvx` preview is not a substitute for the plugin install check.
2. Use the same default review budget and no custom thresholds in both sessions.
3. Put prompts, raw reports, ratings, fingerprints, and worktree mappings in a private scratch
   directory outside both the evaluated repository and the emBEADings checkout.
4. Prepare the pinned embedding model before loading issues. Deny network access at the operating
   system level for commands that can load issue text when the environment supports it.
5. Capture a canonical read-only tracker fingerprint, `HEAD`, and full Git status including untracked
   files before either session. Capture them again after both sessions.
6. Give neither agent prior emBEADings output, previous evaluation findings, known false positives,
   nor the other agent's worksheet. A maintainer may supply a private set of known collisions, but it
   stays sealed until scoring.

Do not create synthetic worktree associations. With fewer than two genuinely active associated
worktrees, collision output is a partial diagnostic and cannot validate observed-to-observed
behavior.

## Matched two-stage run

Use a fresh context for each host and the same two time boxes.

### Stage A: sealed direct-agent baseline

Allow at most 20 minutes and 20 proposed leads. The agent may inspect the tracker and repository with
native read-only tools, but must not invoke emBEADings, inspect its output, or read an earlier
evaluation. Ask it to identify:

- duplicate or overlapping active work;
- active work that may already be completed;
- missing sequencing or dependency relationships; and
- pairs likely to edit the same implementation contract.

For each proposed pair, privately record the two stable record IDs, the evidence class, a one-line
reason, and the concrete coordination action. Seal the worksheet and record its SHA-256 fingerprint
before Stage B. The public report must contain only aggregate baseline counts and timing.

### Stage B: emBEADings-assisted review

Invoke the installed `evaluate` skill. Run the plugin `check`, followed by `triage` and `collisions`
from the implementation repository. Preserve stdout only in the private scratch directory; do not
pass `--output` or `--write-checkpoint`.

Allow at most 20 minutes for interpretation, excluding CLI runtime and one-time model preparation.
Review the complete default semantic queue and collision leads in emitted order, stopping after 20
collision leads if that lane is larger. Record how many items remained when the time box ended.

Run the same commands a second time only to test byte determinism. Do not give the repeat output an
additional review budget.

### Stage C: reveal and compare

After Stage B ratings are sealed, reveal the direct baseline and optional maintainer-known collision
set. Compare stable record pairs without exposing them in the aggregate report:

- found by both;
- baseline-only;
- emBEADings-only;
- known collision surfaced;
- known collision not surfaced; and
- not measurable because no private truth set was supplied.

For every baseline-only or known missed pair, distinguish `qualified-but-capped`,
`hub-or-module-guarded`, and `not-surfaced-or-unexplained` only when the report provides that
evidence. Do not guess why a pair is absent.

## Rating and accounting rules

Rate each reviewed lead:

- **2 — actionable:** coordinate ownership or sequencing, deduplicate work, change a dependency, or
  verify a concrete shared contract before implementation or merge.
- **1 — contextual:** worth knowing or inspecting, but it does not imply an immediate coordination
  action.
- **0 — misleading:** vocabulary-only, incidental path/reference, broad hub, already-obvious native
  structure, or otherwise not useful for this review.

Report `>=1` useful precision and `2` actionable precision separately for:

1. typed dependency/structure;
2. completed-work echo;
3. semantic overlap;
4. explicit code-surface evidence; and
5. observed worktree evidence.

For code-surface leads, also stratify by `exact-file` versus `shared-module`, evidence source
(`explicit-only`, `observed-only`, or `corroborated`), and `edit_intent` (`observed-edit`,
`likely-edit`, `mixed`, `reference-only`, or `unknown`). Do not combine structure with semantic
precision or explicit pointers with observed edits.

Measure use, not just relevance. For each reviewed lead, privately mark:

- `decision-use`: caused a new or changed coordination decision;
- `inspection-use`: caused inspection of a record or surface not selected in the baseline;
- `confirmation-only`: supported a decision the baseline already made; or
- `unused`: did not affect the review.

Report these counts separately. A rating of 1 does not automatically mean the context was used.

### Singleton envelopes

A `singleton-envelope` is packaging, not a semantic group. Each `review_unit` is an independent
one-record review. Record:

- envelopes and independent review units completed;
- units left when the time box ended; and
- any instance where the agent incorrectly inferred a relationship between sibling units.

Do not rate envelope coherence.

## Install-friction and safety evidence

For each host, report:

- elapsed time from session start to a successful plugin `check`;
- commands, restarts, PATH fixes, or documentation detours required;
- whether plugin discovery worked in the fresh session;
- whether credentials remained in environment/configuration rather than prompts or output; and
- agent-review time, CLI wall time, completion, and abandonment separately.

The safety result must distinguish:

- logical tracker non-mutation;
- Git-visible non-mutation; and
- strict physical immutability, if ignored tracker storage was fingerprinted.

Also report whether raw artifacts were confined to private scratch, whether repository files were
created, whether the model was prepared before issue loading, and whether issue-loading runs had
OS-level network denial. Delete private scratch after the owner has retained the approved aggregate
findings.

## Copy/paste prompt

Use the same body for both hosts. In Codex, explicitly ask for the installed emBEADings `evaluate`
skill. In Claude Code, invoke `/embeadings:evaluate` with this body.

```text
Evaluate whether emBEADings reduces coordination-triage work in this private repository.

Follow docs/evaluation-agent-plugin.md exactly. This is a read-only evaluation: do not edit the
tracker, repository, worktrees, dependencies, branches, or issue state. Keep all raw IDs, titles,
bodies, paths, symbols, prompts, reports, mappings, and ratings in the private scratch directory
provided by the repository owner. Return only the aggregate report template from the protocol.

First perform and seal the 20-minute, 20-lead direct-agent baseline without invoking emBEADings or
reading prior findings. Record its private SHA-256 fingerprint. Only then invoke the installed
embeadings evaluate skill, run its check, triage, and collisions workflows, and complete the bounded
assisted review. Use the default review budget and no custom thresholds. Repeat output only to test
determinism.

Keep evidence lanes separate; account for baseline-only and known missed collisions without guessing
omission reasons; stratify code leads by kind, source, and edit_intent; treat singleton-envelope
review_units independently; and measure decision-use, inspection-use, confirmation-only, and unused
context. If fewer than two genuine active worktrees are associated, label collision findings a
partial diagnostic rather than a release gate.

Record install friction, bounded review time, unfinished items, privacy, network posture, and
logical/Git-visible/strict-physical non-mutation at the measured scope. End with ship, revise, or
abandon for this repository and name the smallest next change.
```

## Aggregate report template

Do not include issue IDs or examples from the private corpus.

```text
Environment
- Host/model:
- emBEADings commit/version:
- Tracker/version and acquisition source:
- Corpus: total / active / closed:
- Repository revision:
- Genuine worktrees: discovered / associated:
- Review budget:

Install and execution
- Time to successful plugin check:
- Interventions/restarts/docs detours:
- Plugin discovery:
- CLI cold/warm wall time:
- Output deterministic:

Bounded review
- Direct baseline: minutes / leads / unfinished:
- Assisted review: minutes / semantic reviewed / collision reviewed / unfinished:
- Baseline worksheet fingerprint:
- Pair comparison: both / baseline-only / emBEADings-only:

Per-lane ratings
Lane | reviewed | rating 2 | rating 1 | rating 0 | actionable precision | useful precision

Code-surface stratification
- By exact-file/shared-module:
- By explicit-only/observed-only/corroborated:
- By edit_intent:
- Known collisions surfaced / missed / not measured:
- Miss accounting: qualified-capped / guarded / unexplained:

Packaging and context use
- Singleton envelopes / independent units / units completed / interpretation errors:
- Decision-use / inspection-use / confirmation-only / unused:
- Actionable findings per reviewer minute:

Safety and privacy
- Logical tracker unchanged:
- Git-visible state unchanged:
- Strict physical immutability: pass / fail / not measured:
- Raw artifacts confined to private scratch:
- Repository files created:
- Model prepared before issue loading:
- OS-level network denial during issue-loading runs:

Findings
- Highest-value evidence:
- False-positive patterns:
- Baseline-only misses:
- Did the bounded queue reduce work or create another queue?
- Verdict: ship / revise / abandon for this repository
- Smallest recommended change:
- Scope caveats:
```
