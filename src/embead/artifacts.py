"""Private-by-default filesystem helpers for local derived artifacts."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def private_directory(path: Path) -> None:
    """Create an artifact directory and restrict it to its owner on POSIX."""

    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        path.chmod(PRIVATE_DIRECTORY_MODE)


def atomic_text(path: Path, text: str) -> None:
    """Atomically replace a UTF-8 text artifact with owner-only POSIX access."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        if os.name == "posix":
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            path.chmod(PRIVATE_FILE_MODE)
    finally:
        temporary.unlink(missing_ok=True)
