# Decision: keep PyPI canonical and use uvx before adding npm

Status: **accepted for the next distribution wave on 2026-07-25.**

## Decision

Keep PyPI as the canonical package registry and the `embead` Python console script as the canonical
CLI. Support two installation modes from that one artifact:

- persistent: `uv tool install embeadings` or `pipx install embeadings`;
- one-shot: `uvx --from 'embeadings==VERSION' embead ...`.

For an interactive trial, an unpinned resolution is acceptable:

```bash
uvx --from embeadings embead doctor
```

For an evaluation, automation, or agent plugin, pin the package version and record the version emitted
by the CLI:

```bash
uvx --from 'embeadings==0.4.2' embead doctor
```

Do **not** publish an npm package that shells out to Python, pipx, or uv, and do not use an npm
`postinstall` script to download another executable. That design would make `npx` look self-contained
while retaining an undeclared runtime prerequisite and adding a second network and supply-chain
boundary.

An npm launcher is conditionally approved only after emBEADings has verified standalone executables.
If that gate is reached, npm should contain a small JavaScript dispatcher plus platform-specific npm
packages containing the executables. Publication must come from the same source tag and workflow as
PyPI and GitHub Releases. Homebrew should consume the same standalone artifacts later; it should not
be a separate Python packaging implementation.

This is a **go** for the existing PyPI, uv tool, pipx, and uvx paths; a **no-go for npm, standalone
executables, and Homebrew in the current release**.

## Why this is the natural boundary

emBEADings is implemented and versioned as a Python application. Its `pyproject.toml` already produces
one `py3-none-any` wheel, one source distribution, and one `embead` entry point. The release workflow
builds that bundle once, verifies both installation forms in disposable environments, publishes the
same files to GitHub Releases and PyPI, and uses:

- SHA-256 checksums;
- GitHub artifact attestations for the release files; and
- PyPI Trusted Publishing with OIDC.

The published [0.4.2 PyPI files](https://pypi.org/project/embeadings/0.4.2/#files) confirm Trusted
Publishing and provenance back to the tagged repository workflow. This is already the shortest
artifact path and the lowest-maintenance source of truth. The Python Packaging User Guide recommends
isolated application installation with
[pipx](https://packaging.python.org/en/latest/guides/installing-stand-alone-command-line-tools/);
uv provides the equivalent persistent and ephemeral
[tool environments](https://docs.astral.sh/uv/guides/tools/).

npm is a natural discovery and invocation surface for Node-oriented agent users, but it is not the
natural implementation registry for this codebase. `npx` becomes a meaningful improvement only when
it removes the Python/uv prerequisite. That requires standalone artifacts, not a wrapper around the
existing installer.

## Evidence from the current repository

The following checks were made from a clean checkout at `0cc98e7`:

- `src/embead/_version.py`, the latest Git tag, and PyPI all report `0.4.2`.
- PyPI publishes a 99.2 kB universal wheel and an 84.7 kB source distribution with attestations.
- CI tests Linux, macOS, and Windows on Python 3.11, plus Linux on Python 3.14.
- The release workflow passes one checksum-bound bundle to both GitHub and PyPI publication jobs.
- Node, npm, npx, Python 3.14, and Homebrew were available in the invoking shell, but `embead`, pipx,
  uv, and uvx were not on `PATH`.
- The repository virtual environment could run `.venv/bin/embead --version`, but its editable
  distribution metadata was stale (`0.2.0`) while the source-backed CLI reported `0.4.2`. This is a
  development-environment artifact, not a defect in the published wheel, but it reinforces that a
  clean registry install is a better evaluator path than an old editable checkout.
- `npm view embeadings` returned `E404` on 2026-07-25. The unscoped name was unoccupied at that moment;
  availability can change and is not a reason to ship a placeholder or incomplete package.

The missing command reproduces the reported installation/PATH friction on one workstation. The same
shell already had Node and npm, so npm would have reduced prerequisite setup for this user **if** it
contained a standalone executable. It does not establish population-level demand for npm. Both
supported persistent Python installers provide explicit PATH repair: `uv tool update-shell` and
`pipx ensurepath`. `uvx` avoids the `embead` PATH requirement once uv itself is installed.

## Channel comparison

| Channel | macOS / Linux / Windows prerequisite | One-shot and PATH | Version, update, uninstall | Security and provenance | Maintainer burden |
| --- | --- | --- | --- | --- | --- |
| PyPI via uv | Install `uv`; uv can provision a compatible Python; `bd` remains external for Beads mode | `uvx --from 'embeadings==VERSION' embead ...` needs no persistent `embead` PATH; `uv tool update-shell` repairs persistent installs | Pin in the `--from` requirement; `uv tool upgrade embeadings`; `uv tool uninstall embeadings` | Existing Trusted Publishing and index-hosted provenance; isolated environment; same verified wheel as GitHub | Low; already built, tested, and released |
| PyPI via pipx | Python 3.11+, pipx, and `bd` for Beads mode on all three operating systems | `pipx run --spec embeadings embead ...` is possible; persistent installs may need `pipx ensurepath` and a shell restart | `pipx upgrade embeadings`; `pipx uninstall embeadings` | Same PyPI artifact and provenance; per-tool environment; no global dependency collision | Low; already supported, but bootstrapping Python and pipx is more work |
| npm/npx wrapper around Python | Node/npm **plus** Python, pipx, or uv; `bd` still external | Convenient spelling, but only after hidden prerequisite discovery; nested installers create confusing errors | npm manages only the wrapper, not necessarily its Python environment or cache | npm supports OIDC and automatic provenance, but that would attest the wrapper rather than remove trust in the delegated installer | Medium and misleading; two manifests, two release surfaces, no prerequisite reduction |
| npm/npx with standalone executables | Node/npm and `bd`; no Python if executable packaging succeeds | Natural `npx embeadings@VERSION ...`; local dispatcher selects a bundled platform package | npm version must equal binary version; `npm update`/`uninstall`; npx cache remains disposable | Viable with npm Trusted Publishing, provenance, no lifecycle download, and platform packages built from the same tag | High; JS dispatcher, platform packages, native build/test matrix, signing, and synchronized releases |
| GitHub standalone executables | Only the matching executable and `bd`; no Python/Node | Manual download unless another manager wraps it; user must place it on PATH | Manual replacement/removal unless a manager owns it | Checksums and GitHub attestations already have a pattern, but binaries need per-platform builds and ideally macOS/Windows signing | High; packaging dynamic Python/model dependencies, six common OS/architecture targets, smoke tests, signing |
| Homebrew | Homebrew on macOS or Linux; no Windows; `bd` remains external | Excellent persistent PATH behavior; no one-shot equivalent | `brew upgrade embeadings`; `brew uninstall embeadings` | Formula/cask pins an immutable URL and SHA-256; a cask can consume signed upstream executables | Medium after standalone exists; otherwise Python resources duplicate PyPI dependency maintenance |

`bd` is deliberately outside every emBEADings package. None of these channels should silently install
or select a tracker implementation on the user's behalf.

## Security requirements

Any future secondary registry must preserve or improve the current boundary:

1. One release tag is the authority for the Python package, standalone artifacts, and launcher.
2. The release pipeline derives every version from `src/embead/_version.py` and rejects a tag,
   artifact, package manifest, embedded executable, or `--version` mismatch.
3. Artifacts are built on GitHub-hosted runners, checksummed, and attested. GitHub documents
   [artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
   as build-provenance records.
4. npm publication, if introduced, uses
   [Trusted Publishing](https://docs.npmjs.com/trusted-publishers/) with OIDC and automatic
   provenance—never a long-lived automation token.
5. npm packages contain the executable they run. They do not download or execute remote content from
   `postinstall`, and the JavaScript dispatcher never falls back to an unpinned package manager.
6. A launcher's version and selected executable version must match before issue text is loaded.
7. `doctor` remains safe to run without loading tracker text and reports the CLI version, source mode,
   external `bd` availability, and any PATH repair command.

Trusted publishing proves origin, not correctness. The existing install smoke tests, privacy checks,
and cross-platform CLI tests remain required.

## Staged implementation

### Stage 0 — use the artifact already shipped

- Add the pinned `uvx --from 'embeadings==VERSION' embead ...` form to direct CLI evaluation
  instructions. Agent-plugin evaluations must use a pinned persistent `uv tool` or pipx install
  because the current wrapper intentionally discovers `embead` on `PATH`.
- Use the unpinned form only for an interactive preview; uv may reuse a cached environment.
- Preserve pipx and `uv tool install` as supported persistent installs.
- Make PATH repair explicit in installation troubleshooting.
- Do not add a second console-script alias merely to shorten `uvx`; first measure whether the
  `--from` spelling causes evaluator failure.

This stage changes documentation and evaluation instructions only. It does not require a new
distribution.

### Stage 1 — verify fresh-session installation

On clean macOS, Linux, and Windows environments, test:

1. pinned uvx invocation;
2. `uv tool install`, command discovery, upgrade, and uninstall;
3. pipx install, command discovery, upgrade, and uninstall;
4. `doctor` before model download;
5. one offline semantic rerun after model prefetch; and
6. the expected failure when `bd` is absent.

Record time to first `doctor`, time to first triage, bytes downloaded, PATH intervention, error
clarity, resolved package/CLI versions, and repository mutation. A successful command alone is not
enough.

### Stage 2 — test standalone feasibility only when it buys reach

Start this spike only if fresh evaluators or install telemetry show that the Python/uv prerequisite is
a material adoption blocker. Build disposable, unpublished artifacts for at least:

- macOS arm64 and x86_64;
- Linux x86_64 and arm64; and
- Windows x86_64.

Gate on cold/warm `doctor`, `collisions`, and semantic triage; model download and cache placement;
offline repeat; executable size; startup time; antivirus/notarization behavior; architecture
selection; and byte-stable JSON output versus the wheel. Do not weaken the local-only issue-text
boundary to make bundling easier.

### Stage 3 — npm preview, only after Stage 2 passes

Publish a prerelease such as `embeadings@X.Y.Z-next.0`:

- one unscoped dispatcher package named `embeadings`;
- one platform package per supported OS/architecture selected through npm package metadata and
  optional dependencies;
- no install lifecycle scripts and no runtime download;
- npm Trusted Publishing from the existing release workflow;
- exact version parity with the Git tag, PyPI package, and embedded executable; and
- cross-platform tests for `npx embeadings@X.Y.Z-next.0 doctor`, error handling, cache behavior, and
  uninstall.

Promote to npm's `latest` only after two fresh Node-oriented evaluators complete the workflow without
Python or PATH assistance. Do not publish a placeholder merely to reserve the unscoped name. If the
name is unavailable later, use a clearly owned scope rather than compromising the design.

### Stage 4 — Homebrew after standalone demand

Use an upstream-built, signed standalone artifact in a tap or cask. Homebrew distinguishes a formula
that builds source from a cask that installs
[precompiled upstream binaries](https://docs.brew.sh/Formula-Cookbook#homebrew-terminology); the latter
avoids reproducing the Python dependency graph. Add Homebrew only after repeated macOS demand, and do
not count it as Windows coverage.

## Promotion and stop gates

Proceed from uvx to standalone/npm only if at least one of these is measured:

- two or more otherwise-qualified evaluators fail or abandon setup because Python/uv is unavailable;
- Node-oriented plugin users materially prefer npx and a standalone preview reduces assisted setup;
- a non-Python environment becomes an explicit ICP requirement; or
- executable bundling materially improves reproducible offline deployment.

Stop the npm path if the standalone artifact:

- cannot preserve local model/cache behavior;
- exceeds an agreed size or startup budget without measured adoption benefit;
- requires unsigned executables that trigger common platform security failures;
- changes report bytes or ranking relative to the same-version wheel; or
- creates an independent release/version cadence.

The next product evidence should come from the fresh-session plugin evaluation and native Beads ICP,
not from registry count. Distribution should reduce a measured adoption barrier rather than become a
parallel product.
