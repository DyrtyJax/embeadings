# Ecosystem sweep: semantic search and Beads community tools

Research date: 2026-07-14

## Executive summary

emBEADings already has the right boundary: Beads remains authoritative, the core is read-only, and
semantic output is disposable evidence. The most useful ideas from adjacent projects are operational
and evaluative rather than architectural rewrites:

1. make retrieval quality reproducible against realistic tasks and simple baselines;
2. expose cache/index health, change accounting, and repair commands;
3. prove cache reuse across Git worktrees and workspace moves;
4. keep manifests stable enough for Beads UIs, analytics tools, and agent adapters to consume;
5. benchmark model and storage alternatives before adding a vector database or provider matrix.

## Projects reviewed

### Local semantic search and embedding infrastructure

- **Lumen** uses local embedding servers, Merkle-tree change detection, semantic chunking,
  SQLite/sqlite-vec retrieval, worktree index seeding, health/status tools, and a reproducible
  task-level benchmark harness.
- **Model2Vec** provides the compact static local model used by the MVP. It minimizes inference and
  dependency cost, but its retrieval quality should be tested against stronger ONNX encoders.
- **FastEmbed** provides CPU-oriented ONNX inference with a broader model catalog and is a useful
  quality/performance comparison provider.
- **sqlite-vec** provides embedded KNN search without a vector service. It is attractive only after
  the current file cache becomes a measured bottleneck; it remains pre-1.0 and adds native packaging
  considerations.
- **Qdrant local mode** shows a clean path from in-memory experiments to persistent local search, but
  a vector service/client layer is unnecessary for issue populations at the MVP's scale.

### Beads community tools

- The official community catalog explicitly recommends current tools read through `bd --json`
  instead of legacy `issues.jsonl`, validating the emBEADings adapter boundary.
- **Mardi Gras** treats Beads as the brain and itself as a human-facing lens. Its zero-config
  discovery, workspace identity display, bounded command timeouts, and preserved view state are
  useful UX precedents. Its agent dispatch belongs outside the semantic core.
- **Perles** demonstrates the value of expressive structural filtering and dependency traversal.
  emBEADings should translate Beads-native filters before applying semantics rather than invent a
  competing query language.
- **Thread** demonstrates a strict analytical companion with human and JSON summaries. Its historical
  fidelity/rework signals could become optional counterevidence, but direct Dolt history access must
  not leak into the core live-record adapter.
- **beads-sdk** and several UIs expose change watching, bulk reads, workspace registries, and typed
  contracts. Stable emBEADings schemas can let those tools integrate without importing Python code.
- **BeadHub/aweb** reinforces the separation between analysis artifacts and coordination/dispatch.
  emBEADings should emit bounded handoffs, not become a team server.

## Recommendations

### Original recommendations and current status

This July 2026 sweep helped define the initial roadmap. Several recommendations below are now
shipped; the list is retained as decision history rather than presented as the current queue.

1. **Evaluation harness and baselines — shipped and evolving.** Expand the synthetic corpus into task-level relevance cases.
   Compare Model2Vec with Beads mechanical duplicate search, keyword overlap, and one FastEmbed ONNX
   model. Record recall@k, false-positive categories, cold/warm time, cache behavior, and artifact
   size. Commit raw synthetic inputs and deterministic results.
2. **Explainability and counterevidence — shipped.** Reports should state which canonical fields contributed,
   show structural relationships/differences, and surface parent-child or explicit later-phase
   language as counterevidence. Similarity alone should never be the explanation.
3. **Doctor and cache status — doctor shipped; detailed cache status/repair deferred.** Add read-only diagnostics for Beads compatibility, workspace identity,
   provider/model availability, cache hits/misses/corruption, stale/deleted entries, and output paths.
   Add an explicit repair/purge command that touches only emBEADings state.
4. **Worktree and move tests — partially shipped.** Verify that the Beads `project_id` namespaces state across sibling
   worktrees and repository moves, while different projects never share vectors accidentally.
5. **Structural filter parity — evidence-gated.** Implement the promised status, priority, label, parent, ready, and
   explicit-ID population filters by translating them to allowlisted `bd list --json` operations.
6. **Interoperability contract — shipped.** Publish JSON Schemas and example manifests, with a capability/version
   handshake for consumers. Keep runtime-specific dispatch in separate packages.

### Evaluate before adopting

- **FastEmbed provider:** likely higher retrieval quality at increased model/runtime cost.
- **SQLite/sqlite-vec cache:** potentially simpler bulk lookup and garbage collection at larger scale,
  but unnecessary until JSON file counts or ranking time become measurable problems.
- **Thread enrichment:** useful historical counterevidence when installed, but optional and clearly
  attributed to a separate snapshot.
- **Background refresh:** valuable for interactive UIs, but a daemon conflicts with the weekly,
  disposable review workflow. Finish atomic async runs first.

### Explicitly avoid

- Reading legacy `issues.jsonl` as tracker truth.
- Direct tracker mutation, even when a candidate appears obvious.
- Building a dashboard, coordination server, or custom structural query language in core.
- Adding a remote embedding default or silently falling back to one.
- Replacing the simple cache or batching algorithm without benchmark evidence.

## Product positioning after the sweep

> A local, read-only evidence layer that finds which Beads work deserves another look, explains why,
> and packages the review into bounded, interoperable batches.

This differentiates emBEADings from Beads' mechanical duplicate finder, UI search, historical
analytics, and agent orchestration while leaving clear integration points for each.

## Primary sources

- [Beads community tools](https://github.com/gastownhall/beads/blob/main/docs/COMMUNITY_TOOLS.md)
- [Beads architecture](https://github.com/gastownhall/beads/blob/main/docs/ARCHITECTURE.md)
- [Lumen](https://github.com/ory/lumen)
- [Model2Vec](https://github.com/MinishLab/model2vec)
- [FastEmbed](https://github.com/qdrant/fastembed)
- [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [Mardi Gras](https://github.com/quietpublish/mardi-gras)
- [Perles](https://github.com/zjrosen/perles)
- [Thread](https://github.com/jklenk/thread)
- [beads-sdk](https://github.com/HerbCaudill/beads-sdk)
