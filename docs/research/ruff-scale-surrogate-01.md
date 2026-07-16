# Ruff 8,143-issue scale-surrogate review

## Scope

On 2026-07-16, emBEADings v0.4 reviewed a deterministic conversion of 8,143 public
[`astral-sh/ruff`](https://github.com/astral-sh/ruff) GitHub issues: 1,681 active and 6,462 closed.
The conversion deliberately contained no typed dependency graph. Its disposable Beads repository
was not a Ruff source checkout, so the run is evidence about semantic scale and review packaging,
not native-Beads structure or observed edit collisions.

## Semantic review

The bounded queue contained 16 completed-work echoes and 4 active overlaps. Every admitted pair was
rated against the public issue bodies using the established scale: 2 for a concrete coordination or
duplicate/continuation lead, 1 for useful context, and 0 for misleading or irrelevant output.

| Lane | Rating 2 | Rating 1 | Rating 0 | Useful |
| --- | ---: | ---: | ---: | ---: |
| Echo | 7 | 7 | 2 | 14/16 (87.5%) |
| Overlap | 1 | 2 | 1 | 3/4 (75%) |
| Total | 8 | 9 | 3 | 17/20 (85%) |

Strong results included an exact parser panic follow-up, the same PYI016 interpolation bug, an
isort force-grid-wrap continuation, repeated PERF402 behavior, direct flake8-noqa continuation, and
adjacent Click-docstring rule exceptions. Failures came from broad meta/checklist language, a
template-only closed record with a one-character title, and unrelated flake8 plugin requests.

The hard queue budget was useful: it reduced 13,247 cap omissions to 20 reviewable pairs. This does
not prove recall; it establishes precision of the admitted packet on this public corpus.

## Code-surface diagnostic

All 27 collision leads were explicit-only and none represented a likely edit collision. Four pairs
offered loose subsystem context unrelated to the shared path; 23 were misleading. Generic
reproduction filenames dominated: `example.py` produced 10 pairs, `foo.py` 6, and `conftest.py` 3.
Both `likely-edit` pairs were false because issue-template or reproduction-step verbs occurred near
example paths.

The correct conclusion is not to suppress every explicit path. The tracker was disconnected from
the implementation repository, and issue reports use paths differently from implementation tasks.
The product response is bounded evidence before policy:

- ignore HTML issue-template comments during path and intent extraction;
- distinguish prose, fenced reproduction, and observed-worktree context without retaining snippets;
- report whether explicit paths resolve in the selected repository;
- warn when no explicit pointer resolves, so a detached tracker cannot masquerade as grounded code
  evidence; and
- rank grounded prose above fenced or missing references while preserving all existing leads.

Suppression remains gated on a rated, code-attached tracker with genuine active worktrees.
