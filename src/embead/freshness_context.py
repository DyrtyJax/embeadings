"""Bounded, privacy-safe relationship context for freshness review.

The index deliberately retains only tracker identifiers, relationship types,
and omission counts. It never reads semantic issue fields, so callers cannot
accidentally place titles, bodies, paths, or snippets in a freshness artifact.
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from .analysis import issue_id, issue_status

DEFAULT_RELATIONSHIP_LIMIT: Final[int] = 4
CLOSED_STATUSES: Final[frozenset[str]] = frozenset(
    {"closed", "done", "completed", "resolved", "canceled", "cancelled", "duplicate"}
)
RELATIONSHIP_PRIORITY: Final[tuple[str, ...]] = (
    "blocks",
    "depends-on",
    "duplicate-of",
    "parent-child",
    "discovered-from",
    "relates-to",
    "similar-to",
)
_RELATIONSHIP_RANK: Final[dict[str, int]] = {
    relationship_type: rank for rank, relationship_type in enumerate(RELATIONSHIP_PRIORITY)
}


@dataclass(frozen=True, slots=True)
class RelationshipEdge:
    """One typed, directed edge without semantic tracker content."""

    source_id: str
    target_id: str
    relationship_type: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.relationship_type,
        }


@dataclass(frozen=True, slots=True)
class IssueRelationshipContext:
    """Bounded incoming and outgoing structural context for one endpoint."""

    issue_id: str
    incoming: tuple[RelationshipEdge, ...] = ()
    outgoing: tuple[RelationshipEdge, ...] = ()
    omitted_incoming_count: int = 0
    omitted_outgoing_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "incoming": [edge.as_dict() for edge in self.incoming],
            "outgoing": [edge.as_dict() for edge in self.outgoing],
            "omitted_incoming_count": self.omitted_incoming_count,
            "omitted_outgoing_count": self.omitted_outgoing_count,
        }


class RelationshipContextIndex:
    """Immutable-by-convention lookup for deterministic endpoint context."""

    __slots__ = ("_active_incoming", "_by_id", "_contexts", "_pair_edges", "limit")

    def __init__(
        self,
        contexts: Iterable[IssueRelationshipContext],
        *,
        limit: int,
        pair_edges: Mapping[tuple[str, str], tuple[RelationshipEdge, ...]] | None = None,
        active_incoming: Mapping[str, frozenset[str]] | None = None,
    ) -> None:
        ordered = tuple(sorted(contexts, key=lambda context: context.issue_id))
        self._contexts = ordered
        self._by_id = {context.issue_id: context for context in ordered}
        self._pair_edges = dict(pair_edges or {})
        self._active_incoming = dict(active_incoming or {})
        self.limit = limit

    @property
    def contexts(self) -> tuple[IssueRelationshipContext, ...]:
        return self._contexts

    def __getitem__(self, identifier: str) -> IssueRelationshipContext:
        return self._by_id[identifier]

    def get(self, identifier: str) -> IssueRelationshipContext | None:
        return self._by_id.get(identifier)

    def relationships_between(
        self,
        left_id: str,
        right_id: str,
    ) -> tuple[RelationshipEdge, ...]:
        """Return every direct typed edge between two IDs, in either direction."""

        return self._pair_edges.get(_pair_key(left_id, right_id), ())

    def has_active_incoming(
        self,
        identifier: str,
        *,
        excluding: Iterable[str] = (),
    ) -> bool:
        """Return whether an unexcluded loaded active issue points to ``identifier``."""

        return bool(self._active_incoming.get(identifier, frozenset()) - set(excluding))

    def as_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "issues": [context.as_dict() for context in self._contexts],
        }


def build_relationship_context_index(
    issues: Iterable[Any],
    *,
    limit: int = DEFAULT_RELATIONSHIP_LIMIT,
    candidate_pairs: Iterable[tuple[str, str]] = (),
) -> RelationshipContextIndex:
    """Build bounded bidirectional context in O(V + E) for fixed ``limit``.

    Exact directed/type triples are deduplicated. ``parent_id`` contributes a
    normalized ``parent-child`` edge only when that exact triple is absent.
    Missing endpoints remain in the index with unknown activity, preserving
    boundary evidence without fetching or exposing additional tracker fields.

    Candidate pairs are optional ranking hints. When an endpoint is directly
    related to a supplied counterpart, that edge survives before other active
    neighbors, known relationship priorities, and identifier tie-breakers.
    """

    if limit < 1:
        raise ValueError("relationship context limit must be positive")

    records = tuple(issues)
    statuses: dict[str, str | None] = {}
    record_ids: set[str] = set()
    for record in records:
        identifier = issue_id(record)
        if identifier in record_ids:
            raise ValueError("relationship context issue IDs must be unique")
        record_ids.add(identifier)
        statuses[identifier] = issue_status(record)

    counterparts = _candidate_counterparts(candidate_pairs)
    edges: set[RelationshipEdge] = set()
    for record in records:
        owner_id = issue_id(record)
        explicit_targets: set[str] = set()
        for raw_link in tuple(_field(record, "dependency_links", ()) or ()):
            edge = _relationship_edge(raw_link, default_source_id=owner_id)
            edges.add(edge)
            explicit_targets.add(edge.target_id)

        # ``dependencies`` is retained for older IssueRecord-like inputs. Real
        # adapters populate it alongside typed links, so it is only a fallback
        # when no explicit type exists for that target.
        for raw_target in tuple(_field(record, "dependencies", ()) or ()):
            target_id = _identifier(raw_target, subject="dependency target")
            if target_id not in explicit_targets:
                edges.add(RelationshipEdge(owner_id, target_id, "depends-on"))

        parent = _field(record, "parent_id", None)
        if parent is not None:
            parent_id = _identifier(parent, subject="parent")
            edges.add(RelationshipEdge(owner_id, parent_id, "parent-child"))

    incoming: dict[str, list[RelationshipEdge]] = defaultdict(list)
    outgoing: dict[str, list[RelationshipEdge]] = defaultdict(list)
    pair_edges: dict[tuple[str, str], list[RelationshipEdge]] = defaultdict(list)
    active_incoming: dict[str, set[str]] = defaultdict(set)
    endpoint_ids = set(record_ids)
    for edge in edges:
        outgoing[edge.source_id].append(edge)
        incoming[edge.target_id].append(edge)
        pair_edges[_pair_key(edge.source_id, edge.target_id)].append(edge)
        if _is_active(edge.source_id, statuses):
            active_incoming[edge.target_id].add(edge.source_id)
        endpoint_ids.add(edge.source_id)
        endpoint_ids.add(edge.target_id)

    contexts: list[IssueRelationshipContext] = []
    for identifier in endpoint_ids:
        retained_incoming = _bounded_edges(
            incoming[identifier],
            endpoint_id=identifier,
            direction="incoming",
            limit=limit,
            statuses=statuses,
            counterparts=counterparts,
        )
        retained_outgoing = _bounded_edges(
            outgoing[identifier],
            endpoint_id=identifier,
            direction="outgoing",
            limit=limit,
            statuses=statuses,
            counterparts=counterparts,
        )
        contexts.append(
            IssueRelationshipContext(
                issue_id=identifier,
                incoming=retained_incoming,
                outgoing=retained_outgoing,
                omitted_incoming_count=len(incoming[identifier]) - len(retained_incoming),
                omitted_outgoing_count=len(outgoing[identifier]) - len(retained_outgoing),
            )
        )
    ordered_pair_edges = {
        pair: tuple(
            sorted(
                related,
                key=lambda edge: (edge.source_id, edge.target_id, edge.relationship_type),
            )
        )
        for pair, related in pair_edges.items()
    }
    return RelationshipContextIndex(
        contexts,
        limit=limit,
        pair_edges=ordered_pair_edges,
        active_incoming={
            target_id: frozenset(source_ids) for target_id, source_ids in active_incoming.items()
        },
    )


def _candidate_counterparts(
    candidate_pairs: Iterable[tuple[str, str]],
) -> dict[str, frozenset[str]]:
    mutable: dict[str, set[str]] = defaultdict(set)
    for pair in candidate_pairs:
        try:
            left, right = pair
        except (TypeError, ValueError) as exc:
            raise ValueError("candidate pairs must contain exactly two issue IDs") from exc
        left_id = _identifier(left, subject="candidate endpoint")
        right_id = _identifier(right, subject="candidate endpoint")
        mutable[left_id].add(right_id)
        mutable[right_id].add(left_id)
    return {identifier: frozenset(values) for identifier, values in mutable.items()}


def _relationship_edge(raw_link: Any, *, default_source_id: str) -> RelationshipEdge:
    source = _field(raw_link, "source_id", default_source_id)
    target = _field(raw_link, "target_id", None)
    relationship_type = _field(raw_link, "relationship_type", None)
    return RelationshipEdge(
        source_id=_identifier(source, subject="relationship source"),
        target_id=_identifier(target, subject="relationship target"),
        relationship_type=_identifier(relationship_type, subject="relationship type"),
    )


def _bounded_edges(
    edges: list[RelationshipEdge],
    *,
    endpoint_id: str,
    direction: str,
    limit: int,
    statuses: Mapping[str, str | None],
    counterparts: Mapping[str, frozenset[str]],
) -> tuple[RelationshipEdge, ...]:
    def key(edge: RelationshipEdge) -> tuple[int, int, int, str, str, str, str]:
        neighbor_id = edge.source_id if direction == "incoming" else edge.target_id
        relation_key = edge.relationship_type.casefold()
        return (
            int(neighbor_id not in counterparts.get(endpoint_id, ())),
            int(not _is_active(neighbor_id, statuses)),
            _RELATIONSHIP_RANK.get(relation_key, len(_RELATIONSHIP_RANK)),
            neighbor_id,
            edge.source_id,
            edge.target_id,
            edge.relationship_type,
        )

    # ``limit`` is intentionally small (four by default), making this a
    # bounded O(E log limit) selection and therefore linear for fixed policy.
    return tuple(heapq.nsmallest(limit, edges, key=key))


def _is_active(identifier: str, statuses: Mapping[str, str | None]) -> bool:
    if identifier not in statuses:
        return False
    status = statuses[identifier]
    return status is None or status.casefold() not in CLOSED_STATUSES


def _pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    return (left_id, right_id) if left_id <= right_id else (right_id, left_id)


def _identifier(value: Any, *, subject: str) -> str:
    if value is None:
        raise ValueError(f"{subject} must be a non-empty string")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{subject} must be a non-empty string")
    return normalized


def _field(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)
