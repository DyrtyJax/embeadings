import json
import subprocess
import sys
from pathlib import Path


def test_public_hard_negative_fixture_is_deterministic_and_reason_coded() -> None:
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "scripts/evaluate_semantic_fixture.py"]

    first = subprocess.run(command, cwd=root, check=True, text=True, capture_output=True)
    second = subprocess.run(command, cwd=root, check=True, text=True, capture_output=True)

    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["fixture_version"] == 3
    assert payload["rating_counts"] == {"0": 10, "1": 2, "2": 12}
    assert payload["seed_audit"] == {
        "exact_title_pairs_reviewed": 3,
        "hard_negative_pairs_reviewed": 10,
        "source": "sanitized Ruff evaluator patterns",
        "status": "manually-audited-before-inclusion",
        "strong_reference_pairs_reviewed": 11,
    }
    assert len(payload["fingerprint"]) == 64
    assert {pair["reason"] for pair in payload["pairs"]} >= {
        "generic-token-different-intent",
        "shared-subsystem-different-outcome",
        "explicit-follow-up-repaired-invariant",
        "exact-normalized-title",
        "generic-token-disjoint-rule-code",
    }
    assert all(
        {"selected_channel", "exact_identifier_score", "sparse_tfidf_score"} <= pair.keys()
        for pair in payload["pairs"]
    )
    assert set(payload["retrieval_metrics"]) == {
        "exact_identifier",
        "provider_field_aware",
        "provider_whole_record",
        "sparse_tfidf",
    }


def test_fixture_carries_sanitized_audited_reference_and_title_seeds() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "tests/fixtures/semantic-gold-v3.json").read_text(encoding="utf-8")
    )
    judgments = payload["judgments"]

    assert sum(item["seed"] == "strong-reference" for item in judgments) == 11
    assert sum(item["seed"] == "exact-title" for item in judgments) == 3
    assert sum(item["seed"] == "hard-negative" for item in judgments) == 10
    assert {item["audit_status"] for item in judgments} == {"manually-audited"}
    assert "ruff-gh-" not in json.dumps(payload).lower()
