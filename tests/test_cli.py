import json

from embead import cli
from embead.models import IssueRecord, WorkspaceSnapshot
from embead.provider import HashingProvider
from embead.ranking import CandidateRanking

ISSUES = (
    IssueRecord(
        id="demo-1",
        title="Persist authentication tokens",
        description="Keep users signed in across browser restarts",
        status="open",
    ),
    IssueRecord(
        id="demo-2",
        title="Remember login state",
        description="Store authentication tokens between sessions",
        status="closed",
    ),
    IssueRecord(
        id="demo-3",
        title="Lazy load gallery images",
        description="Defer thumbnail loading until images are visible",
        status="open",
    ),
)


class FakeAdapter:
    def load(self):
        return WorkspaceSnapshot("workspace-test", "1.0.5", "/tmp/demo/.beads"), ISSUES


def _configure(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "BeadsAdapter", FakeAdapter)
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=32))
    monkeypatch.setattr(
        cli, "_workspace_paths", lambda _identity: (tmp_path / "cache", tmp_path / "state")
    )


def test_neighbors_json_stdout_is_machine_readable(monkeypatch, tmp_path, capsys) -> None:
    _configure(monkeypatch, tmp_path)

    assert cli.main(["neighbors", "demo-1", "--include-closed", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["report_type"] == "neighbors"
    assert payload["policy"]["read_only"] is True
    assert {item["id"] for item in payload["neighbors"]} == {"demo-2", "demo-3"}


def test_sweep_writes_versioned_reports_outside_workspace(monkeypatch, tmp_path, capsys) -> None:
    _configure(monkeypatch, tmp_path)
    output = tmp_path / "artifacts"

    assert cli.main(["sweep", "--size", "1", "--output", str(output), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["parameters"]["candidate_policy"]["max_per_issue"] == 3
    assert payload["parameters"]["candidate_policy"]["max_dependencies_per_issue"] == 3
    assert payload["parameters"]["candidate_policy"]["max_total"] == 250
    assert payload["parameters"]["candidate_policy"]["lane_caps"] == {
        "dependency": 75,
        "echo": 125,
        "overlap": 125,
    }
    assert set(payload["parameters"]["candidate_policy"]["lanes"]) == {
        "dependency",
        "echo",
        "overlap",
    }
    assert payload["capped_typed_dependencies"] == []
    assert payload["batches"] == []
    assert payload["no_signal"] == {"count": 2, "issue_ids": ["demo-1", "demo-3"]}
    assert set(payload["timings_ms"]) == {
        "acquisition",
        "embedding_and_cache",
        "similarity_scoring",
        "candidate_analysis",
        "batching",
    }
    assert all(value >= 0 for value in payload["timings_ms"].values())
    assert (output / "report.json").is_file()
    assert (output / "report.md").is_file()
    assert list(output.glob("batch-*.json")) == []


def test_sweep_propagates_non_sensitive_source_warning(monkeypatch, tmp_path, capsys) -> None:
    warning = (
        "Live Beads data contains 3 issues while the discoverable JSONL export contains 2; "
        "live data was used."
    )

    class StaleExportAdapter:
        def load(self):
            return (
                WorkspaceSnapshot(
                    "workspace-test",
                    "1.0.5",
                    "/tmp/demo/.beads",
                    acquisition_source="live-beads-cli",
                    live_issue_count=3,
                    export_issue_count=2,
                    source_warnings=(warning,),
                ),
                ISSUES,
            )

    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "BeadsAdapter", StaleExportAdapter)

    assert cli.main(["sweep", "--output", str(tmp_path / "out"), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["warnings"] == [warning]
    assert payload["snapshot"]["acquisition_source"] == "live-beads-cli"
    assert payload["snapshot"]["live_issue_count"] == 3
    assert payload["snapshot"]["export_issue_count"] == 2


def test_sweep_rejects_invalid_candidate_volume_controls(monkeypatch, tmp_path, capsys) -> None:
    _configure(monkeypatch, tmp_path)

    assert cli.main(["sweep", "--max-candidates", "0", "--json"]) == 2

    assert "run candidate cap must be positive" in capsys.readouterr().err


def test_ranked_candidates_keep_structural_admission_and_specific_explanation() -> None:
    issues = (
        IssueRecord(
            id="demo-a",
            title="Persist authentication session",
            description="Store login tokens between restarts",
            acceptance_criteria="Users remain signed in after relaunch",
            status="open",
            parent_id="demo-parent",
        ),
        IssueRecord(
            id="demo-b",
            title="Remember authentication session",
            description="Keep login tokens between restarts",
            acceptance_criteria="Users remain signed in after relaunch",
            status="open",
            parent_id="demo-parent",
        ),
    )

    class ScoreIndex:
        def score(self, _left_id, _right_id):
            return 0.75

    result = cli._candidate_evidence(
        list(issues),
        issues,
        {},
        echo_threshold=0.8,
        overlap_threshold=0.8,
        similarity_index=ScoreIndex(),
        exception_margin=0.1,
        reciprocal_rank=0,
    )

    candidate = result.candidates[0]
    assert candidate["admission_reason"] == "shared-parent-threshold-exception"
    assert candidate["field_evidence"]
    assert "strongest field alignment" in candidate["why_surfaced"]


def test_sweep_batches_only_signal_issues_and_reports_no_signal_and_epics(
    monkeypatch, tmp_path, capsys
) -> None:
    issues = (
        IssueRecord("active-a", "A", status="open", issue_type="feature"),
        IssueRecord("active-b", "B", status="open", issue_type="task"),
        IssueRecord("no-signal", "No signal", status="open", issue_type="feature"),
        IssueRecord("container", "Broad epic", status="open", issue_type="epic"),
        IssueRecord("closed", "Completed", status="closed", issue_type="task"),
    )

    class CandidateAdapter:
        def load(self):
            return WorkspaceSnapshot("workspace-test", "1.0.5", "/tmp/demo/.beads"), issues

    def fake_candidates(population, _issues, _vectors, **_kwargs):
        assert [issue.id for issue in population] == ["active-a", "active-b", "no-signal"]
        return CandidateRanking(
            candidates=(
                {
                    "kind": "possible-overlap",
                    "issue_id": "active-a",
                    "related_issue_id": "active-b",
                    "similarity": 0.9,
                },
                {
                    "kind": "completed-work-echo",
                    "issue_id": "active-a",
                    "related_issue_id": "closed",
                    "similarity": 0.9,
                },
            ),
            qualified=2,
            dropped_by_issue_cap=0,
            dropped_by_run_cap=0,
        )

    monkeypatch.setattr(cli, "BeadsAdapter", CandidateAdapter)
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=32))
    monkeypatch.setattr(cli, "_candidate_evidence", fake_candidates)
    monkeypatch.setattr(
        cli, "_workspace_paths", lambda _identity: (tmp_path / "cache", tmp_path / "state")
    )

    output = tmp_path / "candidate-artifacts"
    assert cli.main(["sweep", "--size", "5", "--output", str(output), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["batches"] == [
        {
            "batch": 1,
            "kind": "connected-component",
            "issue_ids": ["active-a", "active-b"],
            "review_units": [{"issue_ids": ["active-a", "active-b"]}],
        }
    ]
    assert payload["batch_diagnostics"]["max_batch_size"] == 2
    assert payload["batch_diagnostics"]["configured_max_batch_size"] == 5
    assert payload["no_signal"] == {"count": 1, "issue_ids": ["no-signal"]}
    assert payload["excluded"] == {
        "by_reason": {"epic": 1},
        "count": 1,
        "issue_ids": ["container"],
    }
    manifest = json.loads((output / "batch-1.json").read_text())
    assert {issue["id"] for issue in manifest["issues"]} == {"active-a", "active-b"}
    assert {item["related_issue_id"] for item in manifest["neighbor_evidence"]} == {
        "active-b",
        "closed",
    }
