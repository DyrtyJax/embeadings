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
    assert payload["fixture_version"] == 2
    assert payload["rating_counts"] == {"0": 6, "1": 2, "2": 2}
    assert len(payload["fingerprint"]) == 64
    assert {pair["reason"] for pair in payload["pairs"]} >= {
        "same-token-different-intent",
        "shared-subsystem-different-outcome",
        "reference-versus-edit-intent",
        "completed-invariant",
        "direct-parent-child-known-structure",
        "repeated-closed-target-hub",
    }
    assert all("selected_channel" in pair for pair in payload["pairs"])


def test_fixture_carries_hierarchy_and_repeated_target_regressions() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "tests/fixtures/semantic-hard-negatives-v2.json").read_text(encoding="utf-8")
    )
    issues = {issue["id"]: issue for issue in payload["issues"]}

    assert issues["syn-impact-metrics"]["parent_id"] == "syn-impact-program"
    hub_pairs = [
        judgment
        for judgment in payload["judgments"]
        if judgment["reason"] == "repeated-closed-target-hub"
    ]
    assert len(hub_pairs) == 2
    assert {pair["right"] for pair in hub_pairs} == {"syn-rollout-closed"}
