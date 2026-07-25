"""Shadow-only comparison helpers for the experimental freshness policy.

This module deliberately has no CLI or report-schema wiring. It composes one
immutable candidate pool with privacy-safe relationship context so the policy
can be evaluated before it is eligible to change triage defaults.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .freshness_context import build_relationship_context_index
from .freshness_policy import (
    FreshnessRelationship,
    FreshnessRelationshipContext,
    classify_freshness,
)

SHADOW_POLICY_VERSION = 1
ACTIVE_STATUSES = frozenset({"open", "in_progress", "blocked", "deferred"})
_ACTION_PRIORITY = {
    "duplicate": 0,
    "superseded-open": 1,
    "missing-relation": 2,
    "uncertain": 3,
    "intentional-follow-up": 4,
}


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _issue_id(value: Any) -> str:
    return str(_field(value, "id", "") or "")


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    explicit = candidate.get("candidate_id")
    if explicit:
        return str(explicit)
    kind = str(candidate.get("kind") or "review-candidate")
    left = str(candidate.get("issue_id") or "")
    right = str(candidate.get("related_issue_id") or "")
    if not left or not right or left == right:
        raise ValueError("freshness candidates require two distinct issue endpoints")
    return f"{kind}|{left}|{right}"


def _relationship_context(
    left_id: str,
    right_id: str,
    *,
    index: Any,
    scope_complete: bool,
    structure_degraded: bool,
) -> FreshnessRelationshipContext:
    exact_edges = index.relationships_between(left_id, right_id)
    edges = {
        (edge.source_id, edge.target_id, edge.relationship_type): FreshnessRelationship(
            edge.source_id,
            edge.target_id,
            edge.relationship_type,
        )
        for edge in exact_edges
    }
    active_consumers = {
        endpoint_id
        for endpoint_id in (left_id, right_id)
        if index.has_active_incoming(
            endpoint_id,
            excluding=(left_id, right_id),
        )
    }
    return FreshnessRelationshipContext(
        relationships=tuple(edges[key] for key in sorted(edges)),
        active_incoming_consumers=frozenset(active_consumers),
        scope_complete=scope_complete,
        degraded=structure_degraded,
    )


def _context_receipt(index: Any, issue_id: str) -> dict[str, Any]:
    context = index.get(issue_id)
    if context is None:
        return {
            "issue_id": issue_id,
            "incoming": [],
            "outgoing": [],
            "omitted_incoming_count": 0,
            "omitted_outgoing_count": 0,
        }
    return context.as_dict()


def _fingerprint(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_freshness_shadow_packet(
    candidates: Sequence[Mapping[str, Any]],
    issues: Sequence[Any],
    *,
    relationship_scope_complete: bool = True,
    structure_degraded: bool = False,
    context_limit: int = 4,
) -> dict[str, Any]:
    """Compare legacy and freshness order from one fixed candidate sequence."""

    if context_limit < 1:
        raise ValueError("context_limit must be positive")
    issues_by_id = {_issue_id(issue): issue for issue in issues}
    if "" in issues_by_id or len(issues_by_id) != len(issues):
        raise ValueError("freshness evaluation requires unique non-empty issue IDs")

    fixed_pool: list[tuple[int, Mapping[str, Any], str, str, str]] = []
    seen: set[str] = set()
    candidate_pairs: list[tuple[str, str]] = []
    for legacy_position, candidate in enumerate(candidates, start=1):
        left_id = str(candidate.get("issue_id") or "")
        right_id = str(candidate.get("related_issue_id") or "")
        identifier = _candidate_id(candidate)
        if identifier in seen:
            raise ValueError(f"duplicate freshness candidate ID: {identifier}")
        if left_id not in issues_by_id or right_id not in issues_by_id:
            raise ValueError("freshness candidate endpoint is absent from the issue snapshot")
        seen.add(identifier)
        candidate_pairs.append((left_id, right_id))
        fixed_pool.append((legacy_position, candidate, identifier, left_id, right_id))

    index = build_relationship_context_index(
        issues,
        limit=context_limit,
        candidate_pairs=candidate_pairs,
    )
    assessed: list[dict[str, Any]] = []
    for legacy_position, candidate, identifier, left_id, right_id in fixed_pool:
        context = _relationship_context(
            left_id,
            right_id,
            index=index,
            scope_complete=relationship_scope_complete,
            structure_degraded=structure_degraded,
        )
        assessment = classify_freshness(
            issues_by_id[left_id],
            issues_by_id[right_id],
            candidate_evidence=candidate,
            relationship_context=context,
        )
        assessed.append(
            {
                "candidate_id": identifier,
                "issue_id": left_id,
                "related_issue_id": right_id,
                "legacy_position": legacy_position,
                "likely_action": assessment.likely_action,
                "review_tier": assessment.review_tier,
                "evidence_codes": list(assessment.evidence_codes),
            }
        )

    ranked = sorted(
        assessed,
        key=lambda item: (
            0 if item["review_tier"] == "action" else 1,
            _ACTION_PRIORITY[str(item["likely_action"])],
            int(item["legacy_position"]),
            str(item["candidate_id"]),
        ),
    )
    for position, item in enumerate(ranked, start=1):
        item["freshness_position"] = position

    top_10 = [str(item["candidate_id"]) for item in ranked[:10]]
    top_20 = [str(item["candidate_id"]) for item in ranked[:20]]
    action_counts = Counter(str(item["likely_action"]) for item in ranked)
    tier_counts = Counter(str(item["review_tier"]) for item in ranked)
    reviewed_endpoint_ids = {
        endpoint_id
        for item in ranked
        for endpoint_id in (str(item["issue_id"]), str(item["related_issue_id"]))
    }
    reviewed_contexts = [
        context
        for endpoint_id in sorted(reviewed_endpoint_ids)
        if (context := index.get(endpoint_id)) is not None
    ]
    stable = {
        "shadow_policy_version": SHADOW_POLICY_VERSION,
        "analysis_status": "degraded" if structure_degraded else "complete",
        "relationship_scope_complete": relationship_scope_complete,
        "context_limit": context_limit,
        "source_candidate_count": len(fixed_pool),
        "ranked_candidates": ranked,
        "relationship_contexts": [
            _context_receipt(index, endpoint_id) for endpoint_id in sorted(reviewed_endpoint_ids)
        ],
        "prefixes": {
            "top_10": top_10,
            "top_20": top_20,
            "top_10_is_strict_prefix_of_top_20": (
                len(top_20) > len(top_10) and top_20[: len(top_10)] == top_10
            ),
        },
        "summary": {
            "by_likely_action": dict(sorted(action_counts.items())),
            "by_review_tier": dict(sorted(tier_counts.items())),
            "reviewed_endpoint_count": len(reviewed_contexts),
            "omitted_relationship_context": sum(
                int(context.omitted_incoming_count) + int(context.omitted_outgoing_count)
                for context in reviewed_contexts
            ),
        },
        "evaluation_rubric": {
            "top_10": {
                "actionable_precision_target": 0.70,
                "useful_precision_target": 0.90,
                "category_accuracy_target": 0.90,
                "relationship_explained_false_concern_limit": 0,
            },
            "top_20": {
                "actionable_precision_target": 0.60,
                "useful_precision_target": 0.80,
                "category_accuracy_target": 0.80,
                "relationship_explained_false_concern_limit": 2,
            },
            "reviewer_minutes_limit": 25,
            "ratings": [
                "actionable",
                "useful",
                "likely_action_correct",
                "relationship_explained_false_concern",
                "reviewer_minutes",
            ],
        },
    }
    return {**stable, "shadow_fingerprint": _fingerprint(stable)}
