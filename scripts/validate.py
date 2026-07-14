"""Run the complete local validation contract in CI order."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = (
    (sys.executable, "-m", "ruff", "format", "--check", "src", "tests"),
    (sys.executable, "-m", "ruff", "check", "."),
    (sys.executable, "-m", "pytest"),
)


def main() -> None:
    """Run every check, stopping at the first failure."""
    for command in COMMANDS:
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
