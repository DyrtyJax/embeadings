import json
import subprocess
import sys
from pathlib import Path


def test_warm_benchmark_reports_exact_incremental_scope_and_fingerprint() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "benchmarks/benchmark_warm.py",
            "--records",
            "80",
            "--repeats",
            "2",
            "--eligible-active",
            "7",
        ],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["records"] == 80
    assert payload["active_records"] == 60
    assert payload["eligible_active_records"] == 7
    assert payload["deterministic_output"] is True
    assert len(payload["output_fingerprint"]) == 64
    assert payload["median_timings_ms"]["candidate_analysis"] >= 0
