#!/usr/bin/env python3
"""Evaluate deterministic whole-record and field-aware retrieval on public fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import string
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
        default=Path("tests/fixtures/semantic-gold-v3.json"),
    )
    parser.add_argument("--provider", choices=("hashing", "model2vec"), default="hashing")
    return parser


def _load(path: Path) -> tuple[list[IssueRecord], list[dict[str, Any]], dict[str, Any]]:
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
    return issues, judgments, payload


_TOKEN = re.compile(r"[a-z0-9]+")
_IDENTIFIER = re.compile(r"\b[A-Z]{2,8}-?\d{2,5}\b")
_TITLE_PUNCTUATION = str.maketrans("", "", string.punctuation)


def _tokens(issue: IssueRecord) -> list[str]:
    return _TOKEN.findall(canonical_text(issue).lower())


def _normalized_title(issue: IssueRecord) -> str:
    return " ".join(issue.title.lower().translate(_TITLE_PUNCTUATION).split())


class _ExactIdentifierIndex:
    def __init__(self, issues: list[IssueRecord]) -> None:
        self._issues = {issue.id: issue for issue in issues}
        self._identifiers = {
            issue.id: frozenset(_IDENTIFIER.findall(canonical_text(issue))) for issue in issues
        }

    def score(self, left: str, right: str) -> float:
        if _normalized_title(self._issues[left]) == _normalized_title(self._issues[right]):
            return 1.0
        if self._identifiers[left] & self._identifiers[right]:
            return 0.9
        return 0.0


class _SparseIndex:
    def __init__(self, issues: list[IssueRecord]) -> None:
        documents = {issue.id: _tokens(issue) for issue in issues}
        document_frequency: dict[str, int] = {}
        for tokens in documents.values():
            for token in set(tokens):
                document_frequency[token] = document_frequency.get(token, 0) + 1
        count = len(issues)
        self._vectors: dict[str, dict[str, float]] = {}
        for identifier, tokens in documents.items():
            frequencies: dict[str, int] = {}
            for token in tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
            weighted = {
                token: frequency * (math.log((count + 1) / (document_frequency[token] + 1)) + 1)
                for token, frequency in frequencies.items()
            }
            norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
            self._vectors[identifier] = {token: value / norm for token, value in weighted.items()}

    def score(self, left: str, right: str) -> float:
        left_vector = self._vectors[left]
        right_vector = self._vectors[right]
        if len(left_vector) > len(right_vector):
            left_vector, right_vector = right_vector, left_vector
        return sum(value * right_vector.get(token, 0.0) for token, value in left_vector.items())


def _retrieval_metrics(
    issue_ids: list[str], judgments: list[dict[str, Any]], scorer: Any, *, budget: int
) -> dict[str, Any]:
    positives = [judgment for judgment in judgments if int(judgment["rating"]) == 2]
    recalled = 0
    for judgment in positives:
        left = str(judgment["left"])
        right = str(judgment["right"])
        ranked = sorted(
            (candidate for candidate in issue_ids if candidate != left),
            key=lambda candidate: (-scorer.score(left, candidate), candidate),
        )
        recalled += right in ranked[:5]

    ranked_judgments = sorted(
        judgments,
        key=lambda judgment: (
            -scorer.score(str(judgment["left"]), str(judgment["right"])),
            str(judgment["left"]),
            str(judgment["right"]),
        ),
    )
    admitted = ranked_judgments[:budget]
    above_threshold = [
        judgment
        for judgment in judgments
        if scorer.score(str(judgment["left"]), str(judgment["right"])) >= 0.72
    ]
    return {
        "candidate_recall_at_5": round(recalled / len(positives), 6) if positives else None,
        "fixed_budget": budget,
        "rating_2_precision_at_budget": round(
            sum(int(item["rating"]) == 2 for item in admitted) / len(admitted), 6
        ),
        "useful_precision_at_budget": round(
            sum(int(item["rating"]) >= 1 for item in admitted) / len(admitted), 6
        ),
        "abstention_rate_at_0_72": round(1 - len(above_threshold) / len(judgments), 6),
        "rating_2_recall_at_0_72": round(
            sum(int(item["rating"]) == 2 for item in above_threshold) / len(positives), 6
        )
        if positives
        else None,
    }


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
    issues, judgments, fixture = _load(path)
    provider = HashingProvider() if provider_name == "hashing" else Model2VecProvider()
    whole, fields = _indexes(issues, provider)
    exact_identifier = _ExactIdentifierIndex(issues)
    sparse = _SparseIndex(issues)
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
                "exact_identifier_score": round(exact_identifier.score(left, right), 6),
                "sparse_tfidf_score": round(sparse.score(left, right), 6),
                "selected_channel": fields.channel_scores(left, right)[0][0],
            }
        )
    summary = {
        "fixture_version": int(fixture["fixture_version"]),
        "notice": fixture.get("notice"),
        "seed_audit": fixture.get("seed_audit"),
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
        "retrieval_metrics": {
            "provider_whole_record": _retrieval_metrics(
                [issue.id for issue in issues], judgments, whole, budget=14
            ),
            "provider_field_aware": _retrieval_metrics(
                [issue.id for issue in issues], judgments, fields, budget=14
            ),
            "exact_identifier": _retrieval_metrics(
                [issue.id for issue in issues], judgments, exact_identifier, budget=14
            ),
            "sparse_tfidf": _retrieval_metrics(
                [issue.id for issue in issues], judgments, sparse, budget=14
            ),
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
