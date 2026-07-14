"""Deterministic review-candidate ranking and volume controls."""

from __future__ import annotations

import heapq
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .analysis import issue_id, issue_status


class ScoreIndex(Protocol):
    """The small part of a similarity index needed by candidate ranking."""

    def score(self, left_id: str, right_id: str) -> float: ...


Scorer = ScoreIndex | Callable[[str, str], float]

CLOSED_STATUSES = {"closed", "done", "completed", "resolved"}


@dataclass(frozen=True, slots=True)
class CandidatePolicy:
    """Controls conservative exceptions and the size of the review queue."""

    echo_threshold: float = 0.72
    overlap_threshold: float = 0.82
    exception_margin: float = 0.08
    reciprocal_rank: int = 5
    max_per_issue: int = 3
    max_total: int = 250

    def validate(self) -> None:
        if not -1 <= self.echo_threshold <= 1 or not -1 <= self.overlap_threshold <= 1:
            raise ValueError("similarity thresholds must be between -1 and 1")
        if not 0 <= self.exception_margin <= 2:
            raise ValueError("exception margin must be between 0 and 2")
        if self.reciprocal_rank < 0:
            raise ValueError("reciprocal rank cannot be negative")
        if self.max_per_issue < 1:
            raise ValueError("per-issue candidate cap must be positive")
        if self.max_total < 1:
            raise ValueError("run candidate cap must be positive")


@dataclass(frozen=True, slots=True)
class CandidateRanking:
    candidates: tuple[dict[str, Any], ...]
    qualified: int
    dropped_by_issue_cap: int
    dropped_by_run_cap: int


def rank_candidates(
    population: Sequence[Any],
    all_issues: Sequence[Any],
    scorer: Scorer,
    policy: CandidatePolicy,
) -> CandidateRanking:
    """Rank review candidates, then apply deterministic endpoint and run caps.

    Normal threshold matches remain the highest-signal baseline. A pair within
    ``exception_margin`` of its threshold may also qualify when same-parent or
    dependency structure corroborates it, or when both records rank each other
    within ``reciprocal_rank``. Direct parent/child structure is deliberately
    counterevidence: it never enables a threshold exception by itself.
    """

    policy.validate()
    score = _score_function(scorer)
    active = sorted(population, key=issue_id)
    closed = sorted((item for item in all_issues if _is_closed(issue_status(item))), key=issue_id)

    overlap_ranks = _top_ranks(active, active, score, policy.reciprocal_rank)
    active_to_closed = _top_ranks(active, closed, score, policy.reciprocal_rank)
    closed_to_active = _top_ranks(closed, active, score, policy.reciprocal_rank)

    qualified: list[dict[str, Any]] = []
    for left_index, left in enumerate(active):
        for right in active[left_index + 1 :]:
            candidate = _qualify(
                "possible-overlap",
                left,
                right,
                score,
                threshold=policy.overlap_threshold,
                exception_margin=policy.exception_margin,
                reciprocal_rank=policy.reciprocal_rank,
                left_rank=overlap_ranks.get((issue_id(left), issue_id(right))),
                right_rank=overlap_ranks.get((issue_id(right), issue_id(left))),
            )
            if candidate is not None:
                qualified.append(candidate)

    # Preserve the established one-echo-per-active-record behavior while
    # allowing a corroborated near-threshold record to become that best echo.
    for active_issue in active:
        echoes: list[dict[str, Any]] = []
        for completed_issue in closed:
            if issue_id(active_issue) == issue_id(completed_issue):
                continue
            candidate = _qualify(
                "completed-work-echo",
                active_issue,
                completed_issue,
                score,
                threshold=policy.echo_threshold,
                exception_margin=policy.exception_margin,
                reciprocal_rank=policy.reciprocal_rank,
                left_rank=active_to_closed.get((issue_id(active_issue), issue_id(completed_issue))),
                right_rank=closed_to_active.get(
                    (issue_id(completed_issue), issue_id(active_issue))
                ),
            )
            if candidate is not None:
                echoes.append(candidate)
        if echoes:
            qualified.append(min(echoes, key=_ranking_key))

    ordered = sorted(qualified, key=_ranking_key)
    counts: dict[str, int] = defaultdict(int)
    accepted: list[dict[str, Any]] = []
    dropped_by_issue = 0
    dropped_by_run = 0
    for candidate in ordered:
        if len(accepted) >= policy.max_total:
            dropped_by_run += 1
            continue
        left_id = candidate["issue_id"]
        right_id = candidate["related_issue_id"]
        if counts[left_id] >= policy.max_per_issue or counts[right_id] >= policy.max_per_issue:
            dropped_by_issue += 1
            continue
        accepted.append(candidate)
        counts[left_id] += 1
        counts[right_id] += 1

    return CandidateRanking(
        candidates=tuple(accepted),
        qualified=len(ordered),
        dropped_by_issue_cap=dropped_by_issue,
        dropped_by_run_cap=dropped_by_run,
    )


def structural_context(left: Any, right: Any) -> str:
    left_id = issue_id(left)
    right_id = issue_id(right)
    left_parent = getattr(left, "parent_id", None)
    right_parent = getattr(right, "parent_id", None)
    if left_parent and left_parent == right_parent:
        return f"same parent {left_parent}"
    if left_parent == right_id or right_parent == left_id:
        return "parent/child"
    relationship = _direct_relationship(left, right_id)
    if relationship == "parent-child":
        return "parent/child"
    if relationship:
        return f"{left_id} depends on {right_id} ({relationship})"
    relationship = _direct_relationship(right, left_id)
    if relationship == "parent-child":
        return "parent/child"
    if relationship:
        return f"{right_id} depends on {left_id} ({relationship})"
    return "none recorded"


def _direct_relationship(issue: Any, target_id: str) -> str | None:
    for link in tuple(getattr(issue, "dependency_links", ()) or ()):
        if getattr(link, "target_id", None) == target_id:
            return str(getattr(link, "relationship_type", "depends-on"))
    if target_id in tuple(getattr(issue, "dependencies", ()) or ()):
        return "depends-on"
    return None


def _qualify(
    kind: str,
    left: Any,
    right: Any,
    score: Callable[[str, str], float],
    *,
    threshold: float,
    exception_margin: float,
    reciprocal_rank: int,
    left_rank: int | None,
    right_rank: int | None,
) -> dict[str, Any] | None:
    left_id = issue_id(left)
    right_id = issue_id(right)
    similarity = score(left_id, right_id)
    context = structural_context(left, right)
    reciprocal = (
        reciprocal_rank > 0
        and left_rank is not None
        and right_rank is not None
        and left_rank <= reciprocal_rank
        and right_rank <= reciprocal_rank
    )
    admission_reason = "semantic-threshold"
    if similarity < threshold:
        if similarity < max(-1.0, threshold - exception_margin):
            return None
        if context.startswith("same parent "):
            admission_reason = "shared-parent-threshold-exception"
        elif " depends on " in context:
            admission_reason = "dependency-threshold-exception"
        elif context != "parent/child" and reciprocal:
            admission_reason = "reciprocal-neighbor-threshold-exception"
        else:
            return None

    counterevidence = (
        "Direct parent/child scope may explain semantic similarity; verify distinct outcomes."
        if context == "parent/child"
        else "none recorded"
    )
    what_to_verify = (
        "Check whether the completed outcome changed this active work."
        if kind == "completed-work-echo"
        else "Compare intended outcomes; similar context may still mean different scope."
    )
    return {
        "kind": kind,
        "issue_id": left_id,
        "related_issue_id": right_id,
        "similarity": round(similarity, 6),
        "structural_context": context,
        "admission_reason": admission_reason,
        "reciprocal_ranks": {"issue": left_rank, "related_issue": right_rank},
        "counterevidence": counterevidence,
        "what_to_verify": what_to_verify,
    }


def _top_ranks(
    queries: Sequence[Any],
    candidates: Sequence[Any],
    score: Callable[[str, str], float],
    limit: int,
) -> dict[tuple[str, str], int]:
    if limit == 0:
        return {}
    ranks: dict[tuple[str, str], int] = {}
    candidate_ids = [issue_id(item) for item in candidates]
    for query in queries:
        query_id = issue_id(query)
        eligible = (candidate_id for candidate_id in candidate_ids if candidate_id != query_id)
        ordered = heapq.nsmallest(
            limit,
            eligible,
            key=lambda candidate_id: (-score(query_id, candidate_id), candidate_id),
        )
        ranks.update(
            {
                (
                    query_id,
                    candidate_id,
                ): rank
                for rank, candidate_id in enumerate(ordered, 1)
            }
        )
    return ranks


def _ranking_key(candidate: dict[str, Any]) -> tuple[int, float, str, str, str]:
    exception = candidate["admission_reason"] != "semantic-threshold"
    return (
        int(exception),
        -float(candidate["similarity"]),
        str(candidate["kind"]),
        str(candidate["issue_id"]),
        str(candidate["related_issue_id"]),
    )


def _score_function(scorer: Scorer) -> Callable[[str, str], float]:
    method = getattr(scorer, "score", None)
    if method is not None:
        return lambda left_id, right_id: float(method(left_id, right_id))
    return lambda left_id, right_id: float(scorer(left_id, right_id))


def _is_closed(status: str | None) -> bool:
    return status is not None and status.casefold() in CLOSED_STATUSES
