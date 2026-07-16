# Large-corpus evaluation and ICP protocol

This protocol tests emBEADings on 2,000–10,000 work records without confusing corpus size with
product fit. A public GitHub issue export can establish runtime, memory, determinism, review-budget,
and failure-mode behavior. It cannot validate typed Beads relationships, real agent workflows, or
whether a team acts on the resulting review queue.

## Ideal customer profile

The primary evaluation partner is a team with:

- 2,000–10,000 native Beads records, including meaningful active and completed populations;
- typed parent, dependency, or sequencing relationships;
- multiple agents or developers working concurrently in one codebase;
- recurring tracker hygiene or coordination review work;
- permission to run local, read-only analysis and share aggregate ratings; and
- at least two genuine active implementation worktrees when testing observed collision evidence.

The success measure is not nearest-neighbor cleverness. It is whether a bounded, reproducible queue
finds coordination risks or completed-work echoes that would otherwise cost reviewer time.

## Public scale surrogate

When no consenting native-Beads corpus is available, use a public GitHub repository in the target
size band. Keep the converted database outside both repositories and label every result as a
`github-scale-surrogate`. The conversion has no typed dependencies unless a separate, audited import
supplies them, so the dependency lane is expected to be empty.

The repository includes an evaluation-only exporter. It uses the authenticated GitHub CLI GraphQL
API, fetches issue records but not pull requests or comments, truncates large bodies, and writes a
deterministic flat Beads JSONL file outside the emBEADings checkout:

```console
python scripts/prepare_github_evaluation.py \
  --repo astral-sh/ruff \
  --output /external/ruff-github/issues.jsonl

mkdir -p /external/ruff-beads/.beads
cp /external/ruff-github/issues.jsonl /external/ruff-beads/.beads/issues.jsonl
cd /external/ruff-beads
bd init --from-jsonl --prefix ruff --skip-agents --skip-hooks
embead triage --review-budget 20 --output /private/tmp/ruff-embead-triage
```

Do not commit the export or generated Beads database. Before and after each run, fingerprint the
JSONL, tracker export, Git status, and external cache/state directories.

Converted issue text is not code-repository provenance. Unless the disposable tracker is genuinely
attached to a checkout of the evaluated source repository, rate semantic candidates only and treat
code-surface output as a grounding diagnostic. Missing repository paths and fenced reproduction
filenames must not be reported as known edit collisions.

## Required measurements

Record:

- source repository, immutable export digest, issue count, active/closed split, and import caveats;
- cold and warm wall time, peak memory, cache hits/misses, and model revision;
- byte equality of the compact packets and equality of analysis fingerprints;
- admitted, qualified, and omitted counts by evidence lane;
- output size and whether the review budget remains hard;
- a blinded rating of every admitted candidate, plus a deterministic omission sample;
- generic filename, documentation-reference, vocabulary-only, and lifecycle false positives; and
- tracker, repository, cache, and network non-mutation checks.

Run the lightweight hashing provider only to diagnose pipeline scale. It does not count as a semantic
quality result. The release-quality pass must use the pinned default model and state that a GitHub
surrogate contains no native dependency graph.

## Decision gates

A scale surrogate passes when the command finishes within a documented operator budget, stays within
available memory, produces deterministic bounded artifacts, and preserves non-mutation. A native
Beads ICP passes only when reviewers also find the queue useful enough to repeat and observed
collision behavior is exercised honestly. Never fabricate worktree mappings or promote converted
GitHub issues as native-Beads validation.

## Initial public scale observation

On 2026-07-16, the exporter produced 8,143 public `astral-sh/ruff` issues: 1,681 active and
6,462 closed. The JSONL SHA-256 digest was
`ebee4dfcb7cb59119a8e1e4ded898745fea3d89c090b5b9c7804a5d6155d0309`. A hashing-provider
diagnostic admitted exactly 20 semantic candidates and emitted 27 separately budgeted code-surface
leads. Two post-fix warm runs produced byte-identical 49 KB triage packets with analysis fingerprint
`4739cf560e743ad36a0b5aac6d4fdc8d064409b12acc9c946b14699597861328`.

End-to-end wall time was 82–95 seconds and peak resident memory was 608–633 MB. In the second run,
candidate analysis accounted for 87.9 seconds while similarity scoring took 0.3 seconds. This is a
pipeline observation, not a relevance score: the hashing provider is intentionally unsuitable for
semantic quality claims. It confirms that the current Python candidate-ranking path, already tracked
by the large-corpus performance bead, is the primary scale bottleneck.

The pinned `minishlab/potion-base-8M` model then completed a cold run in 118 seconds at 738 MB peak
resident memory. Acquisition took 6.2 seconds, embedding and cache work 14.5 seconds, similarity
scoring 0.6 seconds, and candidate analysis 95.2 seconds. The bounded packet contained 16 echoes and
4 overlaps. A brief maintainer inspection found both strong duplicate/continuation leads and
high-scoring shared-domain siblings; independent blinded rating is still required before making a
precision claim.

The first maintainer review rated 17 of 20 semantic candidates as at least contextually useful and 8
as concrete coordination leads. None of 27 explicit-only code-surface leads was a likely edit
collision: the disposable database was not attached to a Ruff source checkout, and generic
reproduction paths dominated. The resulting context and repository-grounding changes are documented
in the [public review](research/ruff-scale-surrogate-01.md).
