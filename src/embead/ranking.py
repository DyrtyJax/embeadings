"""Deterministic review-candidate ranking and volume controls."""

from __future__ import annotations

import heapq
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from .analysis import issue_id, issue_status


class ScoreIndex(Protocol):
    """The small part of a similarity index needed by candidate ranking."""

    def score(self, left_id: str, right_id: str) -> float: ...


Scorer = ScoreIndex | Callable[[str, str], float]

CLOSED_STATUSES = {"closed", "done", "completed", "resolved"}
LANES = ("dependency", "echo", "overlap")
DEFAULT_ECHO_THRESHOLD = 0.72
DEFAULT_OVERLAP_THRESHOLD = 0.82


@dataclass(frozen=True, slots=True)
class CandidatePolicy:
    """Controls conservative exceptions and the size of the review queue."""

    echo_threshold: float = DEFAULT_ECHO_THRESHOLD
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD
    exception_margin: float = 0.08
    reciprocal_rank: int = 5
    max_per_issue: int = 3
    max_dependencies_per_issue: int = 3
    max_total: int = 250
    max_dependencies: int = 75
    max_echoes: int = 125
    max_overlaps: int = 125
    baseline_echo_threshold: float = DEFAULT_ECHO_THRESHOLD
    baseline_overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD

    def validate(self) -> None:
        thresholds = (
            self.echo_threshold,
            self.overlap_threshold,
            self.baseline_echo_threshold,
            self.baseline_overlap_threshold,
        )
        if any(not -1 <= value <= 1 for value in thresholds):
            raise ValueError("similarity thresholds must be between -1 and 1")
        if not 0 <= self.exception_margin <= 2:
            raise ValueError("exception margin must be between 0 and 2")
        if self.reciprocal_rank < 0:
            raise ValueError("reciprocal rank cannot be negative")
        if self.max_per_issue < 1:
            raise ValueError("per-issue candidate cap must be positive")
        if self.max_dependencies_per_issue < 0:
            raise ValueError("per-issue dependency candidate cap cannot be negative")
        if self.max_total < 1:
            raise ValueError("run candidate cap must be positive")
        if any(value < 0 for value in self.lane_caps.values()):
            raise ValueError("lane candidate caps cannot be negative")

    @property
    def lane_caps(self) -> dict[str, int]:
        return {
            "dependency": self.max_dependencies,
            "echo": self.max_echoes,
            "overlap": self.max_overlaps,
        }


@dataclass(frozen=True, slots=True)
class LaneMetrics:
    qualified: int = 0
    admitted: int = 0
    baseline_protected: int = 0
    dropped_by_lane_cap: int = 0
    dropped_by_issue_cap: int = 0
    dropped_by_dependency_issue_cap: int = 0
    dropped_by_run_cap: int = 0


@dataclass(frozen=True, slots=True)
class CandidateRanking:
    candidates: tuple[dict[str, Any], ...]
    qualified: int
    dropped_by_issue_cap: int
    dropped_by_run_cap: int
    lanes: dict[str, LaneMetrics] | None = None
    baseline_protected: int = 0
    dropped_by_lane_cap: int = 0
    dropped_by_dependency_issue_cap: int = 0
    capped_typed_dependencies: tuple[dict[str, str], ...] = ()
    reciprocal_diagnostics: dict[str, Any] | None = None
    cap_replacements: tuple[dict[str, Any], ...] = ()


def rank_candidates(
    population: Sequence[Any],
    all_issues: Sequence[Any],
    scorer: Scorer,
    policy: CandidatePolicy,
    *,
    eligible_issue_ids: frozenset[str] | None = None,
) -> CandidateRanking:
    """Rank candidates into independently budgeted deterministic review lanes.

    Typed dependency candidates are admitted before semantic echo and overlap
    candidates. When thresholds are lowered below the normal defaults, the
    queue selected at the default thresholds is protected first. Sensitivity
    additions may consume only the capacity that remains, so a permissive run
    cannot make a baseline candidate disappear under the same caps.
    """

    policy.validate()
    score = _score_function(scorer)
    active = sorted(population, key=issue_id)
    closed = sorted((item for item in all_issues if _is_closed(issue_status(item))), key=issue_id)
    ranks = _Ranks.build(active, closed, score, policy.reciprocal_rank)

    reciprocal_diagnostics = _empty_reciprocal_diagnostics()
    requested = _qualifying_candidates(
        active,
        closed,
        score,
        ranks,
        policy,
        echo_threshold=policy.echo_threshold,
        overlap_threshold=policy.overlap_threshold,
        reciprocal_diagnostics=reciprocal_diagnostics,
    )
    if eligible_issue_ids is not None:
        requested = [
            item
            for item in requested
            if item["issue_id"] in eligible_issue_ids
            or item["related_issue_id"] in eligible_issue_ids
        ]
    is_sensitivity = (
        policy.echo_threshold < policy.baseline_echo_threshold
        or policy.overlap_threshold < policy.baseline_overlap_threshold
    )
    baseline: list[dict[str, Any]] = []
    if is_sensitivity:
        baseline = _qualifying_candidates(
            active,
            closed,
            score,
            ranks,
            policy,
            echo_threshold=policy.baseline_echo_threshold,
            overlap_threshold=policy.baseline_overlap_threshold,
        )
        if eligible_issue_ids is not None:
            baseline = [
                item
                for item in baseline
                if item["issue_id"] in eligible_issue_ids
                or item["related_issue_id"] in eligible_issue_ids
            ]

    result = _select_candidates(baseline, requested, policy)
    reciprocal_admitted = sum(
        item["admission_reason"] == "reciprocal-neighbor-threshold-exception"
        for item in result.candidates
    )
    reciprocal_diagnostics["admitted"] = reciprocal_admitted
    reciprocal_diagnostics["admission_reasons"] = (
        {"substantive-field-token": reciprocal_admitted} if reciprocal_admitted else {}
    )
    replacements: tuple[dict[str, Any], ...] = ()
    is_conservative = (
        policy.echo_threshold > policy.baseline_echo_threshold
        or policy.overlap_threshold > policy.baseline_overlap_threshold
    )
    if is_conservative:
        reference = _qualifying_candidates(
            active,
            closed,
            score,
            ranks,
            policy,
            echo_threshold=policy.baseline_echo_threshold,
            overlap_threshold=policy.baseline_overlap_threshold,
        )
        if eligible_issue_ids is not None:
            reference = [
                item
                for item in reference
                if item["issue_id"] in eligible_issue_ids
                or item["related_issue_id"] in eligible_issue_ids
            ]
        reference_result = _select_candidates((), reference, policy)
        replacements = _cap_replacements(reference_result.candidates, result.candidates, policy)
    return replace(
        result,
        reciprocal_diagnostics=reciprocal_diagnostics,
        cap_replacements=replacements,
    )


@dataclass(frozen=True, slots=True)
class _Ranks:
    overlap: dict[tuple[str, str], int]
    active_to_closed: dict[tuple[str, str], int]
    closed_to_active: dict[tuple[str, str], int]

    @classmethod
    def build(
        cls,
        active: Sequence[Any],
        closed: Sequence[Any],
        score: Callable[[str, str], float],
        limit: int,
    ) -> _Ranks:
        return cls(
            overlap=_top_ranks(active, active, score, limit),
            active_to_closed=_top_ranks(active, closed, score, limit),
            closed_to_active=_top_ranks(closed, active, score, limit),
        )


def _qualifying_candidates(
    active: Sequence[Any],
    closed: Sequence[Any],
    score: Callable[[str, str], float],
    ranks: _Ranks,
    policy: CandidatePolicy,
    *,
    echo_threshold: float,
    overlap_threshold: float,
    reciprocal_diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    qualified: list[dict[str, Any]] = []
    for left_index, left in enumerate(active):
        for right in active[left_index + 1 :]:
            candidate = _qualify(
                "possible-overlap",
                left,
                right,
                score,
                threshold=overlap_threshold,
                exception_margin=policy.exception_margin,
                reciprocal_rank=policy.reciprocal_rank,
                left_rank=ranks.overlap.get((issue_id(left), issue_id(right))),
                right_rank=ranks.overlap.get((issue_id(right), issue_id(left))),
                reciprocal_diagnostics=reciprocal_diagnostics,
            )
            if candidate is not None:
                qualified.append(candidate)

    for active_issue in active:
        echoes: list[dict[str, Any]] = []
        dependency_echoes: list[dict[str, Any]] = []
        for completed_issue in closed:
            if issue_id(active_issue) == issue_id(completed_issue):
                continue
            candidate = _qualify(
                "completed-work-echo",
                active_issue,
                completed_issue,
                score,
                threshold=echo_threshold,
                exception_margin=policy.exception_margin,
                reciprocal_rank=policy.reciprocal_rank,
                left_rank=ranks.active_to_closed.get(
                    (issue_id(active_issue), issue_id(completed_issue))
                ),
                right_rank=ranks.closed_to_active.get(
                    (issue_id(completed_issue), issue_id(active_issue))
                ),
                reciprocal_diagnostics=reciprocal_diagnostics,
            )
            if candidate is not None:
                if candidate["lane"] == "dependency":
                    dependency_echoes.append(candidate)
                else:
                    echoes.append(candidate)
        qualified.extend(dependency_echoes)
        if echoes:
            qualified.append(min(echoes, key=_ranking_key))
    return qualified


def _select_candidates(
    baseline: Sequence[dict[str, Any]],
    requested: Sequence[dict[str, Any]],
    policy: CandidatePolicy,
) -> CandidateRanking:
    baseline_keys = {_candidate_identity(item) for item in baseline}
    requested_by_key = {_candidate_identity(item): item for item in requested}
    # A lower threshold is a superset by construction. Keep the defensive
    # fallback so diagnostics remain honest if a future qualification rule changes.
    baseline_stage = [requested_by_key.get(_candidate_identity(item), item) for item in baseline]
    additions = [item for item in requested if _candidate_identity(item) not in baseline_keys]
    stages = ((baseline_stage, True), (additions, False)) if baseline else ((requested, False),)

    semantic_counts: dict[str, int] = defaultdict(int)
    dependency_counts: dict[str, int] = defaultdict(int)
    lane_counts: dict[str, int] = defaultdict(int)
    metrics: dict[str, dict[str, int]] = {
        lane: {
            "qualified": 0,
            "admitted": 0,
            "baseline_protected": 0,
            "dropped_by_lane_cap": 0,
            "dropped_by_issue_cap": 0,
            "dropped_by_dependency_issue_cap": 0,
            "dropped_by_run_cap": 0,
        }
        for lane in LANES
    }
    accepted: list[dict[str, Any]] = []
    capped_typed_dependencies: list[dict[str, str]] = []
    seen_issues_by_kind: set[tuple[str, str]] = set()
    for candidates, protected in stages:
        for candidate in sorted(candidates, key=_ranking_key):
            lane = candidate["lane"]
            values = metrics[lane]
            values["qualified"] += 1
            if lane_counts[lane] >= policy.lane_caps[lane]:
                values["dropped_by_lane_cap"] += 1
                _record_capped_dependency(capped_typed_dependencies, candidate, "lane-cap")
                continue
            if len(accepted) >= policy.max_total:
                values["dropped_by_run_cap"] += 1
                _record_capped_dependency(capped_typed_dependencies, candidate, "run-cap")
                continue
            left_id = candidate["issue_id"]
            right_id = candidate["related_issue_id"]
            if lane == "dependency":
                if (
                    dependency_counts[left_id] >= policy.max_dependencies_per_issue
                    or dependency_counts[right_id] >= policy.max_dependencies_per_issue
                ):
                    values["dropped_by_issue_cap"] += 1
                    values["dropped_by_dependency_issue_cap"] += 1
                    _record_capped_dependency(
                        capped_typed_dependencies, candidate, "dependency-per-issue-cap"
                    )
                    continue
            elif (
                semantic_counts[left_id] >= policy.max_per_issue
                or semantic_counts[right_id] >= policy.max_per_issue
            ):
                values["dropped_by_issue_cap"] += 1
                continue
            # Keep the established one-echo-per-active-record invariant even
            # when a sensitivity run finds another lower-scoring closed issue.
            kind_issue = (candidate["kind"], left_id)
            if (
                candidate["lane"] == "echo"
                and candidate["kind"] == "completed-work-echo"
                and kind_issue in seen_issues_by_kind
            ):
                values["dropped_by_issue_cap"] += 1
                continue
            admitted = {**candidate, "baseline_protected": protected}
            accepted.append(admitted)
            if lane == "dependency":
                dependency_counts[left_id] += 1
                dependency_counts[right_id] += 1
            else:
                semantic_counts[left_id] += 1
                semantic_counts[right_id] += 1
            lane_counts[lane] += 1
            if candidate["lane"] == "echo":
                seen_issues_by_kind.add(kind_issue)
            values["admitted"] += 1
            values["baseline_protected"] += int(protected)

    lane_metrics = {lane: LaneMetrics(**values) for lane, values in metrics.items()}
    return CandidateRanking(
        candidates=tuple(accepted),
        qualified=sum(values.qualified for values in lane_metrics.values()),
        dropped_by_issue_cap=sum(values.dropped_by_issue_cap for values in lane_metrics.values()),
        dropped_by_run_cap=sum(values.dropped_by_run_cap for values in lane_metrics.values()),
        lanes=lane_metrics,
        baseline_protected=sum(values.baseline_protected for values in lane_metrics.values()),
        dropped_by_lane_cap=sum(values.dropped_by_lane_cap for values in lane_metrics.values()),
        dropped_by_dependency_issue_cap=sum(
            values.dropped_by_dependency_issue_cap for values in lane_metrics.values()
        ),
        capped_typed_dependencies=tuple(capped_typed_dependencies),
    )


def _record_capped_dependency(
    summary: list[dict[str, str]], candidate: dict[str, Any], reason: str
) -> None:
    """Record bounded structural context without promoting it to a candidate."""

    evidence = candidate.get("dependency_evidence")
    if not isinstance(evidence, dict):
        return
    summary.append(
        {
            "source_id": str(evidence["source_id"]),
            "target_id": str(evidence["target_id"]),
            "type": str(evidence["type"]),
            "drop_reason": reason,
        }
    )


def structural_context(left: Any, right: Any) -> str:
    left_id = issue_id(left)
    right_id = issue_id(right)
    left_parent = getattr(left, "parent_id", None)
    right_parent = getattr(right, "parent_id", None)
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
    if left_parent and left_parent == right_parent:
        return f"same parent {left_parent}"
    return "none recorded"


def dependency_evidence(left: Any, right: Any) -> dict[str, str] | None:
    """Return typed, directed dependency evidence, excluding parent/child links."""

    left_id = issue_id(left)
    right_id = issue_id(right)
    relationship = _direct_relationship(left, right_id)
    if relationship and relationship != "parent-child":
        return {"source_id": left_id, "target_id": right_id, "type": relationship}
    relationship = _direct_relationship(right, left_id)
    if relationship and relationship != "parent-child":
        return {"source_id": right_id, "target_id": left_id, "type": relationship}
    return None


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
    reciprocal_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    left_id = issue_id(left)
    right_id = issue_id(right)
    similarity = score(left_id, right_id)
    context = structural_context(left, right)
    relationship = dependency_evidence(left, right)
    reciprocal = (
        reciprocal_rank > 0
        and left_rank is not None
        and right_rank is not None
        and left_rank <= reciprocal_rank
        and right_rank <= reciprocal_rank
    )
    admission_reason = "semantic-threshold"
    signal_quality = "semantic"
    if similarity < threshold:
        if similarity < max(-1.0, threshold - exception_margin):
            return None
        if context.startswith("same parent "):
            admission_reason = "shared-parent-threshold-exception"
        elif relationship is not None:
            admission_reason = "dependency-threshold-exception"
        elif context != "parent/child" and reciprocal:
            signal_quality = _reciprocal_signal_quality(left, right)
            if signal_quality == "generic-vocabulary-only":
                _increment_reciprocal(
                    reciprocal_diagnostics, "omission_reasons", "generic-vocabulary-only"
                )
                return None
            admission_reason = "reciprocal-neighbor-threshold-exception"
            _increment_reciprocal(
                reciprocal_diagnostics,
                "admission_reasons",
                "substantive-field-token",
            )
        else:
            return None

    lane = (
        "dependency"
        if relationship is not None
        else "echo"
        if kind == "completed-work-echo"
        else "overlap"
    )
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
        "lane": lane,
        "issue_id": left_id,
        "related_issue_id": right_id,
        "similarity": round(similarity, 6),
        "structural_context": context,
        "dependency_evidence": relationship,
        "admission_reason": admission_reason,
        "signal_quality": signal_quality,
        "reciprocal_ranks": {"issue": left_rank, "related_issue": right_rank},
        "counterevidence": counterevidence,
        "what_to_verify": what_to_verify,
    }


def _reciprocal_signal_quality(left: Any, right: Any) -> str:
    generic = {
        "add",
        "architecture",
        "build",
        "change",
        "component",
        "data",
        "design",
        "flow",
        "implement",
        "implementation",
        "infrastructure",
        "lifecycle",
        "module",
        "process",
        "project",
        "service",
        "state",
        "system",
        "update",
        "workflow",
    }

    def tokens(field: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]{3,}", field.casefold())) - generic

    substantive = ("description", "acceptance_criteria", "design")
    substantive_shared = set().union(
        *(
            tokens(str(getattr(left, field, ""))) & tokens(str(getattr(right, field, "")))
            for field in substantive
        )
    )
    return "substantive" if substantive_shared else "generic-vocabulary-only"


def _empty_reciprocal_diagnostics() -> dict[str, Any]:
    return {"admitted": 0, "omitted": 0, "admission_reasons": {}, "omission_reasons": {}}


def _increment_reciprocal(diagnostics: dict[str, Any] | None, category: str, reason: str) -> None:
    if diagnostics is None:
        return
    counts = diagnostics[category]
    counts[reason] = counts.get(reason, 0) + 1
    diagnostics["admitted" if category == "admission_reasons" else "omitted"] += 1


def _cap_replacements(
    reference: Sequence[dict[str, Any]],
    conservative: Sequence[dict[str, Any]],
    policy: CandidatePolicy,
) -> tuple[dict[str, Any], ...]:
    """Explain stricter-threshold additions caused by bounded winner selection."""

    reference_keys = {_candidate_identity(item) for item in reference}
    conservative_keys = {_candidate_identity(item) for item in conservative}
    introduced = [item for item in conservative if _candidate_identity(item) not in reference_keys]
    displaced = [item for item in reference if _candidate_identity(item) not in conservative_keys]
    diagnostics: list[dict[str, Any]] = []
    for candidate in introduced:
        cap = _governing_replacement_cap(candidate, reference, displaced, policy)
        if cap is None:
            continue
        related = [
            item
            for item in displaced
            if item["lane"] == candidate["lane"]
            and (
                candidate["issue_id"] in (item["issue_id"], item["related_issue_id"])
                or candidate["related_issue_id"] in (item["issue_id"], item["related_issue_id"])
                or cap in {"run-cap", f"lane-cap:{candidate['lane']}"}
            )
        ]
        diagnostics.append(
            {
                "candidate_id": _candidate_id(candidate),
                "governing_cap": cap,
                "displaced_candidate_ids": sorted(_candidate_id(item) for item in related),
            }
        )
    return tuple(sorted(diagnostics, key=lambda item: item["candidate_id"]))


def _governing_replacement_cap(
    candidate: dict[str, Any],
    reference: Sequence[dict[str, Any]],
    displaced: Sequence[dict[str, Any]],
    policy: CandidatePolicy,
) -> str | None:
    if candidate["kind"] == "completed-work-echo" and any(
        item["kind"] == candidate["kind"] and item["issue_id"] == candidate["issue_id"]
        for item in displaced
    ):
        return "one-echo-per-active-record"
    endpoints = {candidate["issue_id"], candidate["related_issue_id"]}
    cap = (
        policy.max_dependencies_per_issue
        if candidate["lane"] == "dependency"
        else policy.max_per_issue
    )
    if any(
        sum(endpoint in (item["issue_id"], item["related_issue_id"]) for item in reference) >= cap
        for endpoint in endpoints
    ):
        return (
            "max-dependencies-per-issue"
            if candidate["lane"] == "dependency"
            else "max-candidates-per-issue"
        )
    lane = candidate["lane"]
    if sum(item["lane"] == lane for item in reference) >= policy.lane_caps[lane]:
        return f"lane-cap:{lane}"
    if len(reference) >= policy.max_total:
        return "run-cap"
    return None


def _candidate_id(candidate: dict[str, Any]) -> str:
    return "|".join(str(value) for value in _candidate_identity(candidate))


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
            {(query_id, candidate_id): rank for rank, candidate_id in enumerate(ordered, 1)}
        )
    return ranks


def _candidate_identity(candidate: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(candidate["kind"]),
        str(candidate["issue_id"]),
        str(candidate["related_issue_id"]),
    )


def _ranking_key(candidate: dict[str, Any]) -> tuple[int, int, int, float, str, str, str]:
    lane_priority = LANES.index(candidate["lane"])
    exception = candidate["admission_reason"] != "semantic-threshold"
    vocabulary_only = candidate.get("signal_quality") == "vocabulary-only"
    return (
        lane_priority,
        int(exception),
        int(vocabulary_only),
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
