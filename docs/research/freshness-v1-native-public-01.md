# Freshness v1 native public diagnostic 01

Date: 2026-07-25

Verdict: **revise; do not promote the shadow policy.**

This contained diagnostic reused the public native tracker from
[`gastownhall/beads`](https://github.com/gastownhall/beads). It is relationship-heavy evidence from
an in-band open-source corpus, not maintainer consent, customer evidence, or a completed ICP
engagement.

## Corpus and containment

- Source checkout: `96522c1e93bd83ca8850b493d9da61bbde398471`
- Native tracker ref: `refs/dolt/data` at
  `696de12d0f7e2cec04f5d3bde3e531f1827e7e66`
- emBEADings checkout: `5a8873899328a5d94f0c0572c5352dadc1f4abf9`
- Beads: 1.0.5
- Model: `minishlab/potion-base-8M` at
  `bf8b056651a2c21b8d2565580b8569da283cab23`
- Public all-record export: 2,188 issues plus 5 memories
- Live emBEADings snapshot: 2,187 records and 786 typed relationships
- Regular issue export: 1,887 records and 692 typed relationships
- Durable semantic population: 1,886 records
- Excluded from durable review: 301 ephemeral records and 7 active epics
- Active non-epic review population: 90

The source and Dolt snapshot were bootstrapped into the operating system's disposable temporary
directory. Beads correctly rejected `/private/tmp` as an unsafe explicit context on macOS; the run
therefore used the OS-designated `/var/folders` temporary root. Bootstrap created the expected
ignored local database and configuration inside the disposable clone before fingerprints were
recorded.

Every issue-bearing emBEADings command then ran with Hugging Face, Transformers, and Datasets
offline flags under the network-restricted execution sandbox. Model artifacts were prepared before
the tracker was loaded. Cache, state, reports, ratings, and the shadow packet stayed outside both
source repositories.

The regular logical export was byte-identical before and after:
`9088afa57ed51d1e8c5404e0b24f1a2d644dc97ced7c365be370251ef7e1ffb0`.
The disposable source checkout remained Git-clean at the same revision.

## Deterministic baseline

A cold and warm `triage --review-budget 250` run produced the same 87 candidates, 10 code-surface
leads, candidate ordering, collision ordering, and analysis fingerprint:
`45cbd4bb620acfb638abed3976559259857dec5294ca771a47300ef742044edd`.

| Measure | Cold | Warm |
| --- | ---: | ---: |
| Wall time | 7.31s | 4.70s |
| Cache hits / misses | 0 / 1,886 | 1,886 / 0 |
| Dependency candidates | 4 | 4 |
| Completed-work echoes | 73 | 73 |
| Possible overlaps | 10 | 10 |

The queue did not reach the requested 250-item ceiling: only 203 pairs qualified before
deterministic per-issue and completed-target diversity gates, and 87 were admitted. The budget
remained a ceiling rather than a coverage promise.

## Freshness shadow result

The same immutable 87-candidate sequence fed both policies. Cold and warm freshness packets were
byte-identical, with shadow fingerprint
`6851d21934a76189dba5480493e6c23cc51e3e824c7c9d5dafa0da87e968442d`.

| Likely action | Count |
| --- | ---: |
| `superseded-open` | 1 |
| `intentional-follow-up` | 9 |
| `uncertain` | 77 |
| `duplicate` | 0 |
| `missing-relation` | 0 |

Only one pair entered the action tier. It was an exact normalized active/closed title and outcome
match, and the bounded review agreed that `superseded-open` was the correct action category. Nine
directly related or reverse-consumer-explained pairs moved from legacy positions 24–70 to freshness
positions 79–87.

That conservative demotion is useful, but it did not make the operational top 20 more action-dense:
the freshness and legacy top-20 membership and order were identical. The action candidate was
already first in the legacy ranking.

## Bounded internal rating

One emBEADings maintainer reviewed the first 80 pairs using public titles, current descriptions,
lifecycle, and exact relationship facts. The first 20 were the predeclared release-gate sample. The
next 60 were then reviewed in the original immutable legacy order before freshness labels and
positions were revealed. This was an internal review rather than an independent precision result.

| Gate | Top 10 | Target | Top 20 | Target |
| --- | ---: | ---: | ---: | ---: |
| Actionable precision | 5 / 10 (50%) | 70% | 6 / 20 (30%) | 60% |
| Useful precision | 10 / 10 (100%) | 90% | 15 / 20 (75%) | 80% |
| Likely-action category accuracy | 6 / 10 (60%) | 90% | 15 / 20 (75%) | 80% |
| Relationship-explained false concerns | 0 | 0 | 0 | at most 2 |

The policy therefore passes conservative counterevidence handling but fails the action-density,
top-20 usefulness, and category-accuracy gates on this corpus.

### Long-tail diagnostic

The additional review did not rerun triage with a larger budget. It rated legacy positions 21–80
from the same sealed 87-candidate artifact, preserving the original candidate set and order.

| Legacy band | Actionable | Useful | Misleading |
| --- | ---: | ---: | ---: |
| 21–40 | 1 / 20 (5%) | 12 / 20 (60%) | 8 / 20 (40%) |
| 41–60 | 2 / 20 (10%) | 15 / 20 (75%) | 5 / 20 (25%) |
| 61–80 | 2 / 20 (10%) | 9 / 20 (45%) | 11 / 20 (55%) |
| 21–80 | 5 / 60 (8.3%) | 36 / 60 (60%) | 24 / 60 (40%) |
| 1–80 | 11 / 80 (13.8%) | 51 / 80 (63.8%) | 29 / 80 (36.3%) |

The lane split explains part of the result. All 9 overlap candidates in positions 21–80 were useful
and 3 were actionable. All 4 dependency candidates were useful context but none required a tracker
change. The 47 echo candidates yielded 23 useful and 2 actionable reviews. The lowest band fell to
45% useful, showing the expected decay rather than a hidden reserve of high-density actions.

After ratings were sealed, freshness output showed that all nine relationship-explained
`intentional-follow-up` pairs in this band had been moved to positions 79–87. The review agreed that
none required tracker action; eight were useful context and one was misleading even as context.
That is a successful demotion. Conversely, all five actionable tail pairs remained `uncertain`.
They comprised one exact-reference lineage miss, two unlinked active scope overlaps, and two
active/closed implementation echoes whose prior outcome could change the active work.

The practical conclusion is not to raise the default queue from 20 to 80. A larger queue buys
discovery breadth at sharply lower action density. The product should expose a sparse, evidence-led
action queue and make the longer informational/discovery lane an explicit opt-in with its own
budget and stopping signal.

## Missed evidence

Seven candidates contained an exact local reference to the other issue but remained `uncertain`.
The bounded cue vocabulary did not recognize common lineage phrases observed in this public tracker:

- “decision from”;
- “split from”;
- “re-review” and “found by … re-review”;
- “removed … but” as a continuation of a completed repair; and
- “from … adversarial review.”

Five of these missed reference pairs appeared in the top 20. Broadening the matcher to a generic
word such as “from” would create unacceptable noise; any expansion should add narrow multiword
phrases with positive and hard-negative tests.

The result also exposes a packaging problem in the evaluation output: when only one pair qualifies
for the action tier, filling the remainder of a nominal top 20 with `uncertain` informational pairs
makes the queue look denser than the policy's own evidence supports. A freshness artifact should
report a sparse action queue honestly and place uncertain or relationship-explained pairs in a
separate informational section.

The 60-pair extension strengthens this conclusion: enlarging the mixed queue reduced action
precision from 30% in the first 20 to 8.3% in the next 60. Informational results remain useful for
research and tracker archaeology, but they should not silently consume an operational review
budget.

## Decision

Keep freshness-v1 shadow-only. Count this as the additional public relationship-heavy corpus for the
three-corpus protocol, but do not close the promotion gate. Before the next field run:

1. add narrowly audited lineage cues for the observed exact-reference false negatives;
2. separate the action queue from informational fallback instead of backfilling to 20;
3. rerun this immutable public snapshot to measure category recall and queue membership changes; and
4. retain the consenting native-Beads ICP and matched private evaluation as independent promotion
   requirements.
