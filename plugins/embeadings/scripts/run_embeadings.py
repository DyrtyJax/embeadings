#!/usr/bin/env python3
"""Cross-platform, read-only plugin boundary for the installed embead CLI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence

MINIMUM_VERSION = (0, 3, 0)
SUPPORTED_REPORTS = {"sweep", "collisions"}
SUPPORTED_TRACKERS = {"beads", "linear"}
VALUE_OPTIONS = {"--source", "--linear-team", "--provider"}
WRITE_OPTIONS = {"--output", "--write-checkpoint"}


def fail(message: str) -> None:
    print(f"embeadings plugin: {message}", file=sys.stderr)
    raise SystemExit(2)


def find_cli() -> tuple[str, str]:
    executable = shutil.which("embead")
    if executable is None:
        fail("embead was not found on PATH; install embeadings>=0.3.0 first")

    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        fail("embead --version failed")
    if completed.returncode != 0:
        fail("embead --version failed")

    rendered = completed.stdout.strip()
    match = re.fullmatch(
        r"embead (\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?",
        rendered,
    )
    if match is None or tuple(map(int, match.groups())) < MINIMUM_VERSION:
        fail(f"embeadings>=0.3.0 is required; found {rendered}")
    return executable, rendered


def inspect_arguments(arguments: Sequence[str]) -> tuple[str, list[str]]:
    if not arguments:
        fail("expected a sweep or collisions command")

    report_type: str | None = None
    json_requested = False
    skip_value = False
    for argument in arguments:
        if skip_value:
            skip_value = False
            continue
        if argument in VALUE_OPTIONS:
            skip_value = True
        elif any(argument.startswith(f"{option}=") for option in VALUE_OPTIONS):
            continue
        elif argument in WRITE_OPTIONS or any(
            argument.startswith(f"{option}=") for option in WRITE_OPTIONS
        ):
            fail("file-writing options are disabled at the plugin boundary")
        elif argument == "--json":
            json_requested = True
        elif argument in SUPPORTED_REPORTS and report_type is None:
            report_type = argument

    if skip_value:
        fail("a global option is missing its value")
    if report_type is None:
        fail("only sweep and collisions reports are supported")

    command_arguments = list(arguments)
    if not json_requested:
        command_arguments.append("--json")
    return report_type, command_arguments


def validate_report(raw: str, expected_report: str) -> None:
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"CLI returned invalid JSON: {exc}")

    if (
        not isinstance(report, dict)
        or report.get("schema_version") != 1
        or report.get("report_type") != expected_report
    ):
        fail("CLI returned an unsupported report contract")

    policy = report.get("policy")
    if not isinstance(policy, dict) or policy.get("read_only") is not True:
        fail("report did not assert read-only policy")
    if policy.get("tracker_mutation_allowed") is not False:
        fail("report did not prohibit tracker mutation")

    snapshot = report.get("snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("tracker_name") not in SUPPORTED_TRACKERS:
        fail("report has unsupported tracker metadata")


def main(arguments: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    executable, version = find_cli()

    if arguments[:1] == ["check"]:
        if len(arguments) != 1:
            fail("check does not accept arguments")
        print(
            json.dumps(
                {"cli": version, "json_schema_version": 1, "status": "ready"},
                sort_keys=True,
            )
        )
        return 0

    report_type, command_arguments = inspect_arguments(arguments)
    try:
        completed = subprocess.run(
            [executable, *command_arguments],
            check=False,
            stdout=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        fail(f"embead execution failed: {exc}")
    if completed.returncode != 0:
        return completed.returncode

    validate_report(completed.stdout, report_type)
    sys.stdout.write(completed.stdout)
    if completed.stdout and not completed.stdout.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
