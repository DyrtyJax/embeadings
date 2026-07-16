from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from embead import __version__

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "plugins" / "embeadings"
WRAPPER = PLUGIN / "scripts" / "run-embeadings"
LAUNCHER = PLUGIN / "scripts" / "run_embeadings.py"


def _manifest(host: str) -> dict[str, object]:
    return json.loads((PLUGIN / host / "plugin.json").read_text())


def _report(*, report_type: str = "sweep", tracker_name: str = "beads") -> dict[str, object]:
    return {
        "schema_version": 1,
        "report_type": report_type,
        "policy": {
            "read_only": True,
            "tracker_mutation_allowed": False,
        },
        "snapshot": {"tracker_name": tracker_name},
        "candidates": [],
    }


def _stub_environment(
    tmp_path: Path,
    *,
    version: str = "0.3.0",
    payload: dict[str, object] | str | None = None,
    install_cli: bool = True,
) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    arguments_path = tmp_path / "arguments.json"
    if install_cli:
        stub_program = bin_dir / "embead_stub.py"
        stub_program.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys

if sys.argv[1:] == ["--version"]:
    print(os.environ["EMBEAD_STUB_VERSION"])
    raise SystemExit(0)

with open(os.environ["EMBEAD_STUB_ARGUMENTS"], "w", encoding="utf-8") as stream:
    json.dump(sys.argv[1:], stream)
sys.stdout.write(os.environ["EMBEAD_STUB_PAYLOAD"])
"""
        )
        if os.name == "nt":
            stub = bin_dir / "embead.cmd"
            stub.write_text(f'@"{sys.executable}" "{stub_program}" %*\n')
        else:
            stub = bin_dir / "embead"
            stub.write_text(stub_program.read_text())
            stub.chmod(0o755)

    if payload is None:
        payload = _report()
    rendered_payload = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True)
    environment = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
        "EMBEAD_STUB_ARGUMENTS": str(arguments_path),
        "EMBEAD_STUB_PAYLOAD": rendered_payload,
        "EMBEAD_STUB_VERSION": f"embead {version}",
    }
    return environment, arguments_path


def _run_wrapper(
    tmp_path: Path,
    *arguments: str,
    version: str = "0.3.0",
    payload: dict[str, object] | str | None = None,
    install_cli: bool = True,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    environment, arguments_path = _stub_environment(
        tmp_path,
        version=version,
        payload=payload,
        install_cli=install_cli,
    )
    completed = subprocess.run(
        [sys.executable, str(LAUNCHER), *arguments],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )
    return completed, arguments_path


def test_plugin_manifests_match_package_identity_and_version() -> None:
    codex = _manifest(".codex-plugin")
    claude = _manifest(".claude-plugin")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    hatch = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]

    assert codex["name"] == claude["name"] == PLUGIN.name == "embeadings"
    assert project["dynamic"] == ["version"]
    assert hatch["version"]["path"] == "src/embead/_version.py"
    assert codex["version"] == claude["version"] == __version__
    assert codex["description"] == claude["description"]
    assert LAUNCHER.is_file()
    if os.name != "nt":
        assert WRAPPER.stat().st_mode & 0o111


def test_launcher_check_reports_cross_platform_contract(tmp_path: Path) -> None:
    completed, arguments_path = _run_wrapper(tmp_path, "check")

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "cli": "embead 0.3.0",
        "json_schema_version": 1,
        "status": "ready",
    }
    assert completed.stderr == ""
    assert not arguments_path.exists()


def test_wrapper_reports_missing_cli_without_running_tracker(tmp_path: Path) -> None:
    completed, arguments_path = _run_wrapper(tmp_path, "sweep", install_cli=False)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "embead was not found on PATH" in completed.stderr
    assert not arguments_path.exists()


@pytest.mark.parametrize("version", ["0.2.9", "0.3.0rc1", "not-a-version"])
def test_wrapper_rejects_old_or_unrecognized_cli_versions(tmp_path: Path, version: str) -> None:
    completed, arguments_path = _run_wrapper(tmp_path, "sweep", version=version)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "embeadings>=0.3.0 is required" in completed.stderr
    assert not arguments_path.exists()


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (("sweep",), ["sweep", "--json"]),
        (("--source", "beads", "collisions"), ["--source", "beads", "collisions", "--json"]),
        (("sweep", "--json"), ["sweep", "--json"]),
    ],
)
def test_wrapper_forces_exactly_one_json_flag(
    tmp_path: Path, arguments: tuple[str, ...], expected: list[str]
) -> None:
    report_type = "collisions" if "collisions" in arguments else "sweep"
    completed, arguments_path = _run_wrapper(
        tmp_path,
        *arguments,
        payload=_report(report_type=report_type),
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(arguments_path.read_text()) == expected


@pytest.mark.parametrize(
    "blocked_arguments",
    [
        ("sweep", "--output", "report.json"),
        ("sweep", "--output=report.json"),
        ("sweep", "--write-checkpoint", "checkpoint.json"),
        ("sweep", "--write-checkpoint=checkpoint.json"),
    ],
)
def test_wrapper_rejects_file_write_options_before_cli_execution(
    tmp_path: Path, blocked_arguments: tuple[str, ...]
) -> None:
    completed, arguments_path = _run_wrapper(tmp_path, *blocked_arguments)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "file-writing options are disabled" in completed.stderr
    assert not arguments_path.exists()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({**_report(), "schema_version": 2}, "unsupported report contract"),
        ({**_report(), "report_type": "collisions"}, "unsupported report contract"),
        (
            {**_report(), "policy": {"read_only": False, "tracker_mutation_allowed": False}},
            "did not assert read-only policy",
        ),
        (
            {**_report(), "policy": {"read_only": True, "tracker_mutation_allowed": True}},
            "did not prohibit tracker mutation",
        ),
        ({**_report(), "snapshot": {"tracker_name": "unknown"}}, "unsupported tracker metadata"),
    ],
)
def test_wrapper_rejects_unsupported_or_mutating_report_contracts(
    tmp_path: Path, payload: dict[str, object], message: str
) -> None:
    completed, _ = _run_wrapper(tmp_path, "sweep", payload=payload)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert message in completed.stderr


@pytest.mark.parametrize("tracker_name", ["beads", "linear"])
def test_wrapper_passes_through_valid_read_only_report(tmp_path: Path, tracker_name: str) -> None:
    payload = _report(tracker_name=tracker_name)
    completed, _ = _run_wrapper(tmp_path, "sweep", payload=payload)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == payload
    assert completed.stderr == ""
