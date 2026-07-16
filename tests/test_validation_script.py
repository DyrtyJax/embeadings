from __future__ import annotations

import runpy
from pathlib import Path


def test_validation_contract_starts_with_format_check_and_runs_every_check(monkeypatch) -> None:
    script = Path(__file__).parents[1] / "scripts" / "validate.py"
    namespace = runpy.run_path(script)
    calls: list[tuple[tuple[str, ...], Path, bool]] = []

    def record(command, *, cwd, check):
        calls.append((command, cwd, check))

    monkeypatch.setitem(
        namespace["main"].__globals__, "validate_checkout", lambda *_arguments: None
    )
    monkeypatch.setattr(namespace["subprocess"], "run", record)
    namespace["main"]()

    python = namespace["sys"].executable
    root = Path(__file__).parents[1]
    assert calls == [
        ((python, "-m", "ruff", "format", "--check", "src", "tests"), root, True),
        ((python, "-m", "ruff", "check", "."), root, True),
        ((python, "-m", "pytest"), root, True),
    ]
