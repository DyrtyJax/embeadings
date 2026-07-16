# Ruff review-depth and incremental-scope evaluation

## Scope

On 2026-07-16, emBEADings v0.4 evaluated the existing deterministic conversion of 8,143
public Ruff GitHub issues: 1,681 active and 6,462 closed. The corpus remains a scale surrogate,
not native-Beads evidence: it has no typed dependency graph or genuine worktree associations.
All generated reports, ratings, and corpus subsets stayed outside this repository.

This pass separated two questions that the original 20-item evaluation had conflated:

- Is a bounded weekly packet useful for a reviewer?
- How does semantic quality behave below the first 20 results?

## Fixed-pool blinded review

A single 250-candidate run admitted 125 completed-work echoes and 125 active overlaps from 4,675
and 8,599 qualified pairs respectively. It took 101.20 seconds and peaked at 724,828,160 bytes
RSS. Changing the operational budget from 20 to 250 preserved 19 of the original 20 candidates;
lane reservation changed one result, confirming that separate budget runs are not strict prefixes.

The evaluation-only ranked-pool harness therefore sampled one immutable 250-item artifact. It drew
at most ten pairs per lane and rank band, shuffled them deterministically, and hid rank, lane, kind,
and score from a fresh reviewer. The resulting 70 ratings were:

| Rank band | Rated | Actionable (2) | Contextual (1) | Misleading (0) | Useful |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1–20 | 13 | 7 | 4 | 2 | 84.6% |
| 21–50 | 17 | 5 | 7 | 5 | 70.6% |
| 51–100 | 20 | 10 | 2 | 8 | 60.0% |
| 101–250 | 20 | 7 | 8 | 5 | 75.0% |
| Total | 70 | 29 | 21 | 20 | 71.4% |

Echoes were 75.0% useful and 45.0% actionable; overlaps were 66.7% useful and 36.7% actionable.
A post-stratified estimate for the full pool was approximately 72.0% useful and 39.3% actionable,
but the long-tail overlap cell sampled only 10 of 104 pairs. Quality was jagged rather than a
smooth decay curve, so these bands should guide a larger audit rather than a threshold change.

The strongest lower-ranked results shared exact Ruff rule identifiers or explicit continuation
semantics. Repeated false positives came from empty or non-substantive issues and generic words such
as `docstring`, `formatter`, `import`, and `fix` applied to different rules. This favors bounded
substantive-content checks and identifier-aware verification over a global cosine-threshold change.

The first harness invocation exposed a blinding defect: it wrote a safe `review.json` but printed
the detailed manifest to stdout. The harness now prints only paths, sample size, and fingerprints;
the detailed manifest stays sealed until ratings are complete, with a regression test enforcing
that boundary.

## Weekly recency scopes

The 7-, 30-, and 90-day scopes contained 37, 96, and 222 changed active records. Each retained the
20-item operational budget with 16 echoes and 4 overlaps.

| Scope | Changed active | Qualified echo / overlap | Changed records represented | Wall time | Peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 7 days | 37 | 96 / 237 | 16 (43.2%) | 136.22s | 725,778,432 B |
| 30 days | 96 | 259 / 521 | 16 (16.7%) | 90.51s | 712,851,456 B |
| 90 days | 222 | 616 / 1,560 | 17 (7.7%) | 93.83s | 737,198,080 B |

Only 1, 4, and 16 candidates from these packets appeared in the full-corpus top 250. Recency scope
therefore changes the work presented rather than merely truncating a global ranking. The 20-item
default is defensible as reviewer capacity, not corpus coverage.

Runtime did not shrink with the active scope. Candidate generation still traverses the full corpus,
using 77.8–126.7 seconds across these runs. The implementation should constrain eligible active
primaries before ranking while retaining the full closed population as echo evidence.

The scope audit also found a correctness defect: all three incremental packets emitted the same 27
code-surface leads. Code-surface analysis runs before incremental active IDs are applied, so those
leads are currently global even when the semantic packet is scoped. A follow-up bug tracks making
them scope-consistent or explicitly labeling them global.

## Scaling probe

A nested, deterministic, active/closed-stratified hashing-provider probe isolated candidate ranking.
The provider is not a semantic-quality result.

| Records | Active / closed | Pair opportunities | Ranking | Wall time | Peak RSS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2,000 | 413 / 1,587 | 740,509 | 9.56s | 17.86s | 350,879,744 B |
| 4,000 | 826 / 3,174 | 2,962,449 | 22.47s | 26.00s | 423,706,624 B |
| 8,000 | 1,651 / 6,349 | 11,844,274 | 129.91s | 136.53s | 604,143,616 B |

The measured 2K-to-8K ranking exponent was approximately 1.88. This confirms near-quadratic
candidate work and strengthens the existing exact-ranking optimization bead. Approximate indexing
remains gated behind exact optimization and an audited recall target.

## Weak-label recall probe

Weak labels were mined only to design a benchmark; they are not ground truth.

- 211 active-record references to existing issue numbers produced 7 top-250 hits (3.3%).
- 11 strong duplicate/follow-up/related/blocked phrase references produced no hits. A manual
  spot-check found all 11 at least contextual, including same-rule regressions and explicit
  integration follow-ups, making this a small but real recall warning.
- Three exact normalized-title pairs produced two hits.
- 2,497 rare exact-rule-code pairs across 602 codes produced 19 hits, but this set is noisy.
- The union contained 2,689 pairs and 23 top-250 hits (0.86%).
- A generic-token/shared-vocabulary hard-negative probe with disjoint nonempty rule codes contained
  1,424,150 pairs and accounted for 54 of 250 admitted candidates.

GitHub issue-number references may point to pull requests or loose context, and a shared rule code
does not guarantee duplicate intent. The next benchmark step is therefore small and audited: treat
strong phrase references and exact titles as seed positives, manually sample rare-code positives
and generic-token negatives, and compare models only after that gold set exists.

## Decision

Keep `triage --review-budget 20` as the operational default. Do not describe it as representative
corpus evaluation and do not raise it based on this pass. Use the external fixed-pool harness for
rank-depth studies, optimize exact candidate generation before adding ANN infrastructure, and add
identifier-aware verification only behind the audited benchmark.
