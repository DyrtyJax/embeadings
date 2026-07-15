# Decision: retain Model2Vec and the file cache for the MVP

Status: accepted for 0.1.x on 2026-07-15.

## Decision

Keep the pinned `minishlab/potion-base-8M` Model2Vec provider and content-addressed JSON vector cache
as the default MVP architecture. Keep FastEmbed and sqlite-vec as optional benchmark dependencies,
not runtime dependencies. Revisit the provider after a larger blinded quality benchmark; revisit
storage when representative workspaces exceed 5,000 records or measured cache I/O exceeds one second
or 20% of warm sweep time.

## Evidence

The reproducible public result is in
`benchmarks/results/alternatives-apple-arm64-2026-07-15.json`. It used 24 synthetic paraphrase and
hard-negative records plus 1,000- and 5,000-record storage fixtures. Both providers were deterministic
and completed an offline, OS-network-denied repeat after prefetch.

| Signal | Model2Vec | FastEmbed BGE-small |
| --- | ---: | ---: |
| Pair recall@1 | 70.8% | 100% |
| Cold initialization + encode | 634 ms | 485 ms |
| Warm encode, 24 records | 1.2 ms | 92.1 ms |
| Peak RSS, isolated process | 142 MB | 334 MB |
| Model cache | 123 MB | 134 MB |

FastEmbed's quality result is promising but the fixture is intentionally small and does not justify a
provider migration. It used roughly 2.4 times the peak resident memory and added ONNX Runtime plus a
larger dependency surface. The current pinned provider remains substantially faster after loading and
already has private- and public-corpus evidence behind its thresholds.

| Storage, 5,000 × 256-d vectors | JSON files | sqlite-vec |
| --- | ---: | ---: |
| Write | 2,413 ms | 135 ms |
| Full read | 594 ms | 28 ms |
| Disk | 5.95 MB | 5.39 MB |

sqlite-vec is materially faster and supports KNN, but emBEADings currently loads vectors once and
performs deterministic in-memory scoring. At 5,000 records the file cache remains below the one-second
read threshold, is transparent, content-addressed, easy to repair, and avoids a pre-v1 native SQLite
extension. Moving now would add schema migration and cross-platform packaging costs without addressing
the observed warm bottleneck, which is usually Beads acquisition rather than vector loading.

## Follow-up gates

- Repeat provider quality on at least 200 anonymized public/synthetic pairs covering vocabulary shift,
  sparse titles, architecture vocabulary, and hard negatives.
- Profile acquisition, model load, cache I/O, candidate analysis, and sandbox filesystem latency in
  separate processes over at least five uncontended repeats.
- Reconsider sqlite-vec when cache reads exceed the threshold above, when incremental KNN replaces the
  full score matrix, or when a single-file transactional cache materially improves repair behavior.
- Any migration must preserve pinned revisions, offline operation, deterministic ordering, external
  cache placement, and the rule that issue text never leaves the machine.

FastEmbed uses ONNX Runtime according to its official project documentation. sqlite-vec is a compact
SQLite vector extension with `vec0` tables, but its own documentation marks the current line as pre-v1;
both facts are part of the packaging decision rather than performance claims.
