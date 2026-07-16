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
    assert payload["fixture_version"] == 1
    assert payload["rating_counts"] == {"0": 3, "1": 1, "2": 2}
    assert len(payload["fingerprint"]) == 64
    assert {pair["reason"] for pair in payload["pairs"]} >= {
        "same-token-different-intent",
        "shared-subsystem-different-outcome",
        "reference-versus-edit-intent",
        "completed-invariant",
    }
    assert all("selected_channel" in pair for pair in payload["pairs"])
