from __future__ import annotations

import json
from dataclasses import dataclass

from embead.reports import (
    build_batch_manifest,
    build_neighbors_payload,
    build_sweep_payload,
    render_batch_markdown,
    render_neighbors_markdown,
    render_sweep_markdown,
)

SNAPSHOT = {"workspace_id": "workspace-1", "beads_version": "1.2.3"}
MODEL = {"id": "local-model", "revision": "abc123"}
CACHE = {"hits": 8, "misses": 2}


@dataclass
class Issue:
    id: str
    title: str
    status: str


def test_neighbors_payload_is_json_serializable_and_deterministic() -> None:
    issue = Issue("bd-1", "Canonical issue", "open")
    neighbors = [
        {"id": "bd-3", "title": "Lower", "status": "closed", "similarity": 0.7},
        {"id": "bd-2", "title": "Higher", "status": "open", "similarity": 0.9},
    ]

    payload = build_neighbors_payload(issue, neighbors, snapshot=SNAPSHOT, model=MODEL, cache=CACHE)

    json.dumps(payload)
    assert payload["schema_version"] == 1
    assert payload["policy"]["read_only"] is True
    assert [neighbor["id"] for neighbor in payload["neighbors"]] == ["bd-2", "bd-3"]
    assert payload["snapshot"] == SNAPSHOT
    assert payload["model"] == MODEL
    assert payload["cache"] == CACHE


def test_neighbors_markdown_is_advisory_and_compact() -> None:
    payload = build_neighbors_payload(
        Issue("bd-1", "Canonical issue", "open"),
        [
            {
                "id": "bd-2",
                "title": "Related | issue",
                "status": "closed",
                "similarity": 0.87654,
                "relationship": "same parent",
            }
        ],
        snapshot=SNAPSHOT,
        model=MODEL,
        cache=CACHE,
    )

    markdown = render_neighbors_markdown(payload)

    assert "Read-only report" in markdown
    assert "scores are advisory" in markdown.lower()
    assert "Verify" in markdown
    assert "0.88" in markdown
    assert "Related \\| issue" in markdown
    assert "matrix" not in markdown.lower()


def test_batch_manifest_sorts_issues_and_evidence() -> None:
    manifest = build_batch_manifest(
        "run-1",
        2,
        [Issue("bd-9", "Nine", "open"), Issue("bd-1", "One", "closed")],
        [
            {"source_id": "bd-9", "target_id": "bd-8", "score": 0.4},
            {"source_id": "bd-1", "target_id": "bd-2", "score": 0.8},
        ],
        ["Verify against source control", "Record counterevidence"],
        snapshot=SNAPSHOT,
        model=MODEL,
        cache=CACHE,
    )

    json.dumps(manifest)
    assert [issue["id"] for issue in manifest["issues"]] == ["bd-1", "bd-9"]
    assert manifest["neighbor_evidence"][0]["source_id"] == "bd-1"
    assert manifest["policy"]["implementation_allowed"] is False
    assert manifest["policy"]["tracker_mutation_allowed"] is False


def test_batch_markdown_uses_safe_candidate_language() -> None:
    manifest = build_batch_manifest(
        "run-1",
        1,
        [Issue("bd-1", "Active work", "open")],
        [
            {
                "issue_id": "bd-1",
                "related_issue_id": "bd-2",
                "kind": "completed_work_echo",
                "similarity": 0.91,
                "structural_context": "same parent",
            },
            {
                "issue_id": "bd-3",
                "related_issue_id": "bd-4",
                "kind": "possible_overlap",
                "similarity": 0.88,
            },
        ],
        ["Verify against current project state"],
        snapshot=SNAPSHOT,
        model=MODEL,
        cache=CACHE,
    )

    markdown = render_batch_markdown(manifest)

    assert "Completed-work echo" in markdown
    assert "Possible overlap" in markdown
    assert "What to verify" in markdown
    assert "Do not implement changes or mutate the tracker" in markdown


def test_sweep_payload_and_markdown_include_metadata_and_ordering() -> None:
    candidates = [
        {
            "issue_id": "bd-5",
            "related_issue_id": "bd-6",
            "kind": "possible_overlap",
            "similarity": 0.82,
            "admission_reason": "dependency-threshold-exception",
            "dependency_evidence": {
                "source_id": "bd-5",
                "target_id": "bd-6",
                "type": "blocks",
            },
        },
        {
            "issue_id": "bd-2",
            "related_issue_id": "bd-3",
            "kind": "completed_work_echo",
            "similarity": 0.93,
            "counterevidence": "explicit later-phase note",
        },
    ]
    payload = build_sweep_payload(
        "run-7",
        candidates,
        [{"batch": 2, "issue_ids": ["bd-5"]}, {"batch": 1, "issue_ids": ["bd-2"]}],
        snapshot=SNAPSHOT,
        model=MODEL,
        cache=CACHE,
        filters={"status": ["open"]},
        thresholds={"echo": 0.9},
        candidate_policy={
            "max_total": 250,
            "baseline_protected": 1,
            "lanes": {
                "dependency": {"qualified": 2, "admitted": 1, "dropped_by_lane_cap": 1},
                "echo": {"qualified": 1, "admitted": 1, "dropped_by_lane_cap": 0},
                "overlap": {"qualified": 1, "admitted": 1, "dropped_by_lane_cap": 0},
            },
        },
        no_signal={"count": 4, "issue_ids": ["bd-7", "bd-8", "bd-9", "bd-10"]},
        excluded={"count": 1, "by_reason": {"epic": 1}, "issue_ids": ["bd-1"]},
        target_batch_size=9,
        warnings=["z warning", "a warning"],
        duration_ms=42,
    )

    json.dumps(payload)
    assert [batch["batch"] for batch in payload["batches"]] == [1, 2]
    assert payload["warnings"] == ["a warning", "z warning"]
    assert payload["parameters"]["target_batch_size"] == 9
    assert payload["parameters"]["candidate_policy"]["max_total"] == 250
    assert payload["no_signal"]["count"] == 4
    assert payload["excluded"]["by_reason"] == {"epic": 1}

    markdown = render_sweep_markdown(payload)
    assert "Completed-work echoes: 1" in markdown
    assert "Possible overlaps: 1" in markdown
    assert "No-signal records: 4" in markdown
    assert "Excluded records: 1" in markdown
    assert "Dependency: 1 admitted / 2 qualified" in markdown
    assert "Baseline candidates protected in sensitivity mode: 1" in markdown
    assert "Batch 1: 1 issues" in markdown
    assert "local-model" in markdown
    assert "8 hits, 2 misses" in markdown
    assert "verify" in markdown.lower()
    assert "dependency-threshold-exception" in markdown
    assert "Typed dependency: bd-5 → bd-6 (blocks)" in markdown


def test_empty_sweep_is_a_successful_report() -> None:
    payload = build_sweep_payload(
        "run-empty",
        [],
        [],
        snapshot=SNAPSHOT,
        model=MODEL,
        cache={"hits": 3, "misses": 0},
    )

    markdown = render_sweep_markdown(payload)
    assert "No review candidates were found" in markdown
    assert payload["candidates"] == []
