# Objective-default decision from three public corpora

Date: 2026-07-16  
Evaluated release: emBEADings 0.3.0 at `7f0cbbbf9b767f388e506772ce27e520b2a90ca3`

## Decision

Keep the legacy reflowing selector as the default. Combined objective mode is a safe, opt-in
provenance overlay, but fixed semantic/structural artifacts must not replace the default queue.

All three evaluators found the combined-objective queue candidate-identical to legacy: same 20
pairs, order, scores, lanes, and batches. Fixed split budgets underfilled whenever structural supply
was below its reservation and did not return unused capacity to semantic review.

| Corpus | Reviewable typed candidates | Legacy | Combined | Fixed split | Rating-2 leads displaced by split |
| --- | ---: | ---: | ---: | ---: | ---: |
| Morphir | 0 | 20 | 20 | 8 | 8 |
| opencode-beads | 0 | 20 | 20 | 8 | 11 |
| ralph-tui | 4 | 20 | 20 | 12 | 3 |

The split therefore discarded 22 concrete coordination leads across the three evaluations. Its
occasional precision increase came from reviewing fewer candidates, not from discovering better
coverage. The Ralph result shows the failure is not limited to structure-free corpora: a sparse
structural lane can still strand most of its fixed reservation.

## What remains useful

- Objective labels make retrieval provenance and abstention easier to inspect without changing
  queue membership.
- The single-queue reservation policy provides minimum lane access and then deterministically
  reflows unused capacity in dependency, echo, overlap order.
- A separate structural artifact remains useful as an explicit diagnostic when requested; it is not
  a replacement for the bounded mixed review.
- Hub conservation and backfill receipts remained deterministic and internally reconciled. Ralph's
  forced-cap audit also confirmed the receipt identity namespace documented in the consumer contract.

## Defects exposed by the evaluation

The public gate found two implementation gaps independent of the default decision:

1. Current weekly sweep reports contained review-budget and lane receipt fields missing from the
   bundled v1 schema.
2. Structure-only runs embedded every record even when no active typed relationship could possibly
   enter review.

The follow-up restores producer/schema parity with a producer-shaped regression and skips semantic
vector/cache work only when the structural comparability gate is empty. It does not change candidate
selection. Reports retain an explicit skip receipt and the complete dependency funnel.

## Safety note

Logical tracker data, tracked files, and Git status remained unchanged. One evaluator again observed
mtime-only changes to three ignored embedded-Dolt files during read-only Beads access; hashes, sizes,
and logical state were unchanged. Compatibility tests should continue to distinguish storage-engine
metadata churn from tracker mutation.
