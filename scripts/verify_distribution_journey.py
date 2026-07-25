#!/usr/bin/env python3
"""Exercise the supported install journeys against a freshly built wheel."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def discover_wheel(directory: Path) -> Path:
    """Require exactly one wheel so the journey cannot select a stale artifact."""
    wheels = sorted(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one wheel in {directory}, found {len(wheels)}")
    return wheels[0].resolve()


def wheel_version(wheel: Path) -> str:
    """Read the version from the artifact under test, not the checkout."""
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise RuntimeError("wheel must contain exactly one METADATA file")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
    match = re.search(r"^Version: (.+)$", metadata, flags=re.MULTILINE)
    if match is None:
        raise RuntimeError("wheel metadata does not contain a version")
    return match.group(1).strip()


def run(
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
    expected_codes: frozenset[int] = frozenset({0}),
) -> tuple[subprocess.CompletedProcess[str], float]:
    """Run a journey step and preserve its elapsed time for the CI receipt."""
    started = time.monotonic()
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        shell=False,
    )
    elapsed = time.monotonic() - started
    if completed.returncode not in expected_codes:
        raise RuntimeError(
            f"{command[0]} exited {completed.returncode}; "
            f"stdout={completed.stdout!r}; stderr={completed.stderr!r}"
        )
    return completed, elapsed


def parse_json(completed: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{label} did not emit JSON: {completed.stdout!r}") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} must emit a JSON object")
    return payload


def verify_version(completed: subprocess.CompletedProcess[str], version: str, label: str) -> None:
    expected = f"embead {version}"
    if completed.stdout.strip() != expected:
        raise RuntimeError(f"{label} reported {completed.stdout.strip()!r}; expected {expected!r}")


def verify_capabilities(payload: Mapping[str, Any]) -> None:
    if payload.get("document_type") != "embeadings-capabilities":
        raise RuntimeError("capabilities reported an unexpected document type")
    if payload.get("protocol_version") != 1:
        raise RuntimeError("capabilities reported an unexpected protocol version")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or "read-only-review" not in capabilities:
        raise RuntimeError("capabilities omitted the required read-only contract")
    if payload.get("required_capabilities") != ["read-only-review"]:
        raise RuntimeError("capabilities changed the required consumer contract")


def verify_doctor(payload: Mapping[str, Any], raw_output: str, sentinel: str) -> None:
    if payload.get("read_only") is not True or payload.get("corpus_loaded") is not False:
        raise RuntimeError("doctor did not preserve its corpus-free, read-only contract")
    source = payload.get("source")
    if not isinstance(source, dict):
        raise RuntimeError("doctor omitted its source receipt")
    if source.get("name") != "linear" or source.get("verified") is not False:
        raise RuntimeError("doctor attempted or claimed a live Linear verification")
    if source.get("credential") != "api-key":
        raise RuntimeError("doctor did not recognize the isolated placeholder credential")
    if sentinel in raw_output:
        raise RuntimeError("doctor exposed credential text")


def directory_bytes(directory: Path) -> int:
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def executable_name() -> str:
    return "embead.exe" if os.name == "nt" else "embead"


def repository_status(environment: Mapping[str, str]) -> str | None:
    """Return a stable repository mutation signal when Git is available."""
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        shell=False,
    )
    return completed.stdout if completed.returncode == 0 else None


def journey(wheel: Path, uv: str, uvx: str) -> dict[str, Any]:
    """Run persistent and one-shot journeys inside disposable roots."""
    version = wheel_version(wheel)
    sentinel = "distribution-gate-placeholder-do-not-print"
    receipt: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix="embead-distribution-") as temporary:
        scratch = Path(temporary)
        tool_dir = scratch / "tools"
        bin_dir = scratch / "bin"
        uv_cache = scratch / "uv-cache"
        home = scratch / "home"
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "LOCALAPPDATA": str(home / "AppData" / "Local"),
                "XDG_CACHE_HOME": str(scratch / "xdg-cache"),
                "XDG_STATE_HOME": str(scratch / "xdg-state"),
                "UV_CACHE_DIR": str(uv_cache),
                "UV_NO_PROGRESS": "1",
                "UV_PYTHON_DOWNLOADS": "never",
                "UV_TOOL_BIN_DIR": str(bin_dir),
                "UV_TOOL_DIR": str(tool_dir),
                "LINEAR_API_KEY": sentinel,
                "PATH": os.pathsep.join((str(bin_dir), environment.get("PATH", ""))),
            }
        )
        environment.pop("LINEAR_ACCESS_TOKEN", None)
        repository_before = repository_status(environment)
        if repository_before is None:
            raise RuntimeError("Git repository status is unavailable for the mutation check")
        uv_version, _ = run([uv, "--version"], environment=environment)

        install, install_seconds = run(
            [uv, "tool", "install", "--python", sys.executable, str(wheel)],
            environment=environment,
        )
        installed_cli = bin_dir / executable_name()
        if not installed_cli.is_file():
            raise RuntimeError(f"persistent install did not create {installed_cli}")
        discovered_cli = shutil.which("embead", path=str(bin_dir))
        if discovered_cli is None or Path(discovered_cli).resolve() != installed_cli.resolve():
            raise RuntimeError("persistent command was not discoverable from UV_TOOL_BIN_DIR")

        persistent_version, persistent_version_seconds = run(
            [str(installed_cli), "--version"], environment=environment
        )
        verify_version(persistent_version, version, "persistent CLI")
        persistent_capabilities, persistent_capabilities_seconds = run(
            [str(installed_cli), "capabilities", "--json"], environment=environment
        )
        verify_capabilities(parse_json(persistent_capabilities, "persistent capabilities"))
        persistent_doctor, persistent_doctor_seconds = run(
            [
                str(installed_cli),
                "--source",
                "linear",
                "--linear-team",
                "DISTRIBUTION-GATE",
                "doctor",
                "--json",
            ],
            environment=environment,
        )
        verify_doctor(
            parse_json(persistent_doctor, "persistent doctor"),
            persistent_doctor.stdout,
            sentinel,
        )

        one_shot_version, one_shot_version_seconds = run(
            [
                uvx,
                "--python",
                sys.executable,
                "--from",
                str(wheel),
                "embead",
                "--version",
            ],
            environment=environment,
        )
        verify_version(one_shot_version, version, "one-shot CLI")
        one_shot_capabilities, one_shot_capabilities_seconds = run(
            [
                uvx,
                "--python",
                sys.executable,
                "--from",
                str(wheel),
                "embead",
                "capabilities",
                "--json",
            ],
            environment=environment,
        )
        verify_capabilities(parse_json(one_shot_capabilities, "one-shot capabilities"))
        one_shot_doctor, one_shot_doctor_seconds = run(
            [
                uvx,
                "--python",
                sys.executable,
                "--from",
                str(wheel),
                "embead",
                "--source",
                "linear",
                "--linear-team",
                "DISTRIBUTION-GATE",
                "doctor",
                "--json",
            ],
            environment=environment,
        )
        verify_doctor(
            parse_json(one_shot_doctor, "one-shot doctor"),
            one_shot_doctor.stdout,
            sentinel,
        )

        uninstall, uninstall_seconds = run(
            [uv, "tool", "uninstall", "embeadings"], environment=environment
        )
        if installed_cli.exists() or shutil.which("embead", path=str(bin_dir)) is not None:
            raise RuntimeError("persistent uninstall left the embead command discoverable")
        repository_after = repository_status(environment)
        if repository_before != repository_after:
            raise RuntimeError("distribution journey changed the invoking repository")

        receipt = {
            "artifact": wheel.name,
            "artifact_bytes": wheel.stat().st_size,
            "cleanup": {
                "persistent_command_removed": True,
                "scratch_root_removed": False,
            },
            "journey_version": 1,
            "limitations": [
                "local wheel substituted for the not-yet-published source revision",
                "doctor used corpus-free Linear configuration and made no API request",
                (
                    "semantic triage, external bd discovery, pipx, upgrade, and registry "
                    "provenance were not measured"
                ),
            ],
            "path_intervention": "isolated UV_TOOL_BIN_DIR prepended for command discovery",
            "platform": platform.platform(),
            "python": platform.python_version(),
            "repository_status_unchanged": True,
            "timings_seconds": {
                "persistent_capabilities": round(persistent_capabilities_seconds, 3),
                "persistent_doctor": round(persistent_doctor_seconds, 3),
                "persistent_install": round(install_seconds, 3),
                "persistent_uninstall": round(uninstall_seconds, 3),
                "persistent_version": round(persistent_version_seconds, 3),
                "one_shot_capabilities": round(one_shot_capabilities_seconds, 3),
                "one_shot_doctor": round(one_shot_doctor_seconds, 3),
                "one_shot_version": round(one_shot_version_seconds, 3),
                "time_to_first_doctor": round(
                    install_seconds
                    + persistent_version_seconds
                    + persistent_capabilities_seconds
                    + persistent_doctor_seconds,
                    3,
                ),
            },
            "uv_cache_bytes": directory_bytes(uv_cache),
            "uv_cache_bytes_note": "materialized cache size; not network-transfer telemetry",
            "uv_install_output_present": bool(install.stderr.strip() or install.stdout.strip()),
            "uv_uninstall_output_present": bool(
                uninstall.stderr.strip() or uninstall.stdout.strip()
            ),
            "uv_version": uv_version.stdout.strip(),
            "version": version,
        }
    if Path(temporary).exists():
        raise RuntimeError("disposable distribution root was not removed")
    receipt["cleanup"]["scratch_root_removed"] = True
    return receipt


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(arguments)
    wheel = discover_wheel(args.dist)
    uv = shutil.which("uv")
    uvx = shutil.which("uvx")
    if uv is None or uvx is None:
        raise RuntimeError("uv and uvx must be installed before running the distribution journey")
    rendered = json.dumps(journey(wheel, uv, uvx), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"distribution journey failed: {error}", file=sys.stderr)
        raise SystemExit(2) from None
