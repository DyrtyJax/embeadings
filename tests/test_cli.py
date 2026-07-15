import json

from embead import cli
from embead.models import IssueRecord, WorkspaceSnapshot
from embead.provider import HashingProvider
from embead.ranking import CandidateRanking, LaneMetrics

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


def test_readiness_is_corpus_free_and_machine_readable(monkeypatch, capsys) -> None:
    class FailingAdapter:
        def load(self):
            raise AssertionError("readiness must not load Beads records")

    monkeypatch.setattr(cli, "BeadsAdapter", FailingAdapter)
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=32))

    assert cli.main(["readiness", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "corpus_loaded": False,
        "model_id": "hashing/32",
        "model_revision": "1",
        "network_policy": "prefetch-allowed",
        "readiness_version": 1,
        "status": "ready",
        "vector_dimension": 32,
    }


def test_readiness_offline_sets_huggingface_policy(monkeypatch, capsys) -> None:
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=8))

    assert cli.main(["readiness", "--offline", "--json"]) == 0

    assert cli.os.environ["HF_HUB_OFFLINE"] == "1"
    assert json.loads(capsys.readouterr().out)["network_policy"] == "offline"


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
        "code_surface_analysis",
    }
    assert all(value >= 0 for value in payload["timings_ms"].values())
    assert (output / "report.json").is_file()
    assert (output / "report.md").is_file()
    assert list(output.glob("batch-*.json")) == []


def test_collisions_is_corpus_read_only_and_does_not_load_embedding_provider(
    monkeypatch, tmp_path, capsys
) -> None:
    _configure(monkeypatch, tmp_path)

    def no_provider(_name):
        raise AssertionError("collision analysis must not load an embedding provider")

    analysis = {
        "repository_available": True,
        "repository_revision": "revision",
        "base_reference": "origin/main",
        "base_revision": "base-revision",
        "issue_count": 2,
        "pointer_count": 2,
        "issues_with_explicit_surfaces": 0,
        "issues_with_observed_surfaces": 2,
        "issues_without_surfaces": 0,
        "worktrees_discovered": 3,
        "worktrees_associated": 2,
        "source_counts": {"active-worktree-diff": 2},
        "hub_surface_limit": 5,
        "hub_surfaces": [],
        "pairs_omitted_by_hub_guard": 0,
        "surfaces": [],
        "collisions": [
            {
                "issue_id": "demo-1",
                "related_issue_id": "demo-3",
                "kind": "exact-file",
                "confidence": "observed",
                "shared_paths": ["src/cache/index.py"],
                "shared_symbols": [],
                "shared_modules": ["src/cache"],
                "evidence_sources": ["active-worktree-diff"],
                "revision_relation": "same",
                "what_to_verify": "Coordinate the shared file.",
            }
        ],
        "warnings": [],
    }
    monkeypatch.setattr(cli, "_provider", no_provider)
    monkeypatch.setattr(cli, "_surface_analysis", lambda *_args: analysis)

    output = tmp_path / "collisions.json"
    assert cli.main(["collisions", "--output", str(output), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["report_type"] == "collisions"
    assert payload["policy"]["snippets_included"] is False
    assert payload["code_surface_analysis"]["collisions"][0]["kind"] == "exact-file"
    assert json.loads(output.read_text()) == payload


def test_sweep_can_include_code_surface_analysis(monkeypatch, tmp_path, capsys) -> None:
    _configure(monkeypatch, tmp_path)
    analysis = {
        "repository_available": False,
        "repository_revision": None,
        "base_reference": None,
        "base_revision": None,
        "issue_count": 2,
        "pointer_count": 0,
        "issues_with_explicit_surfaces": 0,
        "issues_with_observed_surfaces": 0,
        "issues_without_surfaces": 2,
        "worktrees_discovered": 0,
        "worktrees_associated": 0,
        "source_counts": {},
        "hub_surface_limit": 5,
        "hub_surfaces": [],
        "pairs_omitted_by_hub_guard": 0,
        "surfaces": [],
        "collisions": [],
        "warnings": ["No Git repository was available."],
    }
    monkeypatch.setattr(cli, "_surface_analysis", lambda *_args: analysis)

    output = tmp_path / "surface-sweep"
    assert cli.main(["sweep", "--code-surfaces", "--output", str(output), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["code_surface_analysis"] == analysis
    assert payload["timings_ms"]["code_surface_analysis"] >= 0
    assert "Code-surface collision evidence" in (output / "report.md").read_text()


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

    assert cli.main(["sweep", "--weekly-review-budget", "0", "--json"]) == 2

    assert "run candidate cap must be positive" in capsys.readouterr().err


def test_weekly_budget_composes_with_incremental_scope_and_dependency_allowance(
    monkeypatch, tmp_path, capsys
) -> None:
    issues = (
        IssueRecord("changed", "Changed", status="open", updated_at="2026-07-14T01:00:00Z"),
        IssueRecord("context", "Context", status="open", updated_at="2026-07-01T01:00:00Z"),
        IssueRecord("closed", "Closed", status="closed", updated_at="2026-07-01T01:00:00Z"),
    )

    class WeeklyAdapter:
        def load(self):
            return WorkspaceSnapshot("workspace-test", "1.0.5", None), issues

    def fake_candidates(_population, _issues, _vectors, **kwargs):
        assert kwargs["eligible_issue_ids"] == {"changed"}
        assert kwargs["max_candidates"] == 2
        assert kwargs["max_dependency_candidates_per_issue"] == 7
        return CandidateRanking(
            candidates=(
                {
                    "kind": "possible-overlap",
                    "lane": "dependency",
                    "issue_id": "changed",
                    "related_issue_id": "context",
                    "similarity": 0.9,
                },
                {
                    "kind": "completed-work-echo",
                    "lane": "echo",
                    "issue_id": "changed",
                    "related_issue_id": "closed",
                    "similarity": 0.88,
                },
            ),
            qualified=3,
            dropped_by_issue_cap=0,
            dropped_by_run_cap=1,
            lanes={
                "dependency": LaneMetrics(qualified=1, admitted=1),
                "echo": LaneMetrics(qualified=1, admitted=1),
                "overlap": LaneMetrics(qualified=1, dropped_by_run_cap=1),
            },
        )

    monkeypatch.setattr(cli, "BeadsAdapter", WeeklyAdapter)
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=32))
    monkeypatch.setattr(cli, "_candidate_evidence", fake_candidates)
    monkeypatch.setattr(
        cli, "_workspace_paths", lambda _identity: (tmp_path / "cache", tmp_path / "state")
    )

    assert (
        cli.main(
            [
                "sweep",
                "--weekly-review-budget",
                "2",
                "--max-dependency-candidates-per-issue",
                "7",
                "--changed-since",
                "2026-07-10T00:00:00Z",
                "--output",
                str(tmp_path / "weekly"),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert len(payload["candidates"]) == 2
    assert payload["parameters"]["filters"]["incremental_scope"]["mode"] == "changed-since"
    assert payload["parameters"]["candidate_policy"]["max_dependencies_per_issue"] == 7
    assert payload["parameters"]["candidate_policy"]["review_budget"] == {
        "admitted_candidates": 2,
        "candidate_limit": 2,
        "mode": "weekly",
        "omitted_by_lane": {"dependency": 0, "echo": 0, "overlap": 1},
        "omitted_candidates": 1,
        "priority_order": [
            "typed-dependency",
            "high-confidence-completed-work-echo",
            "possible-overlap",
        ],
    }
    markdown = (tmp_path / "weekly" / "report.md").read_text()
    assert "Mode: weekly" in markdown
    assert "Omitted by lane: dependency=0, echo=0, overlap=1" in markdown


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


def test_changed_since_scopes_candidates_reports_unchanged_and_writes_checkpoint(
    monkeypatch, tmp_path, capsys
) -> None:
    issues = (
        IssueRecord("changed", "Changed", status="open", updated_at="2026-07-14T01:00:00Z"),
        IssueRecord("unchanged", "Unchanged", status="open", updated_at="2026-07-01T01:00:00Z"),
    )

    class IncrementalAdapter:
        def load(self):
            return WorkspaceSnapshot("workspace-test", "1.0.5", None), issues

    def fake_candidates(_population, _issues, _vectors, **kwargs):
        assert kwargs["eligible_issue_ids"] == {"changed"}
        return CandidateRanking(
            candidates=(
                {
                    "kind": "possible-overlap",
                    "issue_id": "changed",
                    "related_issue_id": "unchanged",
                    "similarity": 0.9,
                },
            ),
            qualified=1,
            dropped_by_issue_cap=0,
            dropped_by_run_cap=0,
        )

    monkeypatch.setattr(cli, "BeadsAdapter", IncrementalAdapter)
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=32))
    monkeypatch.setattr(cli, "_candidate_evidence", fake_candidates)
    monkeypatch.setattr(
        cli, "_workspace_paths", lambda _identity: (tmp_path / "cache", tmp_path / "state")
    )
    checkpoint = tmp_path / "checkpoint.json"
    assert (
        cli.main(
            [
                "sweep",
                "--changed-since",
                "2026-07-10T00:00:00Z",
                "--write-checkpoint",
                str(checkpoint),
                "--output",
                str(tmp_path / "out"),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["parameters"]["filters"]["incremental_scope"] == {
        "checkpoint_created_at": None,
        "changed_active_count": 1,
        "deleted_since_checkpoint_count": 0,
        "mode": "changed-since",
        "unchanged_active_count": 1,
        "unknown_timestamp_count": 0,
    }
    assert payload["excluded"] == {
        "by_reason": {"unchanged": 1},
        "count": 1,
        "issue_ids": ["unchanged"],
    }
    checkpoint_payload = json.loads(checkpoint.read_text())
    assert set(checkpoint_payload["issues"]) == {"changed", "unchanged"}
    assert "Changed" not in checkpoint.read_text()
    markdown = (tmp_path / "out" / "report.md").read_text()
    assert "Review scope: changed-since" in markdown
    assert "Unchanged active records excluded: 1" in markdown
