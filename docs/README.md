# Documentation

emBEADings is a read-only evidence layer for Beads and Linear. Start with the task you are trying to
complete; the research reports are supporting evidence, not required setup reading.

## Use the CLI

- [Project overview and quick start](../README.md)
- [Synthetic output examples](../examples/README.md)
- [Linear adapter](linear.md)
- [Safe offline evaluation](evaluation.md)
- [Performance and scale behavior](performance.md)

The complete command and policy contract lives in the
[product and technical specification](spec.md). Run `embead --help` or `embead COMMAND --help` for the
installed version's exact flags.

## Integrate with emBEADings

- [Consumer compatibility and capability contract](consumer-contract.md)
- [Version 1 JSON Schemas](../schemas/v1/)
- [Agent plugin developer preview](../plugins/embeadings/README.md)

Consumers should negotiate `schema_version` and capabilities rather than inferring support from a
package version. Reports are advisory and must not grant tracker-write authority to a consumer.

## Evaluate a repository

- [Private code-surface protocol](evaluation-code-surfaces.md)
- [Private Linear protocol](evaluation-linear.md)
- [Large-corpus and ICP protocol](evaluation-large-corpus.md)
- [Ranked evaluation preparation](../scripts/prepare_ranked_evaluation.py)

Keep raw tracker data, worktree mappings, reports, caches, prompts, and ratings outside both the
embeadings checkout and the evaluated repository. Publish only aggregate results that the repository
owner has approved.

## Understand the design

- [Product and technical specification](spec.md)
- [Ecosystem sweep](ecosystem-sweep.md)
- [Embedding and storage decision](decisions/embedding-storage-alternatives.md)
- [Review-budget default decision](decisions/review-budget-default.md)
- [Research and evaluation ledger](research/README.md)

Older research reports preserve the evidence available at the time. Prefer the index's status and
newest decision report when an early pilot and current behavior differ.

## Project stories

- [The release gate stopped the release twice](articles/dogfooding-v040-worktree-gate.md) — a candid
  account of the v0.4.0 four-worktree dogfood gate and the two defects it exposed.
