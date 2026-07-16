from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "verify_release.py"
SPEC = importlib.util.spec_from_file_location("verify_release", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
verify_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_release)


def _wheel(path: Path, version: str = "0.4.0") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"embeadings-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: embeadings\nVersion: {version}\n",
        )
    return path


def test_artifact_version_reads_wheel_metadata(tmp_path: Path) -> None:
    assert verify_release.artifact_version(_wheel(tmp_path / "package.whl")) == "0.4.0"


def test_project_version_matches_public_package() -> None:
    assert verify_release.project_version() == "0.4.0"


def test_discover_artifacts_requires_exact_pair(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path / "package.whl")
    source = tmp_path / "package.tar.gz"
    source.touch()

    assert verify_release.discover_artifacts(tmp_path) == (wheel, source)


def test_discover_artifacts_rejects_ambiguous_dist(tmp_path: Path) -> None:
    _wheel(tmp_path / "first.whl")
    _wheel(tmp_path / "second.whl")
    (tmp_path / "package.tar.gz").touch()

    with pytest.raises(RuntimeError, match="exactly one"):
        verify_release.discover_artifacts(tmp_path)


def test_write_checksums_is_stable(tmp_path: Path) -> None:
    wheel = tmp_path / "package.whl"
    source = tmp_path / "package.tar.gz"
    wheel.write_bytes(b"wheel")
    source.write_bytes(b"source")

    first = verify_release.write_checksums(tmp_path, (wheel, source)).read_text()
    second = verify_release.write_checksums(tmp_path, (wheel, source)).read_text()

    assert first == second
    assert "package.whl" in first
    assert "package.tar.gz" in first
