---
name: evaluate
description: Evaluate whether emBEADings adds value beyond an agent's direct tracker review using a blind baseline and lane-separated ratings. Use for private pilots, regression tests, release gates, or comparing deterministic triage with agent judgment.
---

# Evaluate the prefilter, not just its output

Keep the repository and tracker unchanged. Use only anonymized findings and aggregate metrics in the
evaluation report.

## Blind comparison

1. Run `python <plugin-root>/scripts/run_embeadings.py check` from the plugin root in this skill's installed
   path and record the CLI version.
2. Before executing a report, independently identify likely duplicate work, missing sequencing, and
   code-edit conflicts from the context available to you. Record that baseline privately.
3. From the implementation repository, run the triage and collision reports described by the other
   plugin skills. Default the semantic queue to twenty candidates unless the evaluation protocol
   specifies another budget.
4. Verify non-mutation with tracker and Git fingerprints when a formal safety gate is requested.

## Score distinct lanes

Never combine these into one precision number without also reporting them separately:

1. Existing typed dependency or structural relationships.
2. Completed-work echoes.
3. Semantic overlap.
4. Explicit code-surface leads.
5. Observed worktree evidence, when genuine active worktrees exist.

Rate every reviewed item `2` for actionable coordination, `1` for useful context, or `0` for
misleading or irrelevant output. Calculate precision at `>=1` and at `2` for each lane. Identify
vocabulary-only matches, inspection-vs-edit path noise, hub effects, cap omissions, and whether the
explanation names a concrete fact or contract to verify.

Compare emBEADings-only findings with baseline-only findings. The final recommendation must answer:

- Did the bounded deterministic queue reduce review work or merely create another queue?
- Did code and worktree evidence add information absent from the tracker?
- Are the results reproducible and safe within the test's measured scope?
- Is the right decision ship, revise, or abandon for this repository?

State corpus and worktree limitations explicitly. Do not claim scale, precision, or observed-edit
coverage that the evaluation did not measure.
