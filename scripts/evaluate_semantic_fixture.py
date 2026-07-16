#!/usr/bin/env python3
"""Evaluate deterministic whole-record and field-aware retrieval on public fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from embead.analysis import MultiViewSimilarityIndex, SimilarityIndex
from embead.models import IssueRecord, canonical_text, semantic_field_texts
from embead.provider import HashingProvider, Model2VecProvider


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "fixture",
        nargs="?",
        type=Path,
        default=Path("tests/fixtures/semantic-hard-negatives-v2.json"),
    )
    parser.add_argument("--provider", choices=("hashing", "model2vec"), default="hashing")
    return parser


def _load(path: Path) -> tuple[list[IssueRecord], list[dict[str, Any]], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues = [IssueRecord(**item) for item in payload["issues"]]
    judgments = list(payload["judgments"])
    identifiers = {issue.id for issue in issues}
    if len(identifiers) != len(issues):
        raise ValueError("fixture issue IDs must be unique")
    for judgment in judgments:
        if judgment["left"] not in identifiers or judgment["right"] not in identifiers:
            raise ValueError("judgment endpoint is missing from the fixture")
        if judgment["rating"] not in {0, 1, 2}:
            raise ValueError("judgment rating must be 0, 1, or 2")
    return issues, judgments, int(payload["fixture_version"])


def _indexes(
    issues: list[IssueRecord], provider: HashingProvider | Model2VecProvider
) -> tuple[SimilarityIndex, MultiViewSimilarityIndex]:
    whole_vectors = provider.encode([canonical_text(issue) for issue in issues])
    whole = SimilarityIndex(dict(zip((issue.id for issue in issues), whole_vectors, strict=True)))
    field_vectors: dict[str, dict[str, list[float]]] = {}
    for field in ("title", "description", "acceptance_criteria", "design"):
        entries = [
            (issue.id, text) for issue in issues if (text := semantic_field_texts(issue).get(field))
        ]
        if entries:
            field_vectors[field] = dict(
                zip(
                    (identifier for identifier, _text in entries),
                    provider.encode([text for _identifier, text in entries]),
                    strict=True,
                )
            )
    return whole, MultiViewSimilarityIndex(whole, field_vectors)


def evaluate(path: Path, provider_name: str) -> dict[str, Any]:
    issues, judgments, fixture_version = _load(path)
    provider = HashingProvider() if provider_name == "hashing" else Model2VecProvider()
    whole, fields = _indexes(issues, provider)
    pair_results = []
    scores_by_rating: dict[int, list[float]] = {0: [], 1: [], 2: []}
    for judgment in judgments:
        left = str(judgment["left"])
        right = str(judgment["right"])
        whole_score = whole.score(left, right)
        field_score = fields.score(left, right)
        scores_by_rating[int(judgment["rating"])].append(field_score)
        pair_results.append(
            {
                **judgment,
                "whole_record_score": round(whole_score, 6),
                "field_aware_score": round(field_score, 6),
                "selected_channel": fields.channel_scores(left, right)[0][0],
            }
        )
    summary = {
        "fixture_version": fixture_version,
        "provider": {
            "model_id": provider.model_id,
            "model_revision": provider.model_revision,
        },
        "issue_count": len(issues),
        "judgment_count": len(judgments),
        "rating_counts": {
            str(rating): len(scores) for rating, scores in sorted(scores_by_rating.items())
        },
        "mean_field_score_by_rating": {
            str(rating): round(sum(scores) / len(scores), 6) if scores else None
            for rating, scores in sorted(scores_by_rating.items())
        },
        "pairs": sorted(pair_results, key=lambda item: (item["left"], item["right"])),
    }
    encoded = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    summary["fingerprint"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return summary


def main() -> int:
    args = _parser().parse_args()
    print(json.dumps(evaluate(args.fixture, args.provider), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
