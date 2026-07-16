# Review-budget default

Status: **keep the fixed 20-candidate triage default; evaluate corpus-aware sizing as opt-in.**

Date: 2026-07-16

## Decision

`triage` keeps a default review budget of 20. The number is a reviewer-capacity limit, not a claim that
20 pairs represent a corpus or provide a recall estimate. Total corpus size is the wrong input: closed
records are evidence for active work, and pair opportunities grow much faster than record count.

The existing Ruff evaluation supports this boundary. Its 8,143-record surrogate produced 13,274
qualified semantic pairs but a 20-pair operational packet; 17 of those 20 were at least contextually
useful. A separate fixed 250-pair pool was required to study rank depth. The lower bands remained
useful, but the study did not measure whether a maintainer would routinely review 30–50 items or gain
more actionable findings per minute. The report therefore concluded that 20 is defensible as reviewer
capacity, not corpus coverage.

An adaptive default would also change queue membership because lane reservations and caps make runs
with different budgets non-prefixes. Changing the default before a native-Beads ICP review would trade
a clear workflow promise for an unvalidated percentage.

## Candidate opt-in policy to evaluate

If corpus-aware sizing is tested, derive it from the active review population after status, epic,
ephemeral, and incremental-scope filters—not from total active-plus-closed records:

```text
eligible_active = active records eligible as review primaries
candidate_limit = min(50, max(20, ceil(0.03 * eligible_active)))
```

This deliberately preserves 20 for up to 666 eligible active records, grows to 30 at 1,000, and caps
at 50 near 1,667. The cap protects reviewer attention; the percentage is a bounded experiment, not a
statistical sampling claim. Explicit numeric `--review-budget N` values must continue to win.

Any opt-in implementation must:

- preserve the current dependency/echo/overlap reservation and priority policy;
- keep code-surface leads outside the semantic candidate limit;
- record the eligible-active count, rate, floor, cap, and effective limit in the report;
- use changed active records as the basis for incremental runs while retaining closed evidence;
- remain deterministic for the same canonical snapshot and filters; and
- compare one fixed candidate pool across rank bands rather than treating separate budget runs as
  strict prefixes.

## Promotion gate

Do not make adaptive sizing the default until a consenting 2,000–10,000-record native-Beads ICP and
at least one public surrogate compare fixed-20 and adaptive packets using blinded usefulness ratings,
actionable findings per reviewer minute, unique active-record coverage, lane mix, completion rate, and
abandonment. Promotion requires a repeatable workflow benefit without materially reducing actionable
precision; a larger queue by itself is not success.

Evidence: [Ruff review-depth evaluation](../research/ruff-review-depth-02.md) and
[large-corpus/ICP protocol](../evaluation-large-corpus.md).
