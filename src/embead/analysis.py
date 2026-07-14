"""Pure semantic ranking and deterministic batching algorithms."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

Vector = Sequence[float]


@dataclass(frozen=True, slots=True)
class Neighbor:
    issue_id: str
    similarity: float
    status: str | None = None


class SimilarityIndex:
    """Validate vectors once and reuse their pairwise cosine similarities.

    Providers and the on-disk cache already return normalized vectors, but the
    index deliberately validates and normalizes its input once at the analysis
    boundary.  The dense score matrix keeps a 1,000-record workspace small
    (about 8 MB with float64 values) while avoiding repeated Python dot products.
    """

    def __init__(self, vectors: Mapping[str, Vector]) -> None:
        self._ids = tuple(sorted(vectors))
        self._positions = {identifier: index for index, identifier in enumerate(self._ids)}
        if not self._ids:
            self._scores = np.empty((0, 0), dtype=np.float64)
            return

        rows: list[list[float]] = []
        dimension: int | None = None
        for identifier in self._ids:
            values = [float(value) for value in vectors[identifier]]
            if not values or any(not math.isfinite(value) for value in values):
                raise ValueError(f"vector for {identifier!r} must be non-empty and finite")
            if dimension is None:
                dimension = len(values)
            elif len(values) != dimension:
                raise ValueError("vectors must have the same dimension")
            rows.append(values)

        matrix = np.asarray(rows, dtype=np.float64)
        norms = np.linalg.norm(matrix, axis=1)
        if np.any(norms == 0):
            identifier = self._ids[int(np.flatnonzero(norms == 0)[0])]
            raise ValueError(f"cannot normalize zero vector for {identifier!r}")
        matrix /= norms[:, np.newaxis]
        self._scores = matrix @ matrix.T
        np.clip(self._scores, -1.0, 1.0, out=self._scores)

    @property
    def ids(self) -> tuple[str, ...]:
        return self._ids

    def score(self, left_id: str, right_id: str) -> float:
        """Return a cached cosine score for two indexed IDs."""

        return float(self._scores[self._position(left_id), self._position(right_id)])

    def ranked(self, query_id: str, candidate_ids: Sequence[str]) -> list[tuple[str, float]]:
        """Rank candidate IDs by descending score, then ascending ID."""

        self._position(query_id)
        unique_ids = set(candidate_ids)
        ranked = [(identifier, self.score(query_id, identifier)) for identifier in unique_ids]
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked

    def sum_scores(
        self,
        query_ids: Sequence[str],
        candidate_ids: Sequence[str],
    ) -> dict[str, float]:
        """Return vectorized score sums for density updates."""

        queries = list(query_ids)
        candidates = list(candidate_ids)
        if not candidates:
            return {identifier: 0.0 for identifier in queries}
        query_positions = [self._position(identifier) for identifier in queries]
        candidate_positions = [self._position(identifier) for identifier in candidates]
        totals = self._scores[np.ix_(query_positions, candidate_positions)].sum(axis=1)
        return dict(zip(queries, (float(value) for value in totals), strict=True))

    def _position(self, identifier: str) -> int:
        try:
            return self._positions[identifier]
        except KeyError as exc:
            raise KeyError(f"missing vector for issue {identifier!r}") from exc


def normalize(vector: Vector) -> list[float]:
    """Return a unit vector, rejecting malformed embedding output."""

    values = [float(value) for value in vector]
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("vectors must be non-empty and finite")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise ValueError("cannot normalize a zero vector")
    return [value / norm for value in values]


def cosine_similarity(left: Vector, right: Vector) -> float:
    """Compute cosine similarity without requiring NumPy."""

    if len(left) != len(right):
        raise ValueError("vectors must have the same dimension")
    normalized_left = normalize(left)
    normalized_right = normalize(right)
    score = sum(a * b for a, b in zip(normalized_left, normalized_right, strict=True))
    # Avoid surprising values such as 1.0000000000000002 in reports and thresholds.
    return max(-1.0, min(1.0, score))


def nearest_neighbors(
    query: Any,
    candidates: Sequence[Any],
    vectors: Mapping[str, Vector],
    *,
    limit: int = 10,
    include_closed: bool = False,
    similarity_index: SimilarityIndex | None = None,
) -> list[Neighbor]:
    """Rank candidates by similarity, breaking equal scores by issue ID.

    Records may be mappings or objects and need only expose ``id`` (or
    ``issue_id``) and, when lifecycle filtering matters, ``status``.
    """

    if limit < 0:
        raise ValueError("limit cannot be negative")
    query_id = issue_id(query)
    if query_id not in vectors:
        raise KeyError(f"missing vector for query issue {query_id!r}")
    index = similarity_index or SimilarityIndex(vectors)

    ranked: list[Neighbor] = []
    for candidate in candidates:
        candidate_id = issue_id(candidate)
        if candidate_id == query_id:
            continue
        status = issue_status(candidate)
        if not include_closed and _is_closed(status):
            continue
        if candidate_id not in vectors:
            raise KeyError(f"missing vector for candidate issue {candidate_id!r}")
        ranked.append(
            Neighbor(
                issue_id=candidate_id,
                status=status,
                similarity=index.score(query_id, candidate_id),
            )
        )
    ranked.sort(key=lambda neighbor: (-neighbor.similarity, neighbor.issue_id))
    return ranked[:limit]


def balanced_batches(
    issues: Sequence[Any],
    vectors: Mapping[str, Vector],
    *,
    target_size: int = 9,
    similarity_index: SimilarityIndex | None = None,
) -> list[list[Any]]:
    """Partition issues into deterministic, balanced semantic neighborhoods.

    The densest remaining record is selected as each seed; its closest remaining
    records fill the batch. Every input appears exactly once, and batch sizes
    differ by at most one.
    """

    if target_size < 1:
        raise ValueError("target_size must be positive")
    if not issues:
        return []

    by_id: dict[str, Any] = {}
    for issue in issues:
        identifier = issue_id(issue)
        if identifier in by_id:
            raise ValueError(f"duplicate issue ID: {identifier}")
        if identifier not in vectors:
            raise KeyError(f"missing vector for issue {identifier!r}")
        by_id[identifier] = issue

    count = len(by_id)
    # Round half up rather than using Python's even-number tie breaking.
    batch_count = max(1, (count + target_size // 2) // target_size)
    batch_count = min(batch_count, count)
    quotient, remainder = divmod(count, batch_count)
    capacities = [quotient + (index < remainder) for index in range(batch_count)]

    index = similarity_index or SimilarityIndex(
        {identifier: vectors[identifier] for identifier in by_id}
    )
    remaining = set(by_id)
    ordered_ids = sorted(remaining)
    totals = index.sum_scores(ordered_ids, ordered_ids)
    for identifier in ordered_ids:
        totals[identifier] -= index.score(identifier, identifier)
    batches: list[list[Any]] = []
    for capacity in capacities:
        if len(remaining) == 1:
            seed = next(iter(remaining))
        else:
            seed = min(
                remaining,
                key=lambda identifier: (-totals[identifier] / (len(remaining) - 1), identifier),
            )
        ordered = [
            identifier
            for identifier, _score in index.ranked(seed, sorted(remaining - {seed}))
        ]
        member_ids = [seed, *ordered[: capacity - 1]]
        batches.append([by_id[identifier] for identifier in member_ids])
        remaining.difference_update(member_ids)
        if remaining:
            reductions = index.sum_scores(sorted(remaining), member_ids)
            for identifier, reduction in reductions.items():
                totals[identifier] -= reduction
    return batches


def issue_id(issue: Any) -> str:
    value = _field(issue, "id", _field(issue, "issue_id", None))
    if value is None or str(value) == "":
        raise ValueError("issue must have a non-empty id or issue_id")
    return str(value)


def issue_status(issue: Any) -> str | None:
    value = _field(issue, "status", None)
    return None if value is None else str(value)


def issue_text(issue: Any) -> str:
    """Read pre-canonicalized text from a duck-typed issue record."""

    value = _field(issue, "text", _field(issue, "canonical_text", None))
    if value is None:
        raise ValueError("issue must have text or canonical_text")
    return str(value)


def _field(issue: Any, name: str, default: Any) -> Any:
    if isinstance(issue, Mapping):
        return issue.get(name, default)
    return getattr(issue, name, default)


def _is_closed(status: str | None) -> bool:
    return status is not None and status.casefold() in {"closed", "done", "completed", "resolved"}
