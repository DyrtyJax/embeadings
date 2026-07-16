# Native Beads public scale diagnostic 01

Date: 2026-07-16

This is a public-corpus diagnostic, not a completed ICP engagement. The public
[`gastownhall/beads`](https://github.com/gastownhall/beads) tracker is native Dolt-backed Beads data
and its team visibly uses typed dependencies and multi-agent workflow records. No maintainer has yet
consented to the evaluation protocol or said whether they would repeat it.

## Corpus and safety

- Source checkout revision: `67652d8b5caf73ce6c1728d8efe621277ad2af24`
- Beads: 1.0.5; emBEADings model: `minishlab/potion-base-8M` at pinned revision
  `bf8b056651a2c21b8d2565580b8569da283cab23`
- Native tracker: 2,162 total records reported by Beads; emBEADings evaluated the 2,161 normal
  records returned by `bd list --all` (the omitted record was Beads infrastructure)
- Typed dependencies in the evaluated snapshot: 783 (506 parent-child, 237 blocks,
  37 discovered-from, 3 related)
- Durable review population after default filtering: 1,860 records, including 77 active non-epics
- Excluded by review policy: 301 `ephemeral: true` runtime records and 7 active epics
- All issue-bearing commands ran with Hugging Face and Transformers offline flags after model
  preparation. Vector cache, state, and reports stayed under `/private/tmp`.
- Canonical live issue fingerprint and Git-status fingerprint were unchanged. An isolated warm
  emBEADings repeat also left the settled `.beads` physical-content fingerprint unchanged. Earlier
  setup and direct Beads reads changed embedded-Dolt physical files without changing logical or
  Git-visible state, so this run does not claim strict physical immutability across setup.

## Evaluator-driven correction

The first 50-candidate run included 26 recurring patrol wisps. They were exact template copies and
valid execution instances, but misleading durable-backlog candidates. The corpus exposed that the
adapter discarded Beads' `ephemeral` field. The corrected default preserves that field in acquisition
and checkpoint state, excludes ephemeral records from semantic and collision populations, reports the
exclusion, and offers `--include-ephemeral` for deliberate runtime analysis.

## Corrected run

| Measure | Cold | Warm |
| --- | ---: | ---: |
| Wall time | 3.89s | 1.60s |
| Report duration | 3.59s | 1.47s |
| Embedding/cache phase | 1.63s | 0.55s |
| Candidate analysis | 0.18s | 0.15s |
| Cache hits / misses | 0 / 1,860 | 1,860 / 0 |
| Peak RSS | 203 MB | 187 MB |

Candidate arrays, ordering, scores, code-surface analysis, and analysis fingerprints were identical
between cold and warm runs. The packet admitted 50 candidates: 37 echoes, 10 semantic overlaps, and
3 typed-dependency candidates. It separately emitted 10 explicit exact-file collision leads.

## Bounded manual rating

One emBEADings developer reviewed all 50 candidate title/outcome pairs without using the embedding
score as the rating:

- rating 2, strongly related/actionable: 27
- rating 1, contextually useful coordination: 18
- rating 0, misleading: 5
- at least useful: 45 / 50 (90%)

The strongest results were explicit follow-ups, duplicated bug statements, implementation/re-review
pairs, and narrow cross-backend contracts. The five false positives paired generic Git operations,
backend names, or process-review vocabulary without a shared remaining outcome. This rating is a
single internal review, not a maintainer judgment.

Nine of ten explicit exact-file leads looked worth coordinating; one was a broad `cmd/bd/main.go`
reference without a clear shared edit. Collision coverage remains limited: zero active worktrees were
mapped, so all ten leads are explicit references and none proves a live observed edit.

## Decision

The corpus validates native typed-graph ingestion, exact incremental ranking performance, and the
need for lifecycle-aware filtering. It does not close the ICP Bead. Completion still requires
maintainer consent, an independently rated packet, and an answer to whether the team would repeat the
workflow. Until then, call this a strong public diagnostic rather than customer evidence.
