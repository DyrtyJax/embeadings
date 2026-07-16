from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest


def _namespace() -> dict[str, object]:
    return runpy.run_path(Path(__file__).parents[1] / "scripts" / "prepare_ranked_evaluation.py")


def _report() -> dict[str, object]:
    lanes = ("echo", "overlap")
    return {
        "report_type": "sweep",
        "analysis_fingerprint": "a" * 64,
        "candidates": [
            {
                "candidate_id": f"candidate-{index}",
                "kind": "completed-work-echo" if lane == "echo" else "possible-overlap",
                "lane": lane,
                "issue_id": f"active-{index}",
                "related_issue_id": f"related-{index}",
                "similarity": round(1 - index / 100, 3),
            }
            for index in range(1, 11)
            for lane in (lanes[index % 2],)
        ],
    }


def test_fixed_pool_and_stratified_blind_sample_are_deterministic() -> None:
    namespace = _namespace()
    kwargs = {
        "input_sha256": "b" * 64,
        "pool_size": 8,
        "boundaries": (2, 4, 8),
        "sample_per_stratum": 1,
        "seed": "public-test-seed",
    }

    first_manifest, first_review = namespace["prepare"](_report(), **kwargs)
    second_manifest, second_review = namespace["prepare"](_report(), **kwargs)

    assert first_manifest == second_manifest
    assert first_review == second_review
    assert first_manifest["fixed_pool"]["actual_size"] == 8
    assert {item["candidate_id"] for item in first_manifest["sample"]} <= {
        f"candidate-{index}" for index in range(1, 9)
    }
    assert all(receipt["sampled"] == 1 for receipt in first_manifest["sampling"]["strata"])
    assert len(first_manifest["sample"]) == 6
    assert {item["rank_bucket"] for item in first_manifest["sample"]} == {
        "1-2",
        "3-4",
        "5-8",
    }

    allowed_review_fields = {"review_id", "issue_id", "related_issue_id", "rating", "notes"}
    assert all(set(item) == allowed_review_fields for item in first_review["review_items"])
    assert all(
        item["rating"] is None and item["notes"] == "" for item in first_review["review_items"]
    )
    assert len(first_review["review_fingerprint"]) == 64


def test_report_digest_and_output_location_do_not_change_payload(tmp_path) -> None:
    namespace = _namespace()
    report_path = tmp_path / "source.json"
    rendered = json.dumps(_report(), sort_keys=True)
    report_path.write_text(rendered, encoding="utf-8")
    report, digest = namespace["_load_report"](report_path)
    boundaries = namespace["_parse_boundaries"]("2,4,8", pool_size=8)
    manifest, review = namespace["prepare"](
        report,
        input_sha256=digest,
        pool_size=8,
        boundaries=boundaries,
        sample_per_stratum=1,
        seed="seed",
    )

    first = tmp_path / "first"
    second = tmp_path / "second"
    namespace["_write_output"](first, manifest, review)
    namespace["_write_output"](second, manifest, review)

    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    assert (first / "review.json").read_bytes() == (second / "review.json").read_bytes()
    assert manifest["source"]["input_sha256"] == digest


def test_rank_configuration_and_duplicate_candidates_are_rejected() -> None:
    namespace = _namespace()
    with pytest.raises(ValueError, match="strictly increasing"):
        namespace["_parse_boundaries"]("20,20,250", pool_size=250)
    with pytest.raises(ValueError, match="cover"):
        namespace["_parse_boundaries"]("20,50", pool_size=100)

    report = _report()
    report["candidates"][1]["candidate_id"] = report["candidates"][0]["candidate_id"]
    with pytest.raises(ValueError, match="duplicate candidate ID"):
        namespace["prepare"](
            report,
            input_sha256="b" * 64,
            pool_size=8,
            boundaries=(2, 4, 8),
            sample_per_stratum=1,
            seed="seed",
        )


def test_cli_stdout_does_not_reveal_blinded_manifest(tmp_path) -> None:
    root = Path(__file__).parents[1]
    report_path = tmp_path / "source.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    output = tmp_path / "ranked-review"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/prepare_ranked_evaluation.py",
            str(report_path),
            "--output-dir",
            str(output),
            "--pool-size",
            "8",
            "--rank-boundaries",
            "2,4,8",
            "--sample-per-stratum",
            "1",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    stdout = json.loads(completed.stdout)
    assert stdout["review_path"] == str(output / "review.json")
    assert stdout["manifest_path"] == str(output / "manifest.json")
    assert stdout["sample_size"] == 6
    assert "sample" not in stdout
    assert "strata" not in stdout
    assert "lane" not in completed.stdout
    assert "similarity" not in completed.stdout
