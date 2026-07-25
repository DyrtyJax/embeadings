# Freshness v1 shadow protocol

Status: implemented shadow policy v2; not a product default and not sufficient precision evidence.

The freshness experiment asks a narrower question than semantic similarity: which retained review
pairs plausibly call for tracker action, and which are already explained by current relationships?
It reuses one immutable candidate pool from the existing ranking engine. It does not add another
embedding model, public objective, CLI flag, or schema field.

## Shadow policy

The internal policy emits one finite action label:

- `duplicate`;
- `superseded-open`;
- `missing-relation`;
- `intentional-follow-up`; or
- `uncertain`.

It also separates `action` from `informational` review. Exact normalized identity can support the
first two action labels. A missing-relation label additionally requires an exact local issue-ID
reference, a bounded relationship cue, complete relationship scope, and no direct explanatory edge.
Cosine similarity alone cannot establish any lifecycle action.

The v2 packet exposes independently budgeted `action` and `informational` queues. Each queue reports
available, emitted, and omitted counts plus whether it stopped because the source was exhausted or
its budget was reached. Informational candidates never backfill a sparse action queue. The complete
immutable ranked pool remains available for evaluation and position audits.

Audited lineage cues include narrow forms such as “decision from,” “split from,” “re-review,” and
“from … adversarial review” adjacent to an exact issue ID. Generic “from,” ordinary review language,
documentation citations, historical notes, and coincidental substrings remain hard negatives.

Direct parent/child, `blocks`, `depends-on`, and `discovered-from` evidence is informational
counterevidence. A third-party active incoming consumer is also counterevidence. Pair-local
relationships and the active-consumer fact use the full deduplicated edge index; persisted context
remains bounded to four incoming and four outgoing ID/type receipts per endpoint with omission
counts. Unknown relationship types remain unknown.

If structural analysis is degraded, exact identity may still be inspected, but absence-based
missing-relation conclusions are suppressed.

Semantic candidates retain finite receipts for overlap versus completed-work echo and for
semantic-threshold versus reciprocal local-evidence admission. These receipts improve uncertainty
audits but do not promote a pair: the native public long-tail replay found no safe rule that
distinguished four actionable semantic-only pairs from misleading matches without a concrete local
contract.

## Privacy and product boundary

Classification can inspect tracker text locally, but its result contains only endpoint IDs, finite
evidence codes, relationship types, omission counts, ranks, and aggregate metrics. It never emits
matched text, titles, bodies, paths, or snippets. The helper is available only as a Python evaluation
primitive in `embead.freshness_evaluation`; normal `triage` behavior is unchanged.

One source candidate sequence feeds both legacy and freshness positions. The top 10 is therefore a
strict prefix of the top 20 instead of being regenerated under different budgets. Queue budgets
only control emitted review prefixes; they never regenerate or mutate the source pool.

## Promotion gates

Rate the same blinded pool under both policies and report:

| Gate | Top 10 | Top 20 |
| --- | ---: | ---: |
| Actionable precision | at least 70% | at least 60% |
| Useful precision | at least 90% | at least 80% |
| Likely-action category accuracy | at least 90% | at least 80% |
| Relationship-explained false concerns | 0 | at most 2 |

The freshness review must preserve known exact duplicates and missing-relation positives, classify
the reverse-edge checklist counterexample as informational, and take no more than 25 reviewer
minutes or improve review time by at least 25%. Promotion requires three relationship-heavy corpora,
including two above 1,000 records, with no material recall loss.

## Initial dogfood receipt

The first local shadow run used this repository's complete three-candidate self-triage pool. It
classified two completed-work echoes as intentional follow-ups because active incoming consumers
explained them, and left the third uncertain. It promoted no action candidates. The packet was
deterministic and reported one omitted bounded-context edge across five reviewed endpoints.

That result is a wiring and counterevidence check, not a precision estimate: three candidates are too
few, the maintainer was not blinded, and the hashing provider was used only to construct the source
pool. The next evidence must come from the matched private evaluation and native Beads ICP.
