"""Pure semantic ranking and deterministic batching algorithms."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

Vector = Sequence[float]


@dataclass(frozen=True, slots=True)
class Neighbor:
    issue_id: str
    similarity: float
    status: str | None = None


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
) -> list[Neighbor]:
    """Rank candidates by similarity, breaking equal scores by issue ID.

    Records may be mappings or objects and need only expose ``id`` (or
    ``issue_id``) and, when lifecycle filtering matters, ``status``.
    """

    if limit < 0:
        raise ValueError("limit cannot be negative")
    query_id = issue_id(query)
    try:
        query_vector = vectors[query_id]
    except KeyError as exc:
        raise KeyError(f"missing vector for query issue {query_id!r}") from exc

    ranked: list[Neighbor] = []
    for candidate in candidates:
        candidate_id = issue_id(candidate)
        if candidate_id == query_id:
            continue
        status = issue_status(candidate)
        if not include_closed and _is_closed(status):
            continue
        try:
            vector = vectors[candidate_id]
        except KeyError as exc:
            raise KeyError(f"missing vector for candidate issue {candidate_id!r}") from exc
        ranked.append(
            Neighbor(
                issue_id=candidate_id,
                status=status,
                similarity=cosine_similarity(query_vector, vector),
            )
        )
    ranked.sort(key=lambda neighbor: (-neighbor.similarity, neighbor.issue_id))
    return ranked[:limit]


def balanced_batches(
    issues: Sequence[Any],
    vectors: Mapping[str, Vector],
    *,
    target_size: int = 9,
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

    remaining = set(by_id)
    batches: list[list[Any]] = []
    for capacity in capacities:
        seed = _dense_seed(remaining, vectors)
        ordered = sorted(
            remaining - {seed},
            key=lambda identifier: (
                -cosine_similarity(vectors[seed], vectors[identifier]),
                identifier,
            ),
        )
        member_ids = [seed, *ordered[: capacity - 1]]
        batches.append([by_id[identifier] for identifier in member_ids])
        remaining.difference_update(member_ids)
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


def _dense_seed(remaining: set[str], vectors: Mapping[str, Vector]) -> str:
    if len(remaining) == 1:
        return next(iter(remaining))

    def density(identifier: str) -> float:
        others = sorted(remaining - {identifier})
        total = sum(cosine_similarity(vectors[identifier], vectors[other]) for other in others)
        return total / len(others)

    return min(remaining, key=lambda identifier: (-density(identifier), identifier))


def _field(issue: Any, name: str, default: Any) -> Any:
    if isinstance(issue, Mapping):
        return issue.get(name, default)
    return getattr(issue, name, default)


def _is_closed(status: str | None) -> bool:
    return status is not None and status.casefold() in {"closed", "done", "completed", "resolved"}
