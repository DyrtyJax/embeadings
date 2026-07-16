from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "worktree_env.py"
SPEC = importlib.util.spec_from_file_location("worktree_env", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
worktree_env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worktree_env)


def test_import_origin_accepts_current_checkout(tmp_path: Path) -> None:
    origin = tmp_path / "src" / "embead" / "__init__.py"
    origin.parent.mkdir(parents=True)
    origin.touch()

    worktree_env.ensure_import_origin(tmp_path, origin)


def test_import_origin_rejects_another_checkout(tmp_path: Path) -> None:
    other = tmp_path.parent / "another-checkout" / "src" / "embead" / "__init__.py"

    with pytest.raises(RuntimeError, match="another checkout"):
        worktree_env.ensure_import_origin(tmp_path, other)


def test_active_environment_rejects_another_worktree(tmp_path: Path) -> None:
    foreign = tmp_path.parent / "other" / ".venv"

    with pytest.raises(RuntimeError, match="deactivate"):
        worktree_env.ensure_active_environment(tmp_path, {"VIRTUAL_ENV": str(foreign)})


def test_active_environment_accepts_checkout_local_venv(tmp_path: Path) -> None:
    local = tmp_path / ".venv"

    worktree_env.ensure_active_environment(tmp_path, {"VIRTUAL_ENV": str(local)})
