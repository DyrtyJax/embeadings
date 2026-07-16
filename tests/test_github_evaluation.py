from __future__ import annotations

import json
import runpy
import subprocess
from pathlib import Path

import pytest


def _namespace() -> dict[str, object]:
    return runpy.run_path(Path(__file__).parents[1] / "scripts" / "prepare_github_evaluation.py")


def test_github_export_is_bounded_deterministic_and_beads_shaped(monkeypatch, tmp_path) -> None:
    namespace = _namespace()
    pages = [
        {
            "data": {
                "repository": {
                    "issues": {
                        "nodes": [
                            {
                                "number": 2,
                                "title": "Later issue",
                                "body": "x" * 20,
                                "state": "OPEN",
                                "url": "https://github.com/acme/demo/issues/2",
                                "createdAt": "2026-01-02T00:00:00Z",
                                "updatedAt": "2026-01-03T00:00:00Z",
                                "closedAt": None,
                                "labels": {"nodes": [{"name": "enhancement"}]},
                            },
                            {
                                "number": 1,
                                "title": "First issue",
                                "body": "failure details",
                                "state": "CLOSED",
                                "url": "https://github.com/acme/demo/issues/1",
                                "createdAt": "2026-01-01T00:00:00Z",
                                "updatedAt": "2026-01-04T00:00:00Z",
                                "closedAt": "2026-01-04T00:00:00Z",
                                "labels": {"nodes": [{"name": "bug"}, {"name": "P1"}]},
                            },
                        ]
                    }
                }
            }
        }
    ]

    def completed(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            ["gh"],
            0,
            stdout=json.dumps(pages),
            stderr="",
        )

    monkeypatch.setattr(namespace["subprocess"], "run", completed)
    issues = namespace["_fetch"]("acme/demo")
    records = namespace["_records"]("acme/demo", issues, body_limit=8)
    summary = namespace["_write_external"](tmp_path / "issues.jsonl", records)

    assert [record["id"] for record in records] == ["demo-gh-1", "demo-gh-2"]
    assert records[0]["issue_type"] == "bug"
    assert records[0]["priority"] == 1
    assert records[1]["issue_type"] == "feature"
    assert records[1]["description"] == "xxxxxxxx"
    assert records[0]["dependencies"] == []
    assert summary["issue_count"] == 2
    assert summary["active_count"] == 1
    assert summary["closed_count"] == 1
    assert len(summary["sha256"]) == 64
    assert len((tmp_path / "issues.jsonl").read_text().splitlines()) == 2


def test_github_export_rejects_invalid_repo_and_in_repository_output(tmp_path) -> None:
    namespace = _namespace()

    with pytest.raises(ValueError, match="OWNER/NAME"):
        namespace["_fetch"]("not-a-repository")
    with pytest.raises(ValueError, match="outside"):
        namespace["_write_external"](
            Path(__file__).parents[1] / "forbidden.jsonl",
            [],
        )
