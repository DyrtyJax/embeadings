"""Conservative, privacy-safe policy for the shadow freshness experiment.

This module deliberately contains no queue construction, CLI, or report
integration.  It classifies one already-discovered pair and emits only a
finite vocabulary of evidence codes.  Tracker text is inspected locally and
is never copied into the result.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

LikelyAction = Literal[
    "duplicate",
    "superseded-open",
    "missing-relation",
    "intentional-follow-up",
    "uncertain",
]
ReviewTier = Literal["action", "informational"]

_CLOSED_STATUSES = frozenset({"closed", "done", "completed", "resolved"})
_EXPLANATORY_RELATIONSHIPS = frozenset({"parent-child", "blocks", "depends-on", "discovered-from"})
# Historical and administrative notes are intentionally excluded. They can
# mention old relationships that no longer describe the current work.
_TEXT_FIELDS = ("title", "description", "acceptance_criteria", "design")
_TEXT_FIELD_LIMIT = 4_096
_REFERENCE_WINDOW = 96
_REFERENCE_CUE = re.compile(
    r"""
    \b(?:
        after
        |before
        |block(?:ed|er|ers|ing|s)?(?:\s+by)?
        |build(?:s|ing)?\s+on
        |continu(?:ation|e|ed|es|ing)
        |depend(?:s|ed|ing)?\s+on
        |discover(?:ed)?\s+from
        |follow[\s-]?up
        |relat(?:e|ed|es|ing|ion|ionship)
        |supersed(?:e|ed|es|ing)
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_EVIDENCE_ORDER = (
    "direct-parent-child",
    "direct-blocks",
    "direct-depends-on",
    "direct-discovered-from",
    "active-incoming-consumer",
    "explicit-issue-id-reference",
    "bounded-relationship-cue",
    "relationship-scope-complete",
    "relationship-scope-incomplete",
    "relationship-scope-degraded",
    "no-direct-explanatory-relationship",
    "exact-normalized-title",
    "lifecycle-active-active",
    "lifecycle-active-closed",
    "lifecycle-unknown",
    "semantic-candidate-only",
    "no-actionable-evidence",
)
_EVIDENCE_POSITION = {code: index for index, code in enumerate(_EVIDENCE_ORDER)}


@dataclass(frozen=True, slots=True)
class FreshnessRelationship:
    """One typed, directed relationship visible to the shadow policy."""

    source_id: str
    target_id: str
    relationship_type: str


class RelationshipContextProtocol(Protocol):
    """Bounded structural facts available while classifying a pair."""

    relationships: Sequence[Any]
    active_incoming_consumers: Collection[str]
    scope_complete: bool
    degraded: bool


@dataclass(frozen=True, slots=True)
class FreshnessRelationshipContext:
    """Default immutable implementation of :class:`RelationshipContextProtocol`."""

    relationships: tuple[FreshnessRelationship, ...] = ()
    active_incoming_consumers: frozenset[str] = field(default_factory=frozenset)
    scope_complete: bool = True
    degraded: bool = False


@dataclass(frozen=True, slots=True)
class FreshnessAssessment:
    """Privacy-safe output of the shadow freshness policy."""

    likely_action: LikelyAction
    review_tier: ReviewTier
    evidence_codes: tuple[str, ...]


def classify_freshness(
    left: Any,
    right: Any,
    candidate_evidence: Mapping[str, Any] | None = None,
    relationship_context: RelationshipContextProtocol | None = None,
) -> FreshnessAssessment:
    """Classify one candidate pair without returning tracker text.

    Structural counterevidence wins over title identity because a known
    hierarchy or delivery relationship usually explains why two issues look
    alike.  Missing-relation findings require complete, non-degraded
    relationship scope; semantic similarity alone is always informational.
    """

    context = relationship_context or FreshnessRelationshipContext()
    left_id = _issue_id(left)
    right_id = _issue_id(right)
    relationship_codes = _direct_relationship_codes(left, right, context)
    incoming_consumer = bool(
        {left_id, right_id} & {str(identifier) for identifier in context.active_incoming_consumers}
    )
    if incoming_consumer:
        relationship_codes.add("active-incoming-consumer")

    scope_codes = {
        "relationship-scope-complete"
        if context.scope_complete and not context.degraded
        else "relationship-scope-incomplete"
    }
    if context.degraded:
        scope_codes.add("relationship-scope-degraded")

    left_title = _normalized_title(left)
    right_title = _normalized_title(right)
    exact_title = bool(left_title) and left_title == right_title
    lifecycle = _pair_lifecycle(left, right)
    references_with_cue = _references_with_bounded_cue(left, right_id) or (
        _references_with_bounded_cue(right, left_id)
    )
    semantic_candidate = _has_semantic_candidate_evidence(candidate_evidence)

    if relationship_codes:
        return _assessment(
            "intentional-follow-up",
            "informational",
            relationship_codes | scope_codes,
        )

    if references_with_cue and context.scope_complete and not context.degraded:
        return _assessment(
            "missing-relation",
            "action",
            {
                "explicit-issue-id-reference",
                "bounded-relationship-cue",
                "relationship-scope-complete",
                "no-direct-explanatory-relationship",
            },
        )

    common_codes = set(scope_codes)
    if references_with_cue:
        common_codes.update(
            {
                "explicit-issue-id-reference",
                "bounded-relationship-cue",
            }
        )
    if exact_title:
        common_codes.add("exact-normalized-title")
        if lifecycle == "active-active":
            common_codes.add("lifecycle-active-active")
            return _assessment("duplicate", "action", common_codes)
        if lifecycle == "active-closed":
            common_codes.add("lifecycle-active-closed")
            return _assessment("superseded-open", "action", common_codes)
        common_codes.add("lifecycle-unknown")

    if semantic_candidate:
        common_codes.add("semantic-candidate-only")
    if not exact_title and not references_with_cue:
        common_codes.add("no-actionable-evidence")
    return _assessment("uncertain", "informational", common_codes)


def _assessment(
    likely_action: LikelyAction,
    review_tier: ReviewTier,
    evidence_codes: Collection[str],
) -> FreshnessAssessment:
    unknown = set(evidence_codes) - set(_EVIDENCE_ORDER)
    if unknown:  # Defensive invariant: outputs must stay in a finite vocabulary.
        raise ValueError(f"unknown freshness evidence code: {min(unknown)}")
    return FreshnessAssessment(
        likely_action=likely_action,
        review_tier=review_tier,
        evidence_codes=tuple(
            sorted(set(evidence_codes), key=lambda code: _EVIDENCE_POSITION[code])
        ),
    )


def _direct_relationship_codes(
    left: Any,
    right: Any,
    context: RelationshipContextProtocol,
) -> set[str]:
    left_id = _issue_id(left)
    right_id = _issue_id(right)
    codes: set[str] = set()
    if _field(left, "parent_id", None) == right_id or _field(right, "parent_id", None) == left_id:
        codes.add("direct-parent-child")

    endpoints = {left_id, right_id}
    for relationship in context.relationships:
        source_id = str(_field(relationship, "source_id", ""))
        target_id = str(_field(relationship, "target_id", ""))
        if {source_id, target_id} != endpoints:
            continue
        relationship_type = _normalize_relationship_type(
            str(_field(relationship, "relationship_type", ""))
        )
        if relationship_type in _EXPLANATORY_RELATIONSHIPS:
            codes.add(f"direct-{relationship_type}")
    return codes


def _references_with_bounded_cue(issue: Any, target_id: str) -> bool:
    if not target_id:
        return False
    identifier = re.escape(target_id)
    boundary = re.compile(
        rf"(?<![A-Za-z0-9_.-]){identifier}(?![A-Za-z0-9_-]|\.[A-Za-z0-9])",
        re.IGNORECASE,
    )
    for field_name in _TEXT_FIELDS:
        text = str(_field(issue, field_name, ""))[:_TEXT_FIELD_LIMIT]
        for match in boundary.finditer(text):
            start = max(0, match.start() - _REFERENCE_WINDOW)
            end = min(len(text), match.end() + _REFERENCE_WINDOW)
            if _REFERENCE_CUE.search(text[start:end]):
                return True
    return False


def _normalized_title(issue: Any) -> str:
    title = unicodedata.normalize("NFKC", str(_field(issue, "title", ""))).casefold()
    return " ".join(re.findall(r"[^\W_]+", title, flags=re.UNICODE))


def _pair_lifecycle(left: Any, right: Any) -> str:
    states = (_lifecycle(left), _lifecycle(right))
    if states == ("active", "active"):
        return "active-active"
    if set(states) == {"active", "closed"}:
        return "active-closed"
    return "unknown"


def _lifecycle(issue: Any) -> str:
    status = str(_field(issue, "status", "")).strip().casefold()
    if not status:
        return "unknown"
    return "closed" if status in _CLOSED_STATUSES else "active"


def _has_semantic_candidate_evidence(candidate_evidence: Mapping[str, Any] | None) -> bool:
    if not candidate_evidence:
        return False
    if isinstance(candidate_evidence.get("similarity"), (int, float)):
        return True
    lane = str(candidate_evidence.get("lane", "")).casefold()
    kind = str(candidate_evidence.get("kind", "")).casefold()
    return lane in {"echo", "overlap"} or kind in {
        "completed-work-echo",
        "possible-overlap",
    }


def _normalize_relationship_type(value: str) -> str:
    return value.strip().casefold().replace("_", "-").replace(" ", "-")


def _issue_id(issue: Any) -> str:
    value = _field(issue, "id", _field(issue, "issue_id", None))
    if value is None or not str(value):
        raise ValueError("issue must have a non-empty id or issue_id")
    return str(value)


def _field(item: Any, name: str, default: Any) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)
