"""Deterministic review-candidate ranking and volume controls."""

from __future__ import annotations

import heapq
import math
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
class DependencyFunnel:
    """Privacy-safe conservation counts for non-parent typed dependencies."""

    total_non_parent_typed: int = 0
    inactive_or_closed_only: int = 0
    below_qualification: int = 0
    eligible: int = 0
    admitted: int = 0
    omitted_by_per_issue_cap: int = 0
    omitted_by_lane_cap: int = 0
    omitted_by_run_cap: int = 0

    @property
    def excluded(self) -> int:
        return self.inactive_or_closed_only + self.below_qualification

    def validate(self) -> None:
        if self.total_non_parent_typed != self.excluded + self.eligible:
            raise ValueError("typed dependency discovery funnel does not conserve")
        omitted = self.omitted_by_per_issue_cap + self.omitted_by_lane_cap + self.omitted_by_run_cap
        if self.eligible != self.admitted + omitted:
            raise ValueError("typed dependency admission funnel does not conserve")


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
    dependency_funnel: DependencyFunnel | None = None


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
    reciprocal_evidence = _ReciprocalEvidence.build((*active, *closed))

    reciprocal_diagnostics = _empty_reciprocal_diagnostics()
    requested = _qualifying_candidates(
        active,
        closed,
        score,
        ranks,
        policy,
        echo_threshold=policy.echo_threshold,
        overlap_threshold=policy.overlap_threshold,
        reciprocal_evidence=reciprocal_evidence,
        reciprocal_diagnostics=reciprocal_diagnostics,
    )
    if eligible_issue_ids is not None:
        requested = [
            item
            for item in requested
            if item["issue_id"] in eligible_issue_ids
            or item["related_issue_id"] in eligible_issue_ids
        ]
    dependency_funnel = _dependency_discovery_funnel(
        active,
        all_issues,
        score,
        echo_threshold=policy.echo_threshold,
        overlap_threshold=policy.overlap_threshold,
        exception_margin=policy.exception_margin,
        eligible_issue_ids=eligible_issue_ids,
    )
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
            reciprocal_evidence=reciprocal_evidence,
        )
        if eligible_issue_ids is not None:
            baseline = [
                item
                for item in baseline
                if item["issue_id"] in eligible_issue_ids
                or item["related_issue_id"] in eligible_issue_ids
            ]

    result = _select_candidates(baseline, requested, policy)
    dependency_metrics = (result.lanes or {}).get("dependency", LaneMetrics())
    dependency_funnel = replace(
        dependency_funnel,
        admitted=dependency_metrics.admitted,
        omitted_by_per_issue_cap=dependency_metrics.dropped_by_dependency_issue_cap,
        omitted_by_lane_cap=dependency_metrics.dropped_by_lane_cap,
        omitted_by_run_cap=dependency_metrics.dropped_by_run_cap,
    )
    dependency_funnel.validate()
    reciprocal_admitted = sum(
        item["admission_reason"] == "reciprocal-neighbor-threshold-exception"
        for item in result.candidates
    )
    reciprocal_diagnostics["admitted"] = reciprocal_admitted
    admitted_reasons: dict[str, int] = defaultdict(int)
    for item in result.candidates:
        reason = item.get("reciprocal_evidence")
        if reason:
            admitted_reasons[str(reason)] += 1
    reciprocal_diagnostics["admission_reasons"] = dict(sorted(admitted_reasons.items()))
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
            reciprocal_evidence=reciprocal_evidence,
        )
        if eligible_issue_ids is not None:
            reference = [
                item
                for item in reference
                if item["issue_id"] in eligible_issue_ids
                or item["related_issue_id"] in eligible_issue_ids
            ]
        reference_result = _select_candidates((), reference, policy)
        replacements = _cap_replacements(
            reference_result.candidates,
            result.candidates,
            policy,
            reference_qualified=reference,
            conservative_qualified=requested,
        )
    return replace(
        result,
        reciprocal_diagnostics=reciprocal_diagnostics,
        cap_replacements=replacements,
        dependency_funnel=dependency_funnel,
    )


def _dependency_discovery_funnel(
    active: Sequence[Any],
    all_issues: Sequence[Any],
    score: Callable[[str, str], float],
    *,
    echo_threshold: float,
    overlap_threshold: float,
    exception_margin: float,
    eligible_issue_ids: frozenset[str] | None,
) -> DependencyFunnel:
    """Classify each typed edge once without retaining endpoint details.

    An edge is comparable when both endpoints are in the selected active
    population, or when one selected active endpoint points to a closed record.
    Incremental runs additionally require one active endpoint in the changed
    scope. All other edges are inactive for this review queue.
    """

    active_ids = {issue_id(item) for item in active}
    records = {issue_id(item): item for item in all_issues}
    seen: set[tuple[str, str, str]] = set()
    total = inactive = below = eligible = 0
    for source in all_issues:
        source_id = issue_id(source)
        typed_links = [
            (
                str(getattr(link, "target_id", "")),
                str(getattr(link, "relationship_type", "depends-on")),
            )
            for link in tuple(getattr(source, "dependency_links", ()) or ())
        ]
        typed_targets = {target for target, _ in typed_links}
        typed_links.extend(
            (str(target), "depends-on")
            for target in tuple(getattr(source, "dependencies", ()) or ())
            if str(target) not in typed_targets
        )
        for target_id, relationship_type in typed_links:
            if relationship_type == "parent-child":
                continue
            identity = (source_id, target_id, relationship_type)
            if identity in seen:
                continue
            seen.add(identity)
            total += 1
            target = records.get(target_id)
            active_endpoints = {
                identifier for identifier in (source_id, target_id) if identifier in active_ids
            }
            in_incremental_scope = eligible_issue_ids is None or bool(
                active_endpoints & eligible_issue_ids
            )
            comparable = (
                target is not None
                and in_incremental_scope
                and (
                    len(active_endpoints) == 2
                    or (
                        len(active_endpoints) == 1
                        and (_is_closed(issue_status(source)) or _is_closed(issue_status(target)))
                    )
                )
            )
            if not comparable:
                inactive += 1
                continue
            threshold = overlap_threshold if len(active_endpoints) == 2 else echo_threshold
            if score(source_id, target_id) < max(-1.0, threshold - exception_margin):
                below += 1
            else:
                eligible += 1
    return DependencyFunnel(
        total_non_parent_typed=total,
        inactive_or_closed_only=inactive,
        below_qualification=below,
        eligible=eligible,
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
    reciprocal_evidence: _ReciprocalEvidence,
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
                reciprocal_evidence=reciprocal_evidence,
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
                reciprocal_evidence=reciprocal_evidence,
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
    reciprocal_evidence: _ReciprocalEvidence,
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
    reciprocal_reason: str | None = None
    if similarity < threshold:
        if similarity < max(-1.0, threshold - exception_margin):
            return None
        if context.startswith("same parent "):
            admission_reason = "shared-parent-threshold-exception"
        elif relationship is not None:
            admission_reason = "dependency-threshold-exception"
        elif context != "parent/child" and reciprocal:
            reciprocal_reason = reciprocal_evidence.reason(left, right)
            if reciprocal_reason is None:
                _increment_reciprocal(
                    reciprocal_diagnostics, "omission_reasons", "no-discriminative-local-evidence"
                )
                return None
            admission_reason = "reciprocal-neighbor-threshold-exception"
            signal_quality = "discriminative-local-evidence"
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
    structural_corroboration = (
        "typed-dependency"
        if relationship is not None
        else "shared-parent"
        if context.startswith("same parent ")
        else "none"
    )
    evidence_basis = (
        "structurally-corroborated" if structural_corroboration != "none" else "semantic-only"
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
        "reciprocal_evidence": reciprocal_reason if similarity < threshold and reciprocal else None,
        "candidate_evidence": {
            "evidence_basis": evidence_basis,
            "structural_corroboration": structural_corroboration,
            "admission_path": admission_reason,
            "uncertainty": (
                "structural-corroboration-recorded"
                if evidence_basis == "structurally-corroborated"
                else "no-structural-corroboration"
            ),
        },
        "reciprocal_ranks": {"issue": left_rank, "related_issue": right_rank},
        "counterevidence": counterevidence,
        "what_to_verify": what_to_verify,
    }


@dataclass(frozen=True, slots=True)
class _ReciprocalEvidence:
    """Corpus-relative field evidence without exposing matched tracker text."""

    token_frequency: dict[str, int]
    phrase_frequency: dict[str, int]
    corpus_size: int

    @classmethod
    def build(cls, issues: Sequence[Any]) -> _ReciprocalEvidence:
        unique = {issue_id(item): item for item in issues}
        token_frequency: dict[str, int] = defaultdict(int)
        phrase_frequency: dict[str, int] = defaultdict(int)
        for item in unique.values():
            fields = _reciprocal_fields(item)
            for token in set().union(*(set(tokens) for tokens in fields.values())):
                token_frequency[token] += 1
            for phrase in set().union(*(_phrases(tokens) for tokens in fields.values())):
                phrase_frequency[phrase] += 1
        return cls(dict(token_frequency), dict(phrase_frequency), len(unique))

    @property
    def rarity_limit(self) -> int:
        return max(2, math.floor(self.corpus_size * 0.1))

    @property
    def title_alignment_limit(self) -> int:
        return max(2, math.floor(self.corpus_size * 0.03))

    def reason(self, left: Any, right: Any) -> str | None:
        left_fields = _reciprocal_fields(left)
        right_fields = _reciprocal_fields(right)

        shared_title = set(left_fields["title"]) & set(right_fields["title"])
        if any(self.token_frequency[token] <= self.rarity_limit for token in shared_title):
            return "discriminative-title-token"
        left_all = set().union(*(set(tokens) for tokens in left_fields.values()))
        right_all = set().union(*(set(tokens) for tokens in right_fields.values()))
        aligned_title = (set(left_fields["title"]) & right_all) | (
            set(right_fields["title"]) & left_all
        )
        if any(
            self.token_frequency[token] <= self.title_alignment_limit for token in aligned_title
        ):
            return "discriminative-title-alignment"

        for field in ("description", "acceptance_criteria", "design"):
            left_tokens = left_fields[field]
            right_tokens = right_fields[field]
            shared_phrases = _phrases(left_tokens) & _phrases(right_tokens)
            if any(self.phrase_frequency[phrase] <= self.rarity_limit for phrase in shared_phrases):
                return "discriminative-field-phrase"
        return None


_GENERIC_RECIPROCAL_TOKENS = {
    "add",
    "architecture",
    "api",
    "apis",
    "application",
    "behavior",
    "build",
    "change",
    "code",
    "component",
    "configure",
    "create",
    "data",
    "design",
    "ensure",
    "feature",
    "flow",
    "handling",
    "implement",
    "implementation",
    "improve",
    "infrastructure",
    "issue",
    "lifecycle",
    "module",
    "native",
    "new",
    "path",
    "process",
    "project",
    "resource",
    "runtime",
    "platform",
    "provide",
    "refactor",
    "service",
    "support",
    "state",
    "system",
    "task",
    "test",
    "update",
    "use",
    "workflow",
}


def _reciprocal_fields(issue: Any) -> dict[str, tuple[str, ...]]:
    return {
        field: tuple(
            token
            for token in re.findall(
                r"[a-z0-9][a-z0-9_-]{2,}",
                re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(getattr(issue, field, ""))).casefold(),
            )
            if token not in _GENERIC_RECIPROCAL_TOKENS
        )
        for field in ("title", "description", "acceptance_criteria", "design")
    }


def _phrases(tokens: Sequence[str]) -> set[str]:
    return {f"{left} {right}" for left, right in zip(tokens, tokens[1:], strict=False)}


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
    *,
    reference_qualified: Sequence[dict[str, Any]],
    conservative_qualified: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Explain stricter-threshold additions caused by bounded winner selection."""

    reference_keys = {_candidate_identity(item) for item in reference}
    conservative_keys = {_candidate_identity(item) for item in conservative}
    introduced = [item for item in conservative if _candidate_identity(item) not in reference_keys]
    displaced = [item for item in reference if _candidate_identity(item) not in conservative_keys]
    conservative_qualified_keys = {_candidate_identity(item) for item in conservative_qualified}
    removed_qualifications = [
        item
        for item in reference_qualified
        if _candidate_identity(item) not in conservative_qualified_keys
    ]
    diagnostics: list[dict[str, Any]] = []
    for candidate in introduced:
        cap = _governing_replacement_cap(candidate, reference, displaced, policy)
        if cap is None:
            continue
        related = [
            item
            for item in displaced
            if (
                cap == "max-candidates-per-issue"
                and item["lane"] != "dependency"
                and (
                    candidate["issue_id"] in (item["issue_id"], item["related_issue_id"])
                    or candidate["related_issue_id"] in (item["issue_id"], item["related_issue_id"])
                )
            )
            or (
                item["lane"] == candidate["lane"]
                and (
                    candidate["issue_id"] in (item["issue_id"], item["related_issue_id"])
                    or candidate["related_issue_id"] in (item["issue_id"], item["related_issue_id"])
                    or cap in {"run-cap", f"lane-cap:{candidate['lane']}"}
                )
            )
        ]
        chain = _replacement_chain(
            candidate,
            introduced,
            displaced,
            removed_qualifications,
            reference,
            policy,
            cap,
        )
        diagnostics.append(
            {
                "candidate_id": _candidate_id(candidate),
                "governing_cap": cap,
                "displaced_candidate_ids": sorted(_candidate_id(item) for item in related),
                "causal_chain": chain,
            }
        )
    return tuple(sorted(diagnostics, key=lambda item: item["candidate_id"]))


def _replacement_chain(
    candidate: dict[str, Any],
    introduced: Sequence[dict[str, Any]],
    displaced: Sequence[dict[str, Any]],
    removed: Sequence[dict[str, Any]],
    reference: Sequence[dict[str, Any]],
    policy: CandidatePolicy,
    governing_cap: str,
) -> list[dict[str, str]]:
    """Find a bounded resource path from a removed qualification to an admission."""

    by_key = {_candidate_identity(item): item for item in (*removed, *displaced, *introduced)}
    start = _candidate_identity(candidate)
    targets = {_candidate_identity(item) for item in removed}
    queue: list[tuple[str, str, str]] = [start]
    previous: dict[tuple[str, str, str], tuple[tuple[str, str, str], str] | None] = {start: None}
    found: tuple[str, str, str] | None = start if start in targets else None
    while queue and found is None:
        current = queue.pop(0)
        for neighbor in sorted(by_key):
            if neighbor in previous:
                continue
            resource = _shared_bounded_resource(
                by_key[current], by_key[neighbor], reference, policy
            )
            if resource is None:
                continue
            previous[neighbor] = (current, resource)
            if neighbor in targets:
                found = neighbor
                break
            queue.append(neighbor)

    if not removed:
        raise AssertionError("bounded replacement has no removed qualification")
    # A future cap type may lack a narrower graph edge. Retain a complete,
    # explicit governing-cap transition rather than an unexplained empty chain.
    if found is None:
        removed_item = min(removed, key=_candidate_id)
        resource = f"governing-cap:{governing_cap}"
        return [
            {
                "candidate_id": _candidate_id(removed_item),
                "event": "qualification-removed",
                "resource": resource,
            },
            {
                "candidate_id": _candidate_id(candidate),
                "event": "selection-admitted",
                "resource": resource,
            },
        ]

    path = [found]
    resources: list[str] = []
    while path[-1] != start:
        link = previous[path[-1]]
        assert link is not None
        parent, resource = link
        resources.append(resource)
        path.append(parent)
    resources.reverse()
    path.reverse()
    # The search runs admission -> removed qualification; report causality in
    # the reviewer-facing direction: qualification removal -> freed slots -> admission.
    path.reverse()
    resources.reverse()
    displaced_keys = {_candidate_identity(item) for item in displaced}
    introduced_keys = {_candidate_identity(item) for item in introduced}
    chain: list[dict[str, str]] = []
    for index, key in enumerate(path):
        event = (
            "qualification-removed"
            if index == 0
            else "selection-admitted"
            if key in introduced_keys
            else "selection-displaced"
            if key in displaced_keys
            else "selection-transition"
        )
        resource = resources[index] if index < len(resources) else resources[-1]
        chain.append(
            {"candidate_id": _candidate_id(by_key[key]), "event": event, "resource": resource}
        )
    return chain


def _shared_bounded_resource(
    left: dict[str, Any],
    right: dict[str, Any],
    reference: Sequence[dict[str, Any]],
    policy: CandidatePolicy,
) -> str | None:
    left_endpoints = {left["issue_id"], left["related_issue_id"]}
    right_endpoints = {right["issue_id"], right["related_issue_id"]}
    shared = sorted(left_endpoints & right_endpoints)
    same_dependency_budget = left["lane"] == right["lane"] == "dependency"
    same_semantic_budget = left["lane"] != "dependency" and right["lane"] != "dependency"
    if (same_dependency_budget or same_semantic_budget) and shared:
        lane = "dependency" if same_dependency_budget else "semantic"
        cap = policy.max_dependencies_per_issue if same_dependency_budget else policy.max_per_issue
        for endpoint in shared:
            count = sum(
                (
                    item["lane"] == "dependency"
                    if same_dependency_budget
                    else item["lane"] != "dependency"
                )
                and endpoint in (item["issue_id"], item["related_issue_id"])
                for item in reference
            )
            if count >= cap:
                return f"{lane}-issue:{endpoint}"
    if (
        left["kind"] == right["kind"] == "completed-work-echo"
        and left["issue_id"] == right["issue_id"]
    ):
        return f"one-echo:{left['issue_id']}"
    if left["lane"] == right["lane"]:
        lane = str(left["lane"])
        if sum(item["lane"] == lane for item in reference) >= policy.lane_caps[lane]:
            return f"lane:{lane}"
    if len(reference) >= policy.max_total:
        return "run"
    return None


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
    budgeted_reference = [
        item
        for item in reference
        if (item["lane"] == "dependency") == (candidate["lane"] == "dependency")
    ]
    if any(
        sum(endpoint in (item["issue_id"], item["related_issue_id"]) for item in budgeted_reference)
        >= cap
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
