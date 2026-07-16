#!/usr/bin/env python3
"""Verify and checksum release artifacts in a disposable wheel environment."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import runpy
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SDIST_ALLOWED_TOP_LEVEL = frozenset(
    {
        ".gitignore",
        "LICENSE",
        "PKG-INFO",
        "README.md",
        "pyproject.toml",
        "schemas",
        "src",
    }
)


def project_version() -> str:
    """Read the version without importing the editable project."""
    namespace = runpy.run_path(ROOT / "src" / "embead" / "_version.py")
    return str(namespace["__version__"])


def artifact_version(wheel: Path) -> str:
    """Read the canonical package version from wheel metadata."""
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


def source_artifact_version(source_archive: Path) -> str:
    """Read the canonical package version from source-distribution metadata."""
    with tarfile.open(source_archive, mode="r:gz") as archive:
        metadata_members = [
            member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")
        ]
        if len(metadata_members) != 1:
            raise RuntimeError("source archive must contain exactly one PKG-INFO file")
        extracted = archive.extractfile(metadata_members[0])
        if extracted is None:
            raise RuntimeError("source archive PKG-INFO is not a regular file")
        metadata = extracted.read().decode("utf-8")
    match = re.search(r"^Version: (.+)$", metadata, flags=re.MULTILINE)
    if match is None:
        raise RuntimeError("source archive metadata does not contain a version")
    return match.group(1).strip()


def source_archive_paths(source_archive: Path) -> tuple[PurePosixPath, ...]:
    """Return regular-file paths relative to the source distribution root."""
    with tarfile.open(source_archive, mode="r:gz") as archive:
        members = [PurePosixPath(member.name) for member in archive.getmembers() if member.isfile()]
    roots = {member.parts[0] for member in members if member.parts}
    if len(roots) != 1:
        raise RuntimeError("source archive must contain exactly one root directory")
    root = next(iter(roots))
    return tuple(
        PurePosixPath(*member.parts[1:])
        for member in members
        if member.parts and member.parts[0] == root
    )


def verify_source_contents(source_archive: Path) -> None:
    """Require package inputs while rejecting repository-only release baggage."""
    paths = source_archive_paths(source_archive)
    path_names = {path.as_posix() for path in paths}
    required_files = {"LICENSE", "PKG-INFO", "README.md", "pyproject.toml"}
    missing_files = sorted(required_files - path_names)
    missing_trees = [
        prefix
        for prefix in ("schemas/v1/", "src/embead/")
        if not any(name.startswith(prefix) for name in path_names)
    ]
    if missing_files or missing_trees:
        missing = ", ".join([*missing_files, *missing_trees])
        raise RuntimeError(f"source archive is missing required package content: {missing}")

    unexpected = sorted(
        path.as_posix()
        for path in paths
        if path.parts
        and (
            path.parts[0] not in SDIST_ALLOWED_TOP_LEVEL
            or path.suffix.casefold() == ".log"
            or path.name == ".coverage"
        )
    )
    if unexpected:
        preview = ", ".join(unexpected[:5])
        raise RuntimeError(f"source archive contains repository-only content: {preview}")


def discover_artifacts(directory: Path) -> tuple[Path, Path]:
    """Require one wheel and one source archive."""
    wheels = sorted(directory.glob("*.whl"))
    source_archives = sorted(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(source_archives) != 1:
        raise RuntimeError("dist must contain exactly one wheel and one .tar.gz source archive")
    return wheels[0], source_archives[0]


def environment_python(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def smoke_install(artifact: Path, expected_version: str) -> None:
    """Install a distribution artifact and verify the public CLI version."""
    with tempfile.TemporaryDirectory(prefix="embead-release-") as temporary:
        environment = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment_python(environment)
        subprocess.run([str(python), "-m", "pip", "install", str(artifact)], check=True)
        completed = subprocess.run(
            [str(python), "-m", "embead.cli", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        if completed.stdout.strip() != f"embead {expected_version}":
            raise RuntimeError(
                f"installed CLI reported {completed.stdout.strip()!r}; "
                f"expected 'embead {expected_version}'"
            )


def write_checksums(directory: Path, artifacts: Sequence[Path]) -> Path:
    """Write stable SHA-256 receipts for release assets."""
    destination = directory / "SHA256SUMS"
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" for path in artifacts]
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", default=project_version())
    parser.add_argument("--dist", type=Path, default=DIST)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args(arguments)

    wheel, source_archive = discover_artifacts(args.dist)
    version = artifact_version(wheel)
    if version != args.expected_version:
        raise RuntimeError(f"wheel version {version} does not match {args.expected_version}")
    source_version = source_artifact_version(source_archive)
    if source_version != args.expected_version:
        raise RuntimeError(
            f"source archive version {source_version} does not match {args.expected_version}"
        )
    verify_source_contents(source_archive)
    smoke_install(wheel, args.expected_version)
    smoke_install(source_archive, args.expected_version)
    if args.write_checksums:
        write_checksums(args.dist, (wheel, source_archive))
    print(f"verified embeadings {version}: {wheel.name}, {source_archive.name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"release verification failed: {error}", file=sys.stderr)
        raise SystemExit(2) from None
