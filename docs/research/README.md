# Research and evaluation ledger

This directory records the evidence behind emBEADings policy decisions. Reports deliberately retain
negative results and release blockers. “Useful” means at least contextually worth investigating under
the report's rating rubric; it does not mean a confirmed collision or universal precision.

## Current evidence

| Report | Corpus or question | Status |
| --- | --- | --- |
| [v0.4.0 concurrent-worktree gate](code-surface-v040-release-gate.md) | Four genuine active worktrees in this repository | Current release gate; passed with explicit limits |
| [Ruff scale surrogate](ruff-scale-surrogate-01.md) | 8,143 converted public GitHub issues | Current scale/packet evidence; not native Beads validation |
| [Ruff review depth](ruff-review-depth-02.md) | Fixed-pool rating, recency scopes, and scale probe | Current precision-depth and performance evidence |
| [Native Beads public diagnostic](beads-native-public-diagnostic-01.md) | Public Dolt-backed Beads tracker | Current structural diagnostic; not customer evidence |
| [Objective-default decision](objective-default-public-decision-01.md) | Three public evaluator corpora | Current default-policy decision |
| [Retrieve–verify synthesis](retrieve-verify-context-2026.md) | Retrieval and model-context research | Current architectural rationale |

## Pilot history

| Report | What it established | Status |
| --- | --- | --- |
| [Private pilot 01](private-pilot-01.md) | Initial semantic relevance, determinism, and batching weaknesses | Historical v0.1 baseline |
| [Public code-surface pilot 01](code-surface-public-eval-01.md) | Pointer coverage and hub fan-out failure patterns | Historical; policy changed afterward |
| [Private code-surface pilot 02](code-surface-private-pilot-02.md) | Provenance and explicit-module blockers, then a partial rerun | Superseded by the v0.4.0 worktree gate |
| [Private Linear pilot 01](linear-private-pilot-01.md) | Adapter funnel, evidence quality, and source boundaries | Current single-team pilot evidence |
| [Retrieve–verify public regression 01](retrieve-verify-public-regression-01.md) | Candidate-generation comparison | Historical checkpoint |
| [Retrieve–verify private regression 02](retrieve-verify-private-regression-02.md) | Objective and backfill behavior | Historical checkpoint |
| [Retrieve–verify private regression 03](retrieve-verify-private-regression-03.md) | Remaining audit-receipt gap | Historical; corrected before v0.4.0 |

## Reading results responsibly

- A converted GitHub corpus can test scale and review packaging, not native tracker structure.
- A single repository's known-collision recovery is not a recall estimate across repositories.
- Determinism and non-mutation are product properties, not evidence that semantic judgment is correct.
- Private findings are published only as approved aggregate counts and redacted failure patterns.
- The primary ICP remains a consenting team with 2,000–10,000 native Beads records and genuine
  concurrent implementation work.

For reproducible procedures, use the [evaluation guides](../README.md#evaluate-a-repository) rather
than copying commands from a historical report.
