from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def _release_workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_scopes_oidc_to_publishing_jobs() -> None:
    workflow = _release_workflow()

    assert "\npermissions:\n" not in workflow
    assert workflow.count("      id-token: write") == 2
    assert "  build:\n" in workflow
    assert "    permissions:\n      contents: read\n" in workflow


def test_pypi_job_uses_trusted_publishing_without_a_stored_token() -> None:
    workflow = _release_workflow()

    pypi_job = workflow.split("  pypi-publish:\n", maxsplit=1)[1]
    assert "name: pypi" in pypi_job
    assert "url: https://pypi.org/p/embeadings" in pypi_job
    assert "id-token: write" in pypi_job
    assert "password:" not in pypi_job
    assert "secrets." not in pypi_job
    assert "pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b" in pypi_job


def test_release_jobs_reuse_verified_build_artifacts() -> None:
    workflow = _release_workflow()

    assert workflow.count("python -m build") == 1
    assert workflow.count("scripts/verify_release.py") == 1
    assert workflow.count("name: verified-release-bundle") == 3
    assert workflow.count("sha256sum -c ../SHA256SUMS") == 2
    assert "pypi-distributions" not in workflow
    assert "needs:\n      - build\n      - github-release" in workflow
    assert "packages-dir: release/packages/" in workflow
