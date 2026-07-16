# The release gate stopped the release twice

When we prepared the emBEADings v0.4.0 technical preview, the code-surface feature still had one
unanswered question: would it remain useful when several genuine implementation worktrees existed at
the same time?

We could have assembled a synthetic demonstration. Instead, we used the four active worktrees that
were building the release itself. The result was less tidy and more useful. The first two honest runs
exposed defects in emBEADings before the final gate passed.

This is a dogfood story from one repository. It is not a precision or recall claim for other projects.
The full counts, revisions, and limitations are in the
[aggregate v0.4.0 gate report](../research/code-surface-v040-release-gate.md).

## What we were testing

The four worktrees covered:

- worktree environment isolation;
- release packaging;
- worktree-association correctness; and
- concurrent-status scoping.

They were genuine active implementations, not idle checkouts created to make the test pass. Two were
associated through their full Bead IDs and two through explicit mappings. The gate checked
association provenance, repeated-output determinism, non-mutation, exact-file evidence, module-level
coordination, and hub suppression.

The release condition was intentionally narrow: known exact-file collisions in this bounded
population should appear, observed evidence should not be suppressed, and the run should not invent
associations or mutate tracker or source state.

## First stop: a version number looked like a Bead ID

One release branch contained `v0.4.0`. The association fallback interpreted its bare numeric suffix
as belonging to an unrelated issue. A worktree already assigned through an explicit mapping was then
attributed to a second issue as well.

That was not a harmless display problem. Once a worktree is attached to the wrong task, every changed
path in that worktree becomes misleading coordination evidence.

We stopped the gate and changed the association contract in
[PR #57](https://github.com/DyrtyJax/embeadings/pull/57):

- an explicitly mapped path is reserved for that issue;
- duplicate explicit ownership is rejected; and
- numeric fallback now requires the documented `bead-N` token rather than any matching digits.

Regression tests cover the version-like branch that exposed the defect.

## Second stop: deferred work looked concurrent

The corrected association run revealed a different scope problem. Tasks deferred until 2027 were
entering the default collision population because the policy treated every non-closed status as
potentially concurrent.

Deferred work can still be useful context, but it should not appear beside active work as though both
implementations are underway now. That makes a conservative coordination queue noisier and weakens
the meaning of an observed lead.

We stopped again. [PR #58](https://github.com/DyrtyJax/embeadings/pull/58) narrowed the default
collision population to `open`, `in_progress`, and `blocked`. Deferred records remain available when
a reviewer asks for them explicitly.

## The final bounded result

After both fixes, the integrated gate used 10 concurrent non-epic records and associated four genuine
worktrees. It observed 21 code-surface pointers and returned four leads:

| Evidence | Leads | Manual interpretation |
| --- | ---: | --- |
| Observed exact file | 3 | Three known pairs were concurrently changing `README.md` |
| Observed shared module | 1 | Useful coordination between separate files under `src/embead` |

Both default runs were byte-identical. No observed exact-file lead was suppressed. Tracker and Git
fingerprints were unchanged, no embedding model loaded, and no issue text left the machine.

All three known exact-file collisions in this small population appeared. That statement is deliberately
bounded. All three involved the same file, the evaluation covered one repository, and only four active
worktrees were associated.

## What we learned

The most valuable output was not a high similarity score. It was a falsifiable statement about local
state: these two active tasks are associated with worktrees that changed the same path at known
revisions.

The failed runs also reinforced three product rules:

1. Association provenance is part of the evidence, not an implementation detail.
2. “Not closed” is not the same as “concurrent.”
3. Abstaining from an uncertain association is safer than manufacturing worktree coverage.

Those rules matter because a deterministic false attribution is still false. Repeatability makes an
analysis auditable; it does not make the underlying evidence correct.

## What this did not establish

This gate did not measure universal collision recall or precision. It did not test teams that use
different branch conventions, repositories with hundreds of active worktrees, or trackers without
code pointers. It did not establish the usefulness of semantic triage, and it does not show that a
shared path proves conflicting intent.

Those are evaluation questions, not conclusions we can borrow from one successful dogfood run.

What the gate did establish is smaller and practical: on the repository building emBEADings, the
read-only worktree mechanism exposed two flaws in its own evidence pipeline, then passed a corrected,
repeatable four-worktree test without fabricating state. That was enough evidence to ship a technical
preview—and enough friction to keep the claim narrow.

## Try the same bounded check

From a Beads repository with genuine active implementation worktrees:

```bash
embead doctor
embead collisions
```

If a branch cannot be associated unambiguously, map it explicitly:

```bash
embead collisions --worktree-map bead-42=../feature-worktree
```

Do not map an idle or reconstructed checkout just to increase coverage. The useful test is whether the
report describes work that is actually underway.
