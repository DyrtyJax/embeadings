# Contributing

Thanks for helping build emBEADings.

## Project boundaries

- Keep the core read-only. Do not add Beads mutation commands.
- Use supported `bd --json` interfaces rather than reading exported JSONL as tracker truth.
- Keep agent runtimes optional and outside the semantic core.
- Do not add persistent semantic labels, clusters, or lifecycle automation.
- Store caches and generated reports outside analyzed repositories by default.

## Privacy

Issues often contain private product plans, customer context, incidents, and source references.

- Use synthetic fixtures and examples.
- Do not commit real tracker exports, vector caches, reports, prompts, repository paths, or logs.
- Scrub issue IDs, people, organizations, domains, branches, commits, and operational identifiers from
  bug reports and benchmarks unless they already belong to a clearly public test repository.
- Reproduce defects in a synthetic scratch workspace before opening an issue or pull request.

## Development workflow

Each clone or Git worktree must own its virtual environment. Use the repository bootstrap so an
active environment from a sibling checkout cannot silently run the wrong code:

```bash
python3 scripts/worktree_env.py
. .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python scripts/validate.py
```

The validation script is the canonical contributor and agent entry point. It checks formatting,
then lint, then the full test suite, and exits at the first failure. It also verifies that the editable
`embead` import resolves to the current checkout. On Windows, use
`.venv\\Scripts\\python scripts\\validate.py` after running the bootstrap.

Integration examples and fixtures must use synthetic Beads workspaces. Keep model artifacts,
vectors, and generated reports out of the repository.

This public repository intentionally tracks Beads' own aggregate interaction audit file while
dogfooding the tracker. The prohibition on committed logs applies to emBEADings run reports, private
tracker exports, evaluator transcripts, local paths, and other generated operational data. Do not add
raw issue text or private identifiers to the public Beads audit trail.

Before opening a pull request:

- run `python scripts/validate.py` from the checkout-local environment;
- keep behavior changes covered by synthetic tests;
- update schemas and examples together when a public artifact changes; and
- confirm `git status --short` contains no cache, report, model, or private evaluation artifact.
