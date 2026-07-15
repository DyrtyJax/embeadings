from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from embead.models import IssueRecord
from embead.surfaces import (
    analyze_code_surfaces,
    extract_explicit_pointers,
    parse_worktree_mappings,
)


def completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], returncode, stdout=stdout, stderr="")


def test_explicit_paths_are_conservative_and_never_copy_snippets() -> None:
    issue = IssueRecord(
        id="proj-1",
        title="Change `src/parser/dependencies.py::parse_dependency` and `README.md`",
        description=(
            "Coordinate foo/bar prose, https://example.com/src/private.py, and package version "
            "releases/1.2.3. Update docs/parser/ as well."
        ),
    )

    pointers = extract_explicit_pointers(issue, revision="abc123")

    assert [(item.path, item.symbol) for item in pointers] == [
        ("README.md", None),
        ("docs/parser/", None),
        ("src/parser/dependencies.py", "parse_dependency"),
    ]
    assert {item.source_field for item in pointers} == {"description", "title"}
    assert all(not hasattr(item, "snippet") for item in pointers)


def test_explicit_surfaces_report_exact_and_module_collisions_without_git() -> None:
    issues = [
        IssueRecord(id="proj-1", title="Edit src/parser/dependencies.py"),
        IssueRecord(id="proj-2", title="Repair src/parser/dependencies.py"),
        IssueRecord(id="proj-3", title="Test src/parser/payload.py"),
        IssueRecord(id="proj-4", title="Unrelated prose"),
    ]

    analysis = analyze_code_surfaces(issues, workspace_path=None)

    assert analysis.repository_available is False
    assert analysis.pointer_count == 3
    assert analysis.issues_without_surfaces == 1
    assert [item.kind for item in analysis.collisions] == [
        "exact-file",
        "shared-module",
        "shared-module",
    ]
    exact = analysis.collisions[0]
    assert exact.shared_paths == ("src/parser/dependencies.py",)
    assert exact.confidence == "explicit"
    assert exact.revision_relation == "unavailable"
    assert analysis.warnings == (
        "No Git repository was available; only explicit code references were analyzed.",
    )


def test_shared_directory_pointer_is_module_evidence_not_exact_file() -> None:
    issues = [
        IssueRecord(id="proj-1", title="Update `src/parser/`"),
        IssueRecord(id="proj-2", title="Refactor `src/parser/`"),
    ]

    analysis = analyze_code_surfaces(issues, workspace_path=None)

    assert len(analysis.collisions) == 1
    collision = analysis.collisions[0]
    assert collision.kind == "shared-module"
    assert collision.shared_paths == ()
    assert collision.shared_modules == ("src/parser",)


def test_shared_path_symbol_is_preserved_as_bounded_evidence() -> None:
    issues = [
        IssueRecord(id="proj-1", title="Change `src/parser/core.py::parse`"),
        IssueRecord(id="proj-2", title="Repair `src/parser/core.py::parse`"),
    ]

    collision = analyze_code_surfaces(issues, workspace_path=None).collisions[0]

    assert collision.shared_paths == ("src/parser/core.py",)
    assert collision.shared_symbols == ("src/parser/core.py::parse",)


def test_worktree_diffs_are_observed_and_revision_bound(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    first = tmp_path / "worktree-1"
    second = tmp_path / "worktree-2"
    root.mkdir()
    first.mkdir()
    second.mkdir()

    def runner(cwd: Path, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        command = tuple(arguments)
        if command == ("rev-parse", "--is-inside-work-tree"):
            return completed("true\n")
        if command == ("rev-parse", "HEAD"):
            return completed("root-head\n")
        if command == ("rev-parse", "--verify", "origin/main"):
            return completed("base-head\n")
        if command == ("rev-parse", "origin/main"):
            return completed("base-head\n")
        if command == ("worktree", "list", "--porcelain"):
            return completed(
                f"worktree {root}\nHEAD root-head\nbranch refs/heads/main\n\n"
                f"worktree {first}\nHEAD head-one\nbranch refs/heads/codex/bead-1-parser\n\n"
                f"worktree {second}\nHEAD head-two\nbranch refs/heads/codex/bead-2-cache\n"
            )
        if command[:4] == ("diff", "--name-only", "--diff-filter=ACMRD", "-z"):
            changed = {
                first.resolve(): (
                    "src/shared/cache.py\0src/first/only.py\0.beads/interactions.jsonl\0"
                ),
                second.resolve(): "src/shared/cache.py\0src/second/only.py\0",
            }
            return completed(changed.get(cwd.resolve(), ""))
        if command == ("ls-files", "--others", "--exclude-standard", "-z"):
            return completed()
        raise AssertionError((cwd, arguments))

    issues = [IssueRecord(id="proj.1", title="First"), IssueRecord(id="proj.2", title="Second")]
    analysis = analyze_code_surfaces(issues, workspace_path=root, runner=runner)

    assert analysis.issues_with_observed_surfaces == 2
    assert analysis.base_revision == "base-head"
    assert analysis.worktrees_discovered == 3
    assert analysis.worktrees_associated == 2
    assert analysis.source_counts == {"active-worktree-diff": 4}
    assert len(analysis.collisions) == 1
    collision = analysis.collisions[0]
    assert collision.kind == "exact-file"
    assert collision.confidence == "observed"
    assert collision.shared_paths == ("src/shared/cache.py",)
    assert collision.revision_relation == "different"


def test_explicit_mapping_validates_issue_and_registered_worktree(tmp_path: Path) -> None:
    mappings = parse_worktree_mappings([f"proj.1={tmp_path}"])
    assert mappings == {"proj.1": tmp_path.resolve()}

    with pytest.raises(ValueError, match="ISSUE_ID=PATH"):
        parse_worktree_mappings(["proj.1"])
    with pytest.raises(ValueError, match="duplicate"):
        parse_worktree_mappings([f"proj.1={tmp_path}", f"proj.1={tmp_path}"])
