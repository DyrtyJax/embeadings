# Safe offline evaluation

Use the public readiness command before loading any Beads records:

```console
HF_HOME=/external/model-cache embead readiness --json
HF_HOME=/external/model-cache embead readiness --offline --json
```

The first form may fetch the pinned model. The offline form requires the artifacts to be present.
Both use the corpus-free string `model readiness probe`, do not invoke `bd`, and report the exact
model ID, revision, and vector dimension. The same contract is available as
`embead.provider_readiness()`.

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
