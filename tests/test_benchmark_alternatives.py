import importlib.util
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).parents[1] / "benchmarks" / "benchmark_alternatives.py"
SPEC = importlib.util.spec_from_file_location("benchmark_alternatives", MODULE_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_quality_rewards_expected_semantic_pairs() -> None:
    vectors = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0], [0.01, 0.99]]
    result = benchmark._quality(vectors)
    assert result["pair_recall_at_1"] == 1.0
    assert result["median_pair_margin"] > 0


def test_file_cache_storage_benchmark_round_trips(tmp_path) -> None:
    vectors = [
        list(vector)
        for vector in np.asarray(
            benchmark._storage_vectors(8, 16),
            dtype=float,
        )
    ]
    result = benchmark._file_cache(tmp_path / "cache", vectors)
    assert result["backend"] == "json-files"
    assert result["records_recovered"] == 8
    assert result["disk_bytes"] > 0
