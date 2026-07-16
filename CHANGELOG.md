# Changelog

## 0.4.2 — 2026-07-16

Standard distribution and public proof.

- Publish verified wheel and source distributions through PyPI Trusted Publishing with short-lived
  GitHub OIDC credentials and a protected `pypi` environment.
- Build release artifacts once, preserve checksums, and pass the exact verified distributions to
  both the GitHub release and PyPI publishing jobs.
- Add `pipx` and `uv tool` installation paths while retaining the immutable GitHub-wheel fallback.
- Add a compact visual system and a bounded four-worktree dogfood story with explicit limitations.
- Document deferred-work inclusion and retain the 20-candidate triage default while a bounded
  corpus-aware budget remains an evaluation decision.

## 0.4.1 — 2026-07-16

Privacy, packaging, and public-repository hardening.

- Restrict POSIX cache/state roots and run directories to `0700`, and sensitive derived files to
  `0600`, including atomic replacements.
- Narrow source distributions to runtime source, schemas, and required package metadata; verify fresh
  installs from both wheel and source archive.
- Pin release workflow actions and build tooling, validate tagged source, and attest future release
  artifacts with GitHub build provenance.
- Replace the internal-reference README with an outcome-led quick start, representative output,
  evidence boundaries, and task-oriented documentation indexes.
- Add privacy-aware issue forms, a pull-request checklist, current security guidance, and accurate
  Linear client version metadata.

## 0.4.0 — 2026-07-16

First public technical preview.

- Read-only Beads and Linear adapters with deterministic structural and semantic review queues.
- Local code-surface collision evidence from explicit task pointers and genuine Git worktrees.
- Bounded triage packets, objective-specific experimental retrieval, checkpoints, and audit receipts.
- Dual Codex and Claude Code plugin foundation around the same guarded CLI contract.
- Public scale diagnostics and privacy-preserving evaluation protocols.

The release gate used four genuine active worktrees and retained all three known exact-file
collisions. That one-repository result does not establish precision or recall across other repository
layouts; broader ICP evaluation remains ongoing.
