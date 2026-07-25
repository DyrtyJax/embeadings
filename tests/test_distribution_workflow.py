from __future__ import annotations

import runpy
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
verify_distribution_journey = SimpleNamespace(
    **runpy.run_path(ROOT / "scripts" / "verify_distribution_journey.py")
)


def _ci_workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_distribution_gate_runs_fresh_wheel_journeys_on_all_supported_systems() -> None:
    workflow = _ci_workflow()
    distribution = workflow.split("  distribution:\n", maxsplit=1)[1]

    assert "ubuntu-latest" in distribution
    assert "macos-latest" in distribution
    assert "windows-latest" in distribution
    assert '"uv==0.11.29"' in distribution
    assert "python -m build" in distribution
    assert "python scripts/verify_distribution_journey.py" in distribution
    assert "--dist dist" in distribution
    assert "--output distribution-receipt.json" in distribution
    assert "distribution-receipt-${{ matrix.os }}" in distribution


def test_distribution_gate_does_not_introduce_a_secondary_channel() -> None:
    distribution = _ci_workflow().split("  distribution:\n", maxsplit=1)[1]

    assert "npm " not in distribution
    assert "npx " not in distribution
    assert "standalone" not in distribution
    assert "secrets." not in distribution
    assert "id-token: write" not in distribution


def test_wheel_discovery_rejects_an_ambiguous_distribution(tmp_path: Path) -> None:
    (tmp_path / "one.whl").touch()
    (tmp_path / "two.whl").touch()

    with pytest.raises(RuntimeError, match="expected exactly one wheel"):
        verify_distribution_journey.discover_wheel(tmp_path)


def test_wheel_version_comes_from_artifact_metadata(tmp_path: Path) -> None:
    wheel = tmp_path / "embeadings-9.8.7-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "embeadings-9.8.7.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: embeadings\nVersion: 9.8.7\n",
        )

    assert verify_distribution_journey.wheel_version(wheel) == "9.8.7"


def test_corpus_free_receipt_rejects_secret_exposure() -> None:
    payload = {
        "read_only": True,
        "corpus_loaded": False,
        "source": {
            "name": "linear",
            "verified": False,
            "credential": "api-key",
        },
    }

    with pytest.raises(RuntimeError, match="exposed credential"):
        verify_distribution_journey.verify_doctor(
            payload,
            "distribution-gate-placeholder-do-not-print",
            "distribution-gate-placeholder-do-not-print",
        )


def test_run_rejects_unexpected_exit_code() -> None:
    with pytest.raises(RuntimeError, match="exited 7"):
        verify_distribution_journey.run(
            [
                __import__("sys").executable,
                "-c",
                "raise SystemExit(7)",
            ],
            environment={},
        )


def test_parse_json_rejects_non_object() -> None:
    completed = subprocess.CompletedProcess(["embead"], 0, stdout="[]", stderr="")

    with pytest.raises(RuntimeError, match="must emit a JSON object"):
        verify_distribution_journey.parse_json(completed, "test")
