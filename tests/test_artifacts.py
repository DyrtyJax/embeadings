import os
import stat
from pathlib import Path

import pytest

from embead.artifacts import atomic_text, private_directory


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_private_artifacts_round_trip_cross_platform(tmp_path: Path) -> None:
    directory = tmp_path / "state" / "run"
    private_directory(directory)
    report = directory / "report.json"

    atomic_text(report, "first")
    atomic_text(report, "second")

    assert report.read_text(encoding="utf-8") == "second"
    assert not list(directory.glob("*.tmp"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits are not portable")
def test_private_artifacts_restrict_existing_paths_on_posix(tmp_path: Path) -> None:
    directory = tmp_path / "run"
    directory.mkdir(mode=0o755)
    report = directory / "report.json"
    report.write_text("old", encoding="utf-8")
    report.chmod(0o644)

    private_directory(directory)
    atomic_text(report, "new")

    assert _mode(directory) == 0o700
    assert _mode(report) == 0o600
