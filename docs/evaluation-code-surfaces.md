# Private code-surface evaluation

Run this protocol inside the private repository. Keep every raw artifact outside both the private
repository and the emBEADings checkout. Return only aggregate measurements; do not report issue IDs,
titles, descriptions, repository paths, symbols, snippets, branch names, or worktree locations.

## Prepare and fingerprint

1. Record the exact emBEADings commit/version, Beads version, repository commit, active-record count,
   and number of Git worktrees.
2. Capture a tracker export fingerprint and a full Git-status fingerprint, including untracked files.
3. Choose external locations for output, cache, and state, such as a private temporary directory.
4. List active worktrees with `git worktree list --porcelain`. Let emBEADings auto-associate branches
   containing a full Bead ID or unique `bead-N` suffix. For other active agent worktrees, supply a
   private repeatable mapping: `--worktree-map ISSUE_ID=/absolute/worktree/path`.
5. For a release gate, require at least two associated active worktrees so observed-only and
   corroborated ranking can both be exercised. Run the command from the current implementation
   worktree, not a tracker-owner checkout retained only to host the shared Beads database.

Do not rename branches, edit issues, create repository files, or copy mappings into the evaluation
report merely to improve association coverage.

## Run

```console
embead collisions --json --output /private/tmp/embead-collisions.json
embead collisions --json --output /private/tmp/embead-collisions-repeat.json
```

Add the same private `--worktree-map` flags to both commands when needed. Confirm the two outputs are
byte-identical after excluding no fields; collision reports are deterministic.

Confirm `repository_context` is `invocation-worktree` and `repository_revision` equals the output of
`git rev-parse HEAD` in the invoking worktree. Treat a silent mismatch as a release-blocking defect. A
warned fallback is acceptable only when the evaluator intentionally invokes outside the tracker
repository.

Run two sensitivity checks with `--max-hub-surface-issues 3` and `8`. Keep all artifacts private.
Do not run a semantic sweep for this code-surface gate unless a separate semantic comparison is
desired; `collisions` intentionally does not load the embedding model.

## Review

Rate a bounded sample of retained leads:

- **2 — likely edit collision:** both tasks are likely to change the same implementation contract and
  should coordinate before merging.
- **1 — useful coordination:** shared ownership or sequencing is worth checking, but simultaneous edits
  are not established.
- **0 — misleading:** the shared pointer is incidental, generated, overly broad, or otherwise not a
  useful coordination lead.

Stratify ratings by `exact-file` versus `shared-module` and by evidence source:

- explicit-only;
- observed-only;
- corroborated explicit plus observed.

Separately inspect up to 20 hub-suppressed pairs sampled deterministically across summarized hubs.
Estimate how many would have been useful and note whether any involved a true active edit. Observed
exact-file evidence should never be hub-suppressed; treat any such case as a release-blocking defect.

## Return this aggregate report

- environment and corpus counts;
- active records with explicit, observed, corroborated, and unavailable surfaces;
- discovered and associated worktree counts, without their locations;
- retained leads by kind, evidence source, and rating;
- hub summaries, omitted-pair count, and the bounded omitted-pair audit;
- explicit-only module omission count and any retained module leads by observed/corroborated source;
- results at hub limits 3, 5, and 8;
- runtime and repeat-output determinism;
- tracker, Git-visible, and repository-file non-mutation results;
- false-positive patterns, missed known collisions if any, and a go/no-go recommendation.

Do not include raw examples, even anonymized quotations. Describe patterns at the level of evidence
class and failure mode so no private task or source content enters emBEADings.
