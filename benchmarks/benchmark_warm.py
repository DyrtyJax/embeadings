#!/usr/bin/env python3
"""Benchmark the warm analysis path with a generated, public synthetic corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from typing import Any

from embead.analysis import SimilarityIndex, balanced_batches
from embead.cli import _candidate_evidence
from embead.models import IssueRecord, canonical_text
from embead.provider import HashingProvider


def _milliseconds(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _synthetic_issues(count: int) -> tuple[IssueRecord, ...]:
    records = []
    closed_start = count * 3 // 4
    for number in range(count):
        area = number % 40
        component = number % 80
        outcome = number % 211
        records.append(
            IssueRecord(
                id=f"synthetic-{number:04d}",
                title=f"Implement outcome {outcome} for component {component}",
                description=(
                    f"Public synthetic record in area {area}. Validate workflow {number % 97} "
                    f"and document lifecycle behavior {number % 29}."
                ),
                status="closed" if number >= closed_start else "open",
            )
        )
    return tuple(records)


def _median(samples: list[dict[str, float]], key: str) -> float:
    return round(statistics.median(sample[key] for sample in samples), 3)


def run(count: int, dimension: int, repeats: int) -> dict[str, Any]:
    started = time.perf_counter()
    issues = _synthetic_issues(count)
    acquisition_ms = _milliseconds(started)

    provider = HashingProvider(dimension=dimension)
    started = time.perf_counter()
    encoded = provider.encode([canonical_text(issue) for issue in issues])
    vectors = dict(zip((issue.id for issue in issues), encoded, strict=True))
    embedding_ms = _milliseconds(started)
    population = [issue for issue in issues if issue.status == "open"]

    samples: list[dict[str, float]] = []
    candidate_counts: list[int] = []
    batch_counts: list[int] = []
    output_fingerprints: list[str] = []
    for _ in range(repeats):
        started = time.perf_counter()
        index = SimilarityIndex(vectors)
        scoring_ms = _milliseconds(started)

        started = time.perf_counter()
        ranking = _candidate_evidence(
            population,
            issues,
            vectors,
            echo_threshold=0.72,
            overlap_threshold=0.82,
            similarity_index=index,
        )
        candidate_analysis_ms = _milliseconds(started)

        started = time.perf_counter()
        batches = balanced_batches(
            population,
            vectors,
            target_size=9,
            similarity_index=index,
        )
        batching_ms = _milliseconds(started)
        samples.append(
            {
                "similarity_scoring": scoring_ms,
                "candidate_analysis": candidate_analysis_ms,
                "batching": batching_ms,
                "analysis_total": scoring_ms + candidate_analysis_ms + batching_ms,
            }
        )
        candidate_counts.append(len(ranking.candidates))
        batch_counts.append(len(batches))
        stable_output = {
            "candidates": ranking.candidates,
            "batches": [[issue.id for issue in batch] for batch in batches],
        }
        output_fingerprints.append(
            hashlib.sha256(
                json.dumps(stable_output, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )

    timing_keys = ("similarity_scoring", "candidate_analysis", "batching", "analysis_total")
    return {
        "benchmark": "embeadings-public-synthetic-warm-analysis-v1",
        "records": count,
        "active_records": len(population),
        "closed_records": count - len(population),
        "vector_dimension": dimension,
        "repeats": repeats,
        "environment": {
            "python": platform.python_version(),
            "numpy": __import__("numpy").__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or "unknown",
        },
        "fixture_prep_ms": {
            "synthetic_acquisition": round(acquisition_ms, 3),
            "synthetic_embedding": round(embedding_ms, 3),
        },
        "median_timings_ms": {key: _median(samples, key) for key in timing_keys},
        "candidate_count": candidate_counts[-1],
        "batch_count": batch_counts[-1],
        "deterministic_output": len(set(output_fingerprints)) == 1,
        "target_ms": 5000,
        "target_met": _median(samples, "analysis_total") < 5000,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=1000)
    parser.add_argument("--dimension", type=int, default=256)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.records < 2 or args.dimension < 2 or args.repeats < 1:
        parser.error("records and dimension must be at least 2; repeats must be positive")
    print(json.dumps(run(args.records, args.dimension, args.repeats), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
