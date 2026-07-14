# Private pilot 01: aggregate findings

Evaluation date: 2026-07-14

This report contains only anonymized aggregate measurements supplied by the repository owner. No
issue IDs, titles, descriptions, labels, repository paths, raw reports, vectors, or tracker exports
were copied into this repository.

## Environment

- Beads 1.0.5 and emBEADings 0.1.0.
- 879 issues: 224 active-status records and 655 closed records.
- Pinned `minishlab/potion-base-8M` model at revision
  `bf8b056651a2c21b8d2565580b8569da283cab23`.

## Safety and determinism

- Tracker fingerprint unchanged.
- Git status unchanged.
- No files created inside the analyzed repository.
- No issue-content network activity observed; only pinned model artifacts were fetched.
- Warm batch membership, candidates, ordering, and scores matched the initial run.

## Performance

| Measurement | Initial | Warm |
|---|---:|---:|
| Runtime | 46.5 s | 45.5 s |
| Cache hits | 0 | 879 |
| Cache misses | 879 | 0 |

The cache behaved correctly but saved only about one second. Full-corpus pairwise comparison and
dense-seed batching, rather than embedding inference, dominated runtime.

## Neighbor relevance

Seven representative queries produced 56 manually rated results:

| Rating | Count | Share |
|---|---:|---:|
| Strongly related | 31 | 55% |
| Contextually related | 15 | 27% |
| Irrelevant or misleading | 10 | 18% |

Overall, 82% were at least contextually relevant. Completed-work echoes, narrow same-subsystem work,
same-outcome records, and parent/child relationships performed best. Broad UI, workflow,
infrastructure, and lifecycle vocabulary produced most false positives.

## Default sweep

- 45 batches and 136 candidates: 119 completed-work echoes and 17 possible overlaps.
- Mean and median batch coherence were both 3 out of 5.
- 27 batches were at least moderately coherent; 17 were clearly coherent.
- 18 batches mixed unrelated work and required substantial reviewer triage.
- Parent/child grouping was often useful, while broad epics reduced focus.
- Every candidate included a verification prompt, but prompts came from only two generic templates
  and did not identify the concrete contract or evidence to inspect.

The default completed-work threshold appeared reasonable. The overlap threshold missed at least one
strong active overlap and one meaningful parent/child relationship.

## Threshold sensitivity

Permissive thresholds added 1,336 candidates, increasing the total from 136 to 1,472. Approximately
65% of sampled additions were at least contextually useful, but the volume was impractical. False
positives increasingly reflected broad subsystem language, generic architecture/lifecycle wording,
boilerplate implementation phrasing, and shared entities without shared outcomes.

A global threshold reduction is therefore the wrong control. Lower thresholds should require
structural corroboration, reciprocal-neighbor evidence, or a bounded per-issue candidate cap.

## Decisions

1. Keep the current pinned Model2Vec provider and default thresholds as the high-signal baseline.
2. Optimize similarity and batching before evaluating a heavier provider or vector store.
3. Batch high-signal review candidates; report unmatched records as `no signal` instead of forcing
   every active issue into a neighborhood.
4. Add structurally aware ranking or threshold exceptions and bound candidate volume.
5. Generate evidence-specific explanations from field-level semantic contribution, structural
   context, lifecycle contrast, and counterevidence.
6. Exclude broad epics from the default review population or clearly discount parent/child similarity.

## Product implication

> emBEADings should produce a bounded queue of high-signal review leads, not partition the entire
> backlog merely because every issue has a nearest neighbor.

