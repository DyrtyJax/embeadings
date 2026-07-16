# Safe offline evaluation

Start with the corpus-free environment diagnostic:

```console
embead doctor --json
embead doctor --offline --json
```

`doctor` checks tracker configuration, invocation-worktree Git metadata, pinned model artifacts,
and external vector-cache presence without loading issue records or contacting Linear. It exits `0`
when the environment is ready or needs only non-blocking attention, and `2` when a required source,
credential, team, or offline model artifact is missing. Failed checks still emit a complete JSON
diagnostic. Credential values and the selected Linear team are never included in that output.

Use the readiness command when the evaluation needs to fetch or load the pinned embedding model:

```console
HF_HOME=/external/model-cache embead readiness --json
HF_HOME=/external/model-cache embead readiness --offline --json
```

The first form may fetch the pinned model. The offline form requires the artifacts to be present.
Both use the corpus-free string `model readiness probe`, do not invoke `bd`, and report the exact
model ID, revision, and vector dimension. The same contract is available as
`embead.provider_readiness()`.

## Retrieve–verify regression checkpoint

Run the committed public fixture before private or public corpus evaluation:

```console
python scripts/evaluate_semantic_fixture.py
python scripts/evaluate_semantic_fixture.py --provider model2vec
```

The output is deterministic for a fixed provider and contains no repository or tracker data. Record
its fingerprint, per-rating mean field score, and pair-level selected channel. A model upgrade does
not pass merely because its average similarity rises: rating-2 candidate recall must improve without
raising vocabulary-only and shared-subsystem hard negatives into the review budget.

For each existing evaluator corpus, compare the unchanged baseline with the experimental path:

```console
embead sweep --weekly-review-budget 20 --json
embead sweep --objective overlap --objective echo --semantic-view fields \
  --weekly-review-budget 20 --json
embead sweep --objective structure --weekly-review-budget 20 --json
```

Keep all output and platform cache/state directories outside the evaluated repository. Compare:

- recall of previously rated-2 pairs in the pre-cap candidate pool;
- actionable precision at a fixed review budget;
- same-token/different-intent and broad-hub rejection;
- direct parent/child exclusion from explicit overlap discovery;
- repeated completed-target omissions and deterministic replacement membership;
- abstention/no-signal quality;
- per-objective and per-channel candidate counts;
- candidate-set churn and deterministic ordering;
- cold/warm runtime, cache accounting, and peak memory;
- tracker, Git-visible, and physical-storage non-mutation evidence.

Do not enable a pairwise reranker in this checkpoint. The first gate isolates whether objective
separation and field-local candidate generation improve recall and review packaging. A later verifier
must be evaluated symmetrically in both issue orders and against permutation stability.

Resolve the tracker executable rather than trusting shell ordering:

```console
command -v -a bd
command -v bd
bd version
```

Record the resolved path and version in the evaluation report. After model preparation, deny network
access at the operating-system level for every command that can load issue text. Keep `HF_HOME`,
`XDG_CACHE_HOME`, `XDG_STATE_HOME`, outputs, and checkpoints outside the analyzed repository.

## Non-mutation evidence

Capture the repository commit, full Git status including untracked files, export hash, and a
read-only canonical tracker snapshot before and after. Audit ignored files by relative path, size,
content hash, birth time, and modification time. Beads 1.0.5 embedded Dolt reads can update or replace
ignored manifest, journal-index, or volume-file metadata without changing their bytes or logical
tracker state. Report this separately:

- **Logical tracker non-mutation:** issue/dependency snapshot and export content are unchanged.
- **Git-visible non-mutation:** tracked and untracked repository state is unchanged.
- **Strict physical immutability:** no file content or metadata changed, including ignored storage.

Do not attribute ignored Dolt metadata churn to emBEADings unless an isolated reproduction excludes
direct `bd --readonly` access and host-application activity. For strict physical evaluation, use a
precreated disposable tracker snapshot or an OS sandbox that denies writes to the corpus while
allowing external cache and artifact paths.
