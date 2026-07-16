"""Create and validate a checkout-local development environment."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import venv
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def venv_python(environment: Path) -> Path:
    """Return the interpreter path for a virtual environment on this platform."""
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def ensure_active_environment(root: Path, environment: Mapping[str, str]) -> None:
    """Reject bootstrapping through a virtualenv owned by another checkout."""
    active = environment.get("VIRTUAL_ENV")
    if active is None:
        return
    expected = (root / ".venv").resolve()
    actual = Path(active).expanduser().resolve()
    if actual != expected:
        raise RuntimeError(
            "active virtual environment belongs to another checkout: "
            f"{actual}; deactivate it before bootstrapping {expected}"
        )


def ensure_import_origin(root: Path, origin: Path | None) -> None:
    """Require the installed embead package to resolve inside ``root``."""
    if origin is None:
        raise RuntimeError("embead is not installed in this environment")
    expected = (root / "src" / "embead").resolve()
    actual = origin.expanduser().resolve()
    if actual != expected and expected not in actual.parents:
        raise RuntimeError(
            "editable embead install targets another checkout: "
            f"{actual}; expected a module under {expected}"
        )


def import_origin(python: Path) -> Path | None:
    """Inspect where an interpreter resolves the embead package."""
    program = (
        "import importlib.util, json; "
        "spec = importlib.util.find_spec('embead'); "
        "print(json.dumps(None if spec is None else spec.submodule_search_locations[0]))"
    )
    completed = subprocess.run(
        [str(python), "-c", program],
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(completed.stdout)
    return None if value is None else Path(value)


def validate_checkout(root: Path, python: Path) -> None:
    """Fail when ``python`` imports embead from a different checkout."""
    ensure_import_origin(root, import_origin(python))


def bootstrap(root: Path) -> Path:
    """Create ``root/.venv``, install development dependencies, and validate it."""
    ensure_active_environment(root, os.environ)
    environment = root / ".venv"
    python = venv_python(environment)
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    else:
        installed_origin = import_origin(python)
        if installed_origin is not None:
            ensure_import_origin(root, installed_origin)
    subprocess.run(
        [str(python), "-m", "pip", "install", "-e", f"{root}[dev]"],
        cwd=root,
        check=True,
    )
    validate_checkout(root, python)
    return python


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create or verify this checkout's isolated development environment."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the current interpreter instead of creating .venv",
    )
    args = parser.parse_args(arguments)
    if args.check:
        validate_checkout(ROOT, Path(sys.executable))
        print(f"environment targets {ROOT}")
        return 0
    python = bootstrap(ROOT)
    print(f"ready: {python}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"worktree environment error: {error}", file=sys.stderr)
        raise SystemExit(2) from None
