# emBEADings agent plugin

This directory is a minimal dual-host plugin around the independently installable `embead` CLI. It
adds the same three read-only skills to Codex and Claude Code:

- `triage`: produce and judge a bounded tracker coordination queue;
- `collisions`: inspect explicit code pointers and genuine active-worktree evidence;
- `evaluate`: compare deterministic output with an agent's blind baseline.

The plugin does not contain a second analysis engine and does not mutate Beads, Linear, Git, or
source files. `python scripts/run_embeadings.py` discovers `embead` on `PATH`, requires emBEADings 0.3.0 or
newer, forces JSON output, rejects report/checkpoint file writes, and verifies the schema-v1
read-only contract before returning a report to the agent. It is the canonical launcher on Windows,
macOS, and Linux. `scripts/run-embeadings` is only a POSIX convenience shim.

## Prerequisites

- Python 3.11 or later;
- `embeadings>=0.3.0` installed so `embead` is on `PATH`;
- `bd` for Beads, or `LINEAR_API_KEY`/`LINEAR_ACCESS_TOKEN` plus a selected Linear team.

For local development from the repository:

```sh
python -m pip install -e .
python plugins/embeadings/scripts/run_embeadings.py check
```

Keep API credentials in the environment. The standalone CLI cannot reuse OAuth credentials stored
inside an agent host, and the plugin never asks an agent to display a key.

## Load in Claude Code

Claude Code supports direct local development loading:

```sh
claude --plugin-dir ./plugins/embeadings
```

The skills appear under the `embeadings` namespace, such as `/embeadings:triage` and
`/embeadings:collisions`. Use `claude plugin validate ./plugins/embeadings` when the installed Claude
Code version exposes plugin validation.

## Load in Codex

The Codex manifest is at `.codex-plugin/plugin.json` and shares the root `skills/` directory. Add the
plugin directory through the local plugin-development or marketplace workflow supported by the
installed Codex version, then start a fresh task so the skill catalog is reloaded.

Repository marketplace metadata is intentionally not included in this foundation. It can be added
when installation policy, authentication timing, version release, and marketplace ownership are
decided; local loading is sufficient to validate the host-neutral skill workflow first.

## Privacy boundary

Semantic issue text is embedded locally by the default engine. A first semantic run may download the
pinned model before issue loading. Linear GraphQL queries send issue data only between the CLI and
Linear itself. The plugin wrapper does not send reports to another service, but the agent host may
receive the bounded JSON it is asked to interpret; follow the host and repository's data policy.

Collision reports contain code pointers, not source snippets. Run them from the implementation
repository whose Git worktrees should be observed, and never fabricate worktree mappings for an
evaluation.
