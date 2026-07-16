#!/usr/bin/env python3
"""Build a deterministic, blinded review sample from one fixed candidate pool.

This is an evaluation harness, not a product command. The source sweep is responsible for
qualification and ranking; this script preserves its candidate order, takes one exact prefix, and
samples within lane/rank strata without rerunning selection at several different budgets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

HARNESS_VERSION = 1
DEFAULT_BOUNDARIES = (20, 50, 100, 250)
DEFAULT_SEED = "embead-ranked-evaluation-v1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create an external audit manifest and blinded, deterministic review sheet from "
            "one expanded emBEADings report."
        )
    )
    parser.add_argument("report", type=Path, help="Expanded sweep report.json or triage.json")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--pool-size", type=int, default=250)
    parser.add_argument(
        "--rank-boundaries",
        default=",".join(str(value) for value in DEFAULT_BOUNDARIES),
        help="Inclusive, increasing rank boundaries (default: 20,50,100,250)",
    )
    parser.add_argument(
        "--sample-per-stratum",
        type=int,
        default=10,
        help="Maximum review pairs selected from each lane/rank stratum",
    )
    parser.add_argument(
        "--seed",
        default=DEFAULT_SEED,
        help="Public deterministic sampling seed; not a source of randomness",
    )
    return parser


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_boundaries(raw: str, *, pool_size: int) -> tuple[int, ...]:
    try:
        values = tuple(int(value.strip()) for value in raw.split(",") if value.strip())
    except ValueError as exc:
        raise ValueError("--rank-boundaries must contain integers") from exc
    if not values or any(value < 1 for value in values):
        raise ValueError("--rank-boundaries must contain positive integers")
    if any(right <= left for left, right in zip(values, values[1:], strict=False)):
        raise ValueError("--rank-boundaries must be strictly increasing")
    if values[-1] < pool_size:
        raise ValueError("the final rank boundary must cover --pool-size")
    return values


def _candidate_id(candidate: dict[str, Any]) -> str:
    # Compact packets expose a pair-level candidate_id. Full sweep reports use `id` for the
    # primary issue, so treating that field as pair identity incorrectly rejects valid siblings.
    explicit = candidate.get("candidate_id")
    if explicit:
        return str(explicit)
    required = ("kind", "issue_id", "related_issue_id")
    if any(not candidate.get(field) for field in required):
        raise ValueError("every candidate needs an ID or kind and two issue endpoints")
    return "|".join(str(candidate[field]) for field in required)


def _lane(candidate: dict[str, Any]) -> str:
    lane = candidate.get("lane")
    if lane:
        return str(lane)
    kind = str(candidate.get("kind") or "")
    if kind == "completed-work-echo":
        return "echo"
    if kind == "possible-overlap":
        return "overlap"
    return "dependency"


def _rank_bucket(rank: int, boundaries: tuple[int, ...]) -> str:
    lower = 1
    for upper in boundaries:
        if rank <= upper:
            return f"{lower}-{upper}"
        lower = upper + 1
    raise AssertionError("rank boundaries did not cover the fixed pool")


def _sample_key(seed: str, purpose: str, candidate_id: str) -> str:
    return hashlib.sha256(f"{seed}\0{purpose}\0{candidate_id}".encode()).hexdigest()


def _load_report(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON report: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise ValueError("report must be a JSON object with a candidates array")
    if payload.get("report_type") not in {"sweep", "triage"}:
        raise ValueError("report_type must be sweep or triage")
    return payload, hashlib.sha256(raw).hexdigest()


def prepare(
    report: dict[str, Any],
    *,
    input_sha256: str,
    pool_size: int,
    boundaries: tuple[int, ...],
    sample_per_stratum: int,
    seed: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if pool_size < 1:
        raise ValueError("--pool-size must be positive")
    if sample_per_stratum < 1:
        raise ValueError("--sample-per-stratum must be positive")
    if not seed:
        raise ValueError("--seed must not be empty")

    source_candidates = report["candidates"]
    pool = source_candidates[:pool_size]
    ranked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, candidate in enumerate(pool, start=1):
        if not isinstance(candidate, dict):
            raise ValueError("every candidate must be an object")
        identifier = _candidate_id(candidate)
        if identifier in seen:
            raise ValueError(f"duplicate candidate ID in fixed pool: {identifier}")
        seen.add(identifier)
        ranked.append(
            {
                "candidate_id": identifier,
                "issue_id": str(candidate.get("issue_id") or ""),
                "related_issue_id": str(candidate.get("related_issue_id") or ""),
                "kind": str(candidate.get("kind") or "unknown"),
                "lane": _lane(candidate),
                "similarity": candidate.get("similarity"),
                "source_rank": rank,
                "rank_bucket": _rank_bucket(rank, boundaries),
            }
        )
    if any(not item["issue_id"] or not item["related_issue_id"] for item in ranked):
        raise ValueError("every candidate must include issue_id and related_issue_id")

    strata: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in ranked:
        strata[(item["lane"], item["rank_bucket"])].append(item)

    selected: list[dict[str, Any]] = []
    stratum_receipts: list[dict[str, Any]] = []
    bucket_order = {
        _rank_bucket(rank, boundaries): index
        for index, rank in enumerate((1, *(value + 1 for value in boundaries[:-1])))
    }
    for lane, bucket in sorted(strata, key=lambda key: (bucket_order[key[1]], key[0])):
        available = strata[(lane, bucket)]
        chosen = sorted(
            available,
            key=lambda item: _sample_key(seed, "stratum", item["candidate_id"]),
        )[:sample_per_stratum]
        selected.extend(chosen)
        stratum_receipts.append(
            {
                "lane": lane,
                "rank_bucket": bucket,
                "available": len(available),
                "sampled": len(chosen),
            }
        )

    review_order = sorted(
        selected,
        key=lambda item: _sample_key(seed, "blind-review-order", item["candidate_id"]),
    )
    review_id_by_candidate = {
        item["candidate_id"]: f"review-{index:03d}"
        for index, item in enumerate(review_order, start=1)
    }
    review = {
        "harness_version": HARNESS_VERSION,
        "notice": (
            "Blinded rating sheet. Resolve both issue IDs and rate the relationship before "
            "opening manifest.json, which contains source rank, lane, and similarity."
        ),
        "source_analysis_fingerprint": report.get("analysis_fingerprint"),
        "review_items": [
            {
                "review_id": review_id_by_candidate[item["candidate_id"]],
                "issue_id": item["issue_id"],
                "related_issue_id": item["related_issue_id"],
                "rating": None,
                "notes": "",
            }
            for item in review_order
        ],
    }
    review["review_fingerprint"] = _digest(review)

    manifest_sample = [
        {**item, "review_id": review_id_by_candidate[item["candidate_id"]]}
        for item in sorted(selected, key=lambda item: item["source_rank"])
    ]
    manifest = {
        "harness_version": HARNESS_VERSION,
        "source": {
            "report_type": report.get("report_type"),
            "analysis_fingerprint": report.get("analysis_fingerprint"),
            "input_sha256": input_sha256,
            "available_candidates": len(source_candidates),
        },
        "fixed_pool": {
            "requested_size": pool_size,
            "actual_size": len(ranked),
            "selection": "exact-prefix-of-source-candidate-order",
            "fingerprint": _digest(ranked),
        },
        "sampling": {
            "method": "stable-sha256-within-lane-and-rank-bucket",
            "seed": seed,
            "rank_boundaries": list(boundaries),
            "sample_per_stratum": sample_per_stratum,
            "sample_size": len(selected),
            "strata": stratum_receipts,
            "review_fingerprint": review["review_fingerprint"],
        },
        "sample": manifest_sample,
    }
    manifest["manifest_fingerprint"] = _digest(manifest)
    return manifest, review


def _write_output(output_dir: Path, manifest: dict[str, Any], review: dict[str, Any]) -> None:
    root = Path(__file__).resolve().parents[1]
    destination = output_dir.expanduser().resolve()
    if destination == root or root in destination.parents:
        raise ValueError("evaluation output must be outside the emBEADings repository")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (destination / "review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = _parser().parse_args()
    if args.pool_size < 1:
        raise ValueError("--pool-size must be positive")
    boundaries = _parse_boundaries(args.rank_boundaries, pool_size=args.pool_size)
    report, input_sha256 = _load_report(args.report)
    manifest, review = prepare(
        report,
        input_sha256=input_sha256,
        pool_size=args.pool_size,
        boundaries=boundaries,
        sample_per_stratum=args.sample_per_stratum,
        seed=args.seed,
    )
    _write_output(args.output_dir, manifest, review)
    destination = args.output_dir.expanduser().resolve()
    print(
        json.dumps(
            {
                "harness_version": HARNESS_VERSION,
                "manifest_path": str(destination / "manifest.json"),
                "next_step": "Rate review.json before opening manifest.json.",
                "review_fingerprint": review["review_fingerprint"],
                "review_path": str(destination / "review.json"),
                "sample_size": len(review["review_items"]),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
