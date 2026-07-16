# v0.4.0 concurrent-worktree release gate

Date: 2026-07-16

Verdict: **pass for the v0.4.0 technical-preview release.** This is evidence from one repository,
not a claim of universal collision precision.

## Scope

The gate used four genuine, active implementation worktrees created for the release-polish wave:
worktree environment isolation, release packaging, worktree-association correctness, and concurrent
status scoping. Two worktrees were explicitly mapped and two were associated through their full Bead
IDs. No idle, reconstructed, administrative, or completed worktree was mapped.

The tested integration tree was byte-identical to the tree merged to `main` at
`3131d1a643db4696c6af84eecd852f9142f77e49`. The invocation revision during the gate was
`2aca1c2878001cfdabea57e32c9242fc0534683b`; the verified base was
`177d13e67d8dd0dd76c5abb19581eaf2a9111f0d` from `origin/main`.

- Beads: 1.0.5
- emBEADings: 0.4.0
- Live tracker records: 103
- Evaluated concurrent, non-epic records: 10
- Registered worktrees discovered: 22
- Genuine active worktrees associated: 4
- Code-surface pointers: 21 (17 observed, 4 explicit)

## Results

Two default runs were byte-identical. Repository context was `invocation-worktree`, the reported
repository revision matched the invoking worktree, and no warnings were emitted.

The queue contained four observed-worktree leads:

| Evidence | Rating 2 | Rating 1 | Rating 0 | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Exact file | 3 | 0 | 0 | Three real pairs concurrently changed `README.md`. |
| Shared module | 0 | 1 | 0 | Two core fixes changed separate files under `src/embead`; coordination was useful, but no exact edit collision existed. |

All known exact-file collisions in the four-worktree population surfaced. No observed exact-file
lead was hub-suppressed. Hub limits 3, 5, and 8 retained the same four leads with zero hub surfaces,
zero hub omissions, and zero module-guard omissions. Measured sensitivity runs completed in
1.26–1.98 seconds on the evaluation machine.

Tracker population fingerprints and Git-status fingerprints for the invoking checkout and all four
implementation worktrees were unchanged across the repeated runs. No model loaded, no issue text
left the machine, and no raw report or worktree mapping is stored in this repository.

## Dogfood findings

The first honest run prevented a premature release by finding two defects:

1. A release branch containing `v0.4.0` matched the bare numeric suffix of an unrelated issue, so
   one explicitly mapped worktree was attributed to two issues. PR #57 reserves explicit paths,
   rejects duplicate ownership, and requires the documented `bead-N` token for suffix fallback.
2. Tasks deferred until 2027 entered the default collision queue as concurrent work. PR #58 narrows
   collision defaults to `open`, `in_progress`, and `blocked`, while keeping deferred review opt-in.

Both fixes have direct regressions. PR #59 added checkout-local editable-environment protection, and
PR #60 added deterministic release artifacts and a fresh-wheel installation gate. The integrated
suite passed 256 tests; GitHub CI passed on macOS, Windows, Python 3.11, Python 3.14, and the package
artifact job.

## Decision and limitations

The observed collision mechanism is ready for a v0.4.0 technical preview: it found the real merge
boundary, preserved provenance, abstained from fabricated associations after the fix, and remained
deterministic and non-mutating. The result does not establish recall for teams that lack worktree
mappings, precision across other repository layouts, or semantic-triage value at the target ICP.
Those questions remain separate evaluation work rather than tag blockers.
