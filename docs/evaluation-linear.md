# Private Linear regression evaluation

Use this protocol to compare the corrected weekly queue, team selection, relation-boundary
diagnostics, and code-surface safeguards against a previous private Linear evaluation. Keep API keys,
raw reports, issue data, repository paths, and worktree mappings outside emBEADings and the evaluated
repository. Return only aggregate counts and bounded human ratings.

## Prepare

1. Record the exact emBEADings version and commit, selected Linear team key, active issue count, local
   repository commit, and number of registered worktrees. Do not include the team UUID in the report.
2. Put `HF_HOME`, `XDG_CACHE_HOME`, `XDG_STATE_HOME`, and report output under a private temporary
   directory outside both repositories. Enter the Linear credential through the environment, never a
   command argument or committed file.
3. Fingerprint Git status and repository contents before the run. If another tracker store is present,
   isolate it outside the clone as in the first evaluation.
4. Identify the canonical UUID for the same team privately. The first acquisition run below is the
   regression test for direct UUID selection.

## Run

Use the same model revision and thresholds as the previous evaluation. Substitute private values and
repeat any `--worktree-map` only for a genuinely active, included issue:

```console
RUN_DIR=/private/tmp/embead-linear-rerun
mkdir -p "$RUN_DIR/cache" "$RUN_DIR/state" "$RUN_DIR/model"
export XDG_CACHE_HOME="$RUN_DIR/cache"
export XDG_STATE_HOME="$RUN_DIR/state"
export HF_HOME="$RUN_DIR/model"
read -rs "LINEAR_API_KEY?Linear API key: " && export LINEAR_API_KEY && printf '\n'

embead --source linear --linear-team "$LINEAR_TEAM_UUID" \
  sweep --weekly-review-budget 20 --code-surfaces --json \
  --output "$RUN_DIR/uuid-default"

embead --source linear --linear-team "$LINEAR_TEAM_KEY" \
  sweep --weekly-review-budget 20 --code-surfaces --json \
  --output "$RUN_DIR/key-repeat"
```

Each sweep output is a directory; compare its `report.json` and batch artifacts. The UUID and key
reports should agree on source counts, relation diagnostics, candidates, batches, and collision
analysis. Cache/performance metadata may differ. Repeat the key run once more with the same
environment to confirm deterministic semantic membership, ordering, scores, explanations, and lane
accounting.

Inspect these specific regressions:

- `snapshot.relation_diagnostics` conserves raw relations as retained + collapsed + omitted and
  matches the human-readable source warning. Report boundary counts by direction and type, but no
  external identifiers.
- With a budget of 20 and sufficient qualified candidates, the report reserves 12 dependency, 4
  echo, and 4 overlap slots. Record reserved, `admitted_to_reservation`, unused, qualified, total
  admitted, and omitted counts for all three lanes. Code-surface leads remain separate from these 20
  candidates.
- Rate every retained no-edge semantic pair, or a deterministic sample of 20 if the queue is larger,
  as 2 (actionable coordination), 1 (contextually useful), or 0 (vocabulary-only/misleading).
- Rate code-surface leads separately with the same scale. Stratify exact-file leads by explicit-only,
  observed-only, and corroborated evidence; do not merge them into semantic precision.
- Confirm generic semantic explanations abstain when no pair-corroborated contract category can be
  extracted. Existing typed relations must be described as tracker context, not novel evidence.

## Worktree diagnostic

Use a current integration base and map only genuine active implementation worktrees:

```console
embead --source linear --linear-team "$LINEAR_TEAM_KEY" \
  collisions --base-ref origin/main --json \
  --output "$RUN_DIR/collisions.json"
```

Add repeatable `--worktree-map ACTIVE_ISSUE=/private/worktree` flags only when automatic association is
not possible. If fewer than two active implementation worktrees exist, label this a partial diagnostic
rather than a release gate. Do not map closed or administrative work to manufacture coverage.

If a deliberately old base is available, run one negative-control collision command privately. A
range above 250 eligible code paths should trigger the volume circuit breaker and be excluded while
current tracked and untracked paths remain. This does not prove that smaller ranges use a correct
base; verify the intended integration point independently. Delete that artifact after recording only
aggregate counts; it is a guard test, not a useful collision report.

## Return

Return one aggregate report containing:

- environment, source, issue, relationship, and non-mutation counts;
- UUID-versus-key acquisition equivalence;
- retained, collapsed, omitted, inbound-boundary, outbound-boundary, and unrelated-external relation
  counts, stratified by relation type;
- weekly reservations, admissions, unused capacity, and omissions by candidate lane;
- semantic and code-surface ratings reported separately;
- worktree association coverage, base-guard behavior, deterministic-output result, and runtime; and
- remaining false-positive patterns plus a go/revise/no-go recommendation.

Do not return issue IDs, text, labels, team or workspace IDs, file paths, symbols, snippets, branch
names, worktree locations, API responses, raw reports, credentials, or repository fingerprints.
Unset `LINEAR_API_KEY` and delete the private run directory after producing the aggregate report.
