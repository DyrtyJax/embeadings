import json

from embead import cli
from embead.models import IssueRecord, WorkspaceSnapshot
from embead.provider import HashingProvider

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
    assert payload["parameters"]["candidate_policy"]["max_total"] == 250
    assert len(payload["batches"]) == 2
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
    assert sorted(path.name for path in output.glob("batch-*.json")) == [
        "batch-1.json",
        "batch-2.json",
    ]


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
