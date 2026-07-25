import json

import pytest

from embead.freshness_context import (
    RelationshipEdge,
    build_relationship_context_index,
)
from embead.models import DependencyLink, IssueRecord


def issue(
    identifier,
    *,
    status="open",
    parent_id=None,
    dependencies=(),
    links=(),
    title=None,
    description="",
):
    return IssueRecord(
        id=identifier,
        title=title or identifier,
        description=description,
        status=status,
        parent_id=parent_id,
        dependencies=dependencies,
        dependency_links=links,
    )


def test_preserves_reciprocal_multi_type_edges_and_deduplicates_exact_triples() -> None:
    issues = (
        issue(
            "A",
            links=(
                DependencyLink("A", "B", "blocks"),
                DependencyLink("A", "B", "blocks"),
                DependencyLink("A", "B", "custom-relation"),
            ),
        ),
        issue("B", links=(DependencyLink("B", "A", "blocks"),)),
    )

    index = build_relationship_context_index(issues)

    assert set(index["A"].outgoing) == {
        RelationshipEdge("A", "B", "blocks"),
        RelationshipEdge("A", "B", "custom-relation"),
    }
    assert index["A"].incoming == (RelationshipEdge("B", "A", "blocks"),)
    assert index["B"].incoming == (
        RelationshipEdge("A", "B", "blocks"),
        RelationshipEdge("A", "B", "custom-relation"),
    )
    assert index["B"].outgoing == (RelationshipEdge("B", "A", "blocks"),)


def test_normalizes_parent_without_duplicating_an_explicit_parent_edge() -> None:
    child = issue(
        "child",
        parent_id="parent",
        links=(DependencyLink("child", "parent", "parent-child"),),
    )

    index = build_relationship_context_index((child,))

    edge = RelationshipEdge("child", "parent", "parent-child")
    assert index["child"].outgoing == (edge,)
    assert index["parent"].incoming == (edge,)


def test_legacy_dependencies_do_not_invent_a_second_type_for_explicit_targets() -> None:
    source = issue(
        "source",
        dependencies=("typed-target", "legacy-target"),
        links=(DependencyLink("source", "typed-target", "blocks"),),
    )

    index = build_relationship_context_index((source,))

    assert set(index["source"].outgoing) == {
        RelationshipEdge("source", "typed-target", "blocks"),
        RelationshipEdge("source", "legacy-target", "depends-on"),
    }


def test_missing_endpoints_remain_indexed_with_bidirectional_evidence() -> None:
    source = issue(
        "known",
        links=(DependencyLink("known", "not-loaded", "vendor-specific"),),
    )

    index = build_relationship_context_index((source,))

    edge = RelationshipEdge("known", "not-loaded", "vendor-specific")
    assert index["known"].outgoing == (edge,)
    assert index["not-loaded"].incoming == (edge,)
    assert index["not-loaded"].outgoing == ()


def test_bounds_each_direction_and_reports_omitted_counts() -> None:
    center = issue(
        "center",
        links=tuple(DependencyLink("center", target, "relates-to") for target in "ABCDE"),
    )
    sources = tuple(
        issue(source, links=(DependencyLink(source, "center", "relates-to"),)) for source in "FGHIJ"
    )

    context = build_relationship_context_index((center, *sources), limit=2)["center"]

    assert [edge.target_id for edge in context.outgoing] == ["A", "B"]
    assert [edge.source_id for edge in context.incoming] == ["F", "G"]
    assert context.omitted_outgoing_count == 3
    assert context.omitted_incoming_count == 3


def test_exact_pair_lookup_survives_a_bounded_hub_without_expanding_receipts() -> None:
    center = issue(
        "center",
        links=tuple(
            DependencyLink("center", target, relationship_type)
            for target, relationship_type in (
                ("A", "blocks"),
                ("B", "blocks"),
                ("C", "relates-to"),
                ("D", "unknown"),
                ("E", "discovered-from"),
            )
        ),
    )

    index = build_relationship_context_index((center,), limit=2)

    assert [edge.target_id for edge in index["center"].outgoing] == ["A", "B"]
    expected = (RelationshipEdge("center", "E", "discovered-from"),)
    assert index.relationships_between("center", "E") == expected
    assert index.relationships_between("E", "center") == expected
    assert index.relationships_between("center", "absent") == ()
    assert index["center"].as_dict()["omitted_outgoing_count"] == 3
    assert "pair_edges" not in index.as_dict()


def test_active_incoming_fact_uses_the_full_unbounded_edge_set() -> None:
    sources = tuple(
        issue(source, links=(DependencyLink(source, "hub", "relates-to"),))
        for source in ("active-a", "active-b", "active-c")
    )
    closed = issue(
        "closed-source",
        status="closed",
        links=(DependencyLink("closed-source", "closed-only", "blocks"),),
    )

    index = build_relationship_context_index((*sources, closed), limit=1)

    assert len(index["hub"].incoming) == 1
    assert index["hub"].omitted_incoming_count == 2
    assert index.has_active_incoming("hub")
    assert not index.has_active_incoming(
        "hub",
        excluding=("active-a", "active-b", "active-c"),
    )
    assert not index.has_active_incoming("closed-only")
    assert not index.has_active_incoming("missing")


def test_ranking_prioritizes_counterpart_then_active_relation_priority_and_id() -> None:
    center = issue(
        "center",
        links=(
            DependencyLink("center", "closed-counterpart", "unknown"),
            DependencyLink("center", "active-z", "relates-to"),
            DependencyLink("center", "active-b", "blocks"),
            DependencyLink("center", "active-a", "blocks"),
            DependencyLink("center", "closed-a", "blocks"),
        ),
    )
    neighbors = (
        issue("closed-counterpart", status="closed"),
        issue("active-z"),
        issue("active-b"),
        issue("active-a"),
        issue("closed-a", status="closed"),
    )

    context = build_relationship_context_index(
        (center, *neighbors),
        limit=4,
        candidate_pairs=(("center", "closed-counterpart"),),
    )["center"]

    assert [edge.target_id for edge in context.outgoing] == [
        "closed-counterpart",
        "active-a",
        "active-b",
        "active-z",
    ]
    assert context.omitted_outgoing_count == 1


def test_output_is_privacy_safe() -> None:
    private = issue(
        "private-id",
        title="PRIVATE TITLE",
        description="PRIVATE BODY /private/source.py code snippet",
        links=(DependencyLink("private-id", "other-id", "blocks"),),
    )

    encoded = json.dumps(build_relationship_context_index((private,)).as_dict(), sort_keys=True)

    assert "private-id" in encoded
    assert "PRIVATE TITLE" not in encoded
    assert "PRIVATE BODY" not in encoded
    assert "/private/source.py" not in encoded
    assert "code snippet" not in encoded


def test_mapping_inputs_and_shuffled_edges_are_byte_deterministic() -> None:
    first = {
        "id": "A",
        "status": "open",
        "title": "must not leak",
        "dependency_links": [
            {"source_id": "A", "target_id": "C", "relationship_type": "unknown-z"},
            {"source_id": "A", "target_id": "B", "relationship_type": "blocks"},
        ],
    }
    second = {"id": "B", "status": "closed", "dependency_links": []}
    third = {"id": "C", "status": "open", "dependency_links": []}
    shuffled_first = {
        **first,
        "dependency_links": list(reversed(first["dependency_links"])),
    }

    left = build_relationship_context_index(
        (first, second, third),
        candidate_pairs=(("C", "A"),),
    ).as_dict()
    right = build_relationship_context_index(
        (third, second, shuffled_first),
        candidate_pairs=(("A", "C"),),
    ).as_dict()

    assert left == right
    assert json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right,
        sort_keys=True,
        separators=(",", ":"),
    )


def test_rejects_invalid_bounds_duplicate_ids_and_malformed_pairs() -> None:
    with pytest.raises(ValueError, match="limit must be positive"):
        build_relationship_context_index((), limit=0)
    with pytest.raises(ValueError, match="issue IDs must be unique"):
        build_relationship_context_index((issue("A"), issue("A")))
    with pytest.raises(ValueError, match="exactly two"):
        build_relationship_context_index((issue("A"),), candidate_pairs=(("A",),))
