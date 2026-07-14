import json
import subprocess
from pathlib import Path

import pytest

from embead.beads import BeadsAdapter, BeadsError


class FakeRunner:
    def __init__(self, responses: list[tuple[int, object, str]]) -> None:
        self.responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, argv: object) -> subprocess.CompletedProcess[str]:
        args = list(argv)  # type: ignore[arg-type]
        self.calls.append(args)
        returncode, payload, stderr = self.responses.pop(0)
        stdout = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def test_list_invocation_is_read_only_and_parses_current_shape() -> None:
    runner = FakeRunner(
        [
            (
                0,
                [
                    {
                        "id": "bd-2",
                        "title": "Vector cache",
                        "description": "Cache vectors",
                        "status": "open",
                        "issue_type": "feature",
                        "priority": 1,
                        "labels": ["storage", "semantic"],
                        "parent_id": "bd-1",
                        "dependencies": [{"id": "bd-0"}],
                        "acceptance_criteria": "Atomic writes",
                        "design": "Content addressing",
                        "notes": "Cross-platform lock",
                    }
                ],
                "",
            )
        ]
    )
    records = BeadsAdapter(runner=runner).list_issues()
    assert runner.calls == [["bd", "--readonly", "list", "--all", "--limit", "0", "--json"]]
    assert records[0].id == "bd-2"
    assert records[0].issue_type == "feature"
    assert records[0].labels == ("semantic", "storage")
    assert records[0].dependencies == ("bd-0",)
    assert records[0].acceptance_criteria == "Atomic writes"


def test_list_parses_legacy_envelope_and_aliases() -> None:
    runner = FakeRunner(
        [
            (
                0,
                {
                    "issues": [
                        {
                            "id": "old-1",
                            "title": "Legacy",
                            "body": "Old description",
                            "status": "closed",
                            "type": "epic",
                            "priority": "P3",
                            "labels": [{"name": "old"}],
                            "parent": {"id": "old-root"},
                            "depends_on": [{"depends_on_id": "old-0"}],
                            "acceptanceCriteria": "Works",
                            "design_notes": "Simple",
                            "current_notes": "Done",
                        }
                    ]
                },
                "",
            )
        ]
    )
    issue = BeadsAdapter(runner=runner).list_issues()[0]
    assert issue.description == "Old description"
    assert issue.issue_type == "epic"
    assert issue.priority == 3
    assert issue.labels == ("old",)
    assert issue.parent_id == "old-root"
    assert issue.dependencies == ("old-0",)


def test_workspace_snapshot_uses_stable_explicit_identity() -> None:
    runner = FakeRunner(
        [
            (0, {"workspace_id": "workspace-123", "path": "/tmp/project/.beads"}, ""),
            (0, {"version": "1.0.5"}, ""),
        ]
    )
    snapshot = BeadsAdapter(runner=runner).workspace_snapshot()
    assert snapshot.workspace_id == "workspace-123"
    assert snapshot.beads_version == "1.0.5"
    assert snapshot.workspace_path == str(Path("/tmp/project/.beads").resolve())
    assert runner.calls == [
        ["bd", "--readonly", "context", "--json"],
        ["bd", "--readonly", "version", "--json"],
    ]


@pytest.mark.parametrize(
    "payload",
    ["not json", {"unexpected": []}, [{"id": "bd-1", "title": "Missing status"}]],
)
def test_list_fails_closed_on_malformed_or_unknown_shapes(payload: object) -> None:
    runner = FakeRunner([(0, payload, "")])
    with pytest.raises(BeadsError):
        BeadsAdapter(runner=runner).list_issues()


def test_nonzero_exit_is_bounded_and_does_not_fall_back() -> None:
    runner = FakeRunner([(2, "", "database unavailable")])
    with pytest.raises(BeadsError, match="database unavailable"):
        BeadsAdapter(runner=runner).list_issues()
    assert len(runner.calls) == 1


def test_command_allowlist_rejects_mutation_before_runner() -> None:
    runner = FakeRunner([])
    adapter = BeadsAdapter(runner=runner)
    with pytest.raises(BeadsError, match="not allowlisted"):
        adapter._run("update", "bd-1")
    assert runner.calls == []
