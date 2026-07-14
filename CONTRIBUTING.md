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

Create a virtual environment, install the development extras, and run the same checks as CI:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/pytest
```

Integration examples and fixtures must use synthetic Beads workspaces. Keep model artifacts,
vectors, and generated reports out of the repository.
