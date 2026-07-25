# Beads compatibility contract

emBEADings v0.4.2 supports Beads **1.0.5 and newer** through a narrow, read-only CLI
contract. Version 1.0.5 is the oldest release exercised by the committed relationship fixture and by
the native-Beads evaluations; older releases are not claimed compatible.

The adapter executes exactly these command shapes:

```text
bd --readonly version --json
bd --readonly context --json
bd --readonly list --all --limit 0 --json
```

The installed `bd` must:

- report a semantic version at least `1.0.5`;
- return a context object containing a project/workspace identity or workspace path;
- return either an issue array or one recognized issue envelope;
- provide non-empty issue IDs, titles, and statuses;
- represent labels, parentage, and typed dependencies using one of the validated aliases; and
- preserve dependency direction by identifying the target separately from the source.

The minimum version is an admission check, not a promise that every future Beads payload is
compatible. emBEADings continues to validate every response and fails closed on unknown or malformed
shapes. Run `embead doctor --json` to see the configured and resolved `bd` executable, detected
version, and an actionable failure before loading issue content.

## Bootstrap and partial snapshots

A child can legitimately reference a parent that is absent from the returned issue population
during bootstrap, filtering, or partial synchronization. emBEADings preserves that parent ID and
typed edge as external structural evidence; it does not fabricate a parent record or discard the
relationship. Self-dependencies and malformed targets still fail closed.

## What read-only means

emBEADings never asks Beads to create, update, synchronize, import, export, or otherwise mutate
tracker records. Logical source comparisons use canonical content digests rather than file
modification times.

This does **not** promise byte-for-byte or mtime stability for every file in Beads storage. The
embedded database may update physical metadata while servicing a read-only command. Evaluations
should therefore compare logical tracker exports/content hashes and Git-visible repository state,
and report physical mtime-only changes separately rather than treating them as tracker mutation.
