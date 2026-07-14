import json
import subprocess
from pathlib import Path

import pytest

from embead.beads import BeadsAdapter, BeadsError

FIXTURES = Path(__file__).parent / "fixtures"


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
                        "updated_at": "2026-07-14T05:30:00-07:00",
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
    assert records[0].updated_at == "2026-07-14T05:30:00-07:00"


def test_beads_1_0_5_relationship_fixture_preserves_targets_direction_and_type() -> None:
    payload = json.loads((FIXTURES / "beads-1.0.5-list.json").read_text())
    runner = FakeRunner([(0, payload, "")])

    records = BeadsAdapter(runner=runner).list_issues()

    assert sum(len(issue.dependency_links) for issue in records) == 3
    assert records[0].dependencies == ("sample-parent", "sample-prerequisite")
    assert [
        (link.source_id, link.target_id, link.relationship_type)
        for link in records[0].dependency_links
    ] == [
        ("sample-child", "sample-parent", "parent-child"),
        ("sample-child", "sample-prerequisite", "blocks"),
    ]
    assert records[1].dependency_links[0].relationship_type == "discovered-from"


def test_current_shape_prefers_target_over_source_issue_id() -> None:
    runner = FakeRunner(
        [
            (
                0,
                [
                    {
                        "id": "source",
                        "title": "Source",
                        "status": "open",
                        "dependencies": [
                            {
                                "issue_id": "source",
                                "depends_on_id": "target",
                                "type": "blocks",
                            }
                        ],
                    }
                ],
                "",
            )
        ]
    )
    issue = BeadsAdapter(runner=runner).list_issues()[0]
    assert issue.dependencies == ("target",)


def test_self_dependency_fails_closed_with_identifier_only_diagnostic() -> None:
    runner = FakeRunner(
        [
            (
                0,
                [
                    {
                        "id": "self-link",
                        "title": "No private body in error",
                        "description": "PRIVATE BODY",
                        "status": "open",
                        "dependencies": [{"depends_on_id": "self-link", "type": "blocks"}],
                    }
                ],
                "",
            )
        ]
    )
    with pytest.raises(BeadsError, match="issue self-link contains a self-dependency") as error:
        BeadsAdapter(runner=runner).list_issues()
    assert "PRIVATE BODY" not in str(error.value)


def test_load_reports_relationship_counts_in_snapshot() -> None:
    payload = json.loads((FIXTURES / "beads-1.0.5-list.json").read_text())
    runner = FakeRunner(
        [
            (0, {"project_id": "project", "beads_dir": "/tmp/project/.beads"}, ""),
            (0, {"version": "1.0.5"}, ""),
            (0, payload, ""),
        ]
    )
    snapshot, _records = BeadsAdapter(runner=runner).load()
    assert snapshot.dependency_count == 3
    assert snapshot.dependency_type_counts == (
        ("blocks", 1),
        ("discovered-from", 1),
        ("parent-child", 1),
    )


def test_load_warns_when_discoverable_export_is_stale(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir()
    (beads_dir / "issues.jsonl").write_text(
        json.dumps({"id": "export-only", "title": "Synthetic", "status": "open"}) + "\n"
    )
    live = [
        {"id": "live-1", "title": "One", "status": "open"},
        {"id": "live-2", "title": "Two", "status": "closed"},
    ]
    runner = FakeRunner(
        [
            (0, {"project_id": "project", "beads_dir": str(beads_dir)}, ""),
            (0, {"version": "1.0.5"}, ""),
            (0, live, ""),
        ]
    )

    snapshot, records = BeadsAdapter(runner=runner).load()

    assert len(records) == 2
    assert snapshot.acquisition_source == "live-beads-cli"
    assert snapshot.live_issue_count == 2
    assert snapshot.export_issue_count == 1
    assert snapshot.source_warnings == (
        "Live Beads data contains 2 issues while the discoverable JSONL export contains 1; "
        "live data was used.",
    )


def test_load_does_not_expose_malformed_export_content(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir()
    secret = "customer-secret-never-report"
    (beads_dir / "issues.jsonl").write_text(f"not-json-{secret}\n")
    runner = FakeRunner(
        [
            (0, {"project_id": "project", "beads_dir": str(beads_dir)}, ""),
            (0, {"version": "1.0.5"}, ""),
            (0, [{"id": "live", "title": "Live", "status": "open"}], ""),
        ]
    )

    snapshot, _records = BeadsAdapter(runner=runner).load()

    assert snapshot.export_issue_count is None
    assert snapshot.source_warnings == (
        "A discoverable Beads JSONL export could not be inspected safely.",
    )
    assert secret not in str(snapshot)


def test_load_warns_when_equal_count_export_has_different_state(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir()
    export_record = {
        "id": "same-id",
        "title": "Private export title",
        "status": "closed",
        "updated_at": "2026-07-13T00:00:00Z",
    }
    (beads_dir / "issues.jsonl").write_text(json.dumps(export_record) + "\n")
    live_record = {
        "id": "same-id",
        "title": "Different private live title",
        "status": "open",
        "updated_at": "2026-07-14T00:00:00Z",
    }
    runner = FakeRunner(
        [
            (0, {"project_id": "project", "beads_dir": str(beads_dir)}, ""),
            (0, {"version": "1.0.5"}, ""),
            (0, [live_record], ""),
        ]
    )

    snapshot, records = BeadsAdapter(runner=runner).load()

    assert records[0].updated_at == "2026-07-14T00:00:00Z"
    assert snapshot.live_issue_count == snapshot.export_issue_count == 1
    assert snapshot.live_source_digest != snapshot.export_source_digest
    assert snapshot.source_warnings == (
        "Live Beads data and the discoverable JSONL export have matching issue counts but "
        "different canonical state digests; live data was used.",
    )
    assert "Private" not in str(snapshot)


def test_load_accepts_matching_canonical_export_despite_private_text_difference(tmp_path) -> None:
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir()
    export_record = {
        "id": "same-id",
        "title": "Old private title",
        "status": "open",
        "updated_at": "2026-07-14T00:00:00Z",
    }
    (beads_dir / "issues.jsonl").write_text(json.dumps(export_record) + "\n")
    live_record = {
        **export_record,
        "title": "New private title",
    }
    runner = FakeRunner(
        [
            (0, {"project_id": "project", "beads_dir": str(beads_dir)}, ""),
            (0, {"version": "1.0.5"}, ""),
            (0, [live_record], ""),
        ]
    )

    snapshot, _records = BeadsAdapter(runner=runner).load()

    assert snapshot.live_source_digest == snapshot.export_source_digest
    assert snapshot.source_warnings == ()


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
