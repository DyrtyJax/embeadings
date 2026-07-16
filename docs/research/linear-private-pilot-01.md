# Private Linear pilot 01: aggregate findings

Evaluation date: 2026-07-15

This report contains only aggregate measurements and failure patterns supplied by the repository
owner. No issue or team identifiers, issue text, labels, file paths, symbols, snippets, branch names,
worktree locations, raw reports, credentials, or repository fingerprints were copied into
emBEADings.

## Verdict

Revise before presenting the default weekly sweep as a reduced coordination queue. The read-only
Linear acquisition reproduced the expected telemetry, and explicit exact-file collisions added
information that the tracker's relation graph did not. The 20-candidate default queue, however, was
entirely occupied by existing typed relations. Qualified echo and overlap candidates received no
capacity, so the artifact contained no novel semantic relationships.

The differentiated product in this corpus was conservative code-surface coordination. Semantic
similarity remained an advisory prefilter, and typed dependencies were useful context but low
marginal value because Linear already exposed them.

## Corpus and funnel

- 1,246 issues and 502 canonical relationships were acquired.
- Relationship types were 104 blocks, 48 duplicate-of, and 350 relates-to.
- 102 workspace relations with endpoints outside the selected team were omitted.
- The 20-candidate weekly queue entered entirely through the dependency lane.
- 108 echo and 64 overlap pairs qualified but received no admission under the former dependency-first
  total-budget policy.
- 253 qualified pairs were omitted by the run cap, and 112 active records had no accepted signal.
- Explicit extraction found 112 code pointers and produced 22 collision leads.

The evaluator independently reproduced these counts using the native Linear source, an isolated
external store, and a short-lived credential.

## Evidence quality

Typed relationships were faithful but mostly duplicated Linear's own relation panel. Roughly one
quarter of the reviewed dependency candidates were rated as actionable coordination; the remainder
were primarily useful existing context.

No-edge semantic precision was weaker. Approximately 40% of reviewed echo/overlap pairs were at least
contextually useful, while an estimated 10–15% were actionable. Shared domain vocabulary and repeated
closed-issue targets dominated the false positives. Generic verification prose did not identify a
candidate-specific fact or contract.

Explicit code-surface evidence was the strongest differentiated lane. Every reviewed pair shared the
reported file, and an estimated 55–65% represented a likely edit collision. The useful leads exposed
sequencing or shared-implementation hazards without an existing relation edge. Remaining noise came
from hierarchy-redundant pairs and broad shared files near the hub boundary.

Only one worktree existed, so observed-to-observed behavior was not evaluated. A deliberately old
base produced 1,344 observed pointers and 51 noisy collision leads, demonstrating the need for a
bounded committed-diff circuit breaker. This result does not establish that smaller diffs use the
correct base; repository owners must still verify their intended integration reference.

## Decisions

1. Reserve weekly capacity across dependency, echo, and overlap lanes before applying the normal
   priority pass. Keep code-surface leads outside the semantic candidate limit.
2. Accept a canonical Linear team UUID directly, while retaining paginated exact key/name lookup.
3. Surface selected-team relation omissions by direction and type in both warnings and structured
   snapshot diagnostics. Do not fetch external records implicitly.
4. Require explicit worktree mappings to target active included records and return a corrective error
   for filtered or closed identifiers.
5. Exclude committed ranges above 250 eligible paths while retaining current tracked and untracked
   changes. Describe this as a volume guard, not staleness detection.
6. Abstain from candidate-specific semantic claims unless both records corroborate the bounded
   category; present existing typed relations as tracker context rather than novel evidence.

The follow-up protocol is documented in
[Private Linear regression evaluation](../evaluation-linear.md). A full worktree release gate still
requires at least two genuine concurrent implementation worktrees.
