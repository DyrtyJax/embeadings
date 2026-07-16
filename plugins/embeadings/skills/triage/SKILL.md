---
name: triage
description: Run a bounded, deterministic emBEADings review of Beads or Linear work, then judge the structural and semantic signals. Use for tracker triage, weekly coordination review, duplicate-work discovery, or requests to find related active tasks.
---

# Triage work without mutating it

Use emBEADings as a deterministic prefilter, not as the final judge. Do not update the tracker,
source files, dependencies, or issue state while this skill is active.

## Prepare

1. Run `python <plugin-root>/scripts/run_embeadings.py check` from the plugin root shown in this skill's
   installed path. If it fails, report the dependency error exactly and stop.
2. Work from the repository whose Git context should be evaluated.
3. Use Beads by default. Use Linear only when the user selected it or `EMBEAD_SOURCE=linear` is
   already set. Linear also requires `LINEAR_TEAM` or an explicitly supplied team ID, key, or exact
   name. Never print credentials.
4. Before looking at the result, briefly record your own likely coordination risks from the context
   already available. This keeps the algorithm from anchoring your judgment.

## Run

For Beads, run:

```sh
python <plugin-root>/scripts/run_embeadings.py triage
```

For Linear, run:

```sh
python <plugin-root>/scripts/run_embeadings.py --source linear --linear-team TEAM triage
```

Replace `TEAM` with the selected team ID, key, or exact name.

Triage includes code-surface analysis when the current repository is the implementation repository;
unavailable Git evidence fails soft with an explicit warning. Pass only options the user requested or
that are necessary to select the tracker. Do not add `--output` or `--write-checkpoint`; the wrapper
deliberately rejects writes.

## Judge

Keep the three evidence lanes separate:

- Dependency: authoritative tracker structure, useful for sequencing but not novel intelligence.
- Echo: active work resembling a completed outcome; verify that the outcome or invariant is shared.
- Overlap: advisory semantic similarity; reject vocabulary-only matches.

Rate a candidate `2` only when it implies a likely collision or concrete coordination action, `1`
for useful context without immediate action, and `0` for misleading or irrelevant output. Prefer
specific contracts, files, invariants, and ownership boundaries over cosine score. Compare the queue
with your independent baseline and call out important misses.

Return a compact summary: tracker and population, queue size and cap omissions, per-lane ratings,
actionable coordination leads, false-positive patterns, and whether the queue reduced review work.
Do not reproduce private issue bodies or proprietary source snippets.
