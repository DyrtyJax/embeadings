from __future__ import annotations

import json

import pytest

from embead.freshness_evaluation import build_freshness_shadow_packet
from embead.models import DependencyLink, IssueRecord


def issue(
    identifier: str,
    title: str,
    *,
    status: str = "open",
    description: str = "",
    links: tuple[DependencyLink, ...] = (),
) -> IssueRecord:
    return IssueRecord(
        id=identifier,
        title=title,
        status=status,
        description=description,
        dependency_links=links,
    )


def candidate(left: str, right: str, *, kind: str = "possible-overlap") -> dict[str, object]:
    return {
        "candidate_id": f"{kind}|{left}|{right}",
        "kind": kind,
        "issue_id": left,
        "related_issue_id": right,
        "similarity": 0.99,
    }


def test_shadow_packet_ranks_actions_without_changing_the_fixed_pool() -> None:
    issues = (
        issue("A", "Repair cache invalidation"),
        issue("B", "Repair cache invalidation"),
        issue(
            "C",
            "Run release checklist",
            links=(DependencyLink("C", "D", "blocks"),),
        ),
        issue("D", "Ship release"),
    )
    pool = (candidate("C", "D"), candidate("A", "B"))

    packet = build_freshness_shadow_packet(pool, issues)

    assert packet["source_candidate_count"] == 2
    assert [item["candidate_id"] for item in packet["ranked_candidates"]] == [
        "possible-overlap|A|B",
        "possible-overlap|C|D",
    ]
    assert packet["ranked_candidates"][0]["likely_action"] == "duplicate"
    assert packet["ranked_candidates"][1]["likely_action"] == "intentional-follow-up"
    assert packet["ranked_candidates"][1]["review_tier"] == "informational"
    assert packet["prefixes"]["top_10_is_strict_prefix_of_top_20"] is False
    assert {item["legacy_position"] for item in packet["ranked_candidates"]} == {1, 2}
    assert packet["summary"]["reviewed_endpoint_count"] == 4


def test_reverse_active_consumer_is_bounded_counterevidence() -> None:
    issues = (
        issue("A", "Incident cleanup", status="closed"),
        issue("B", "Incident cleanup checklist"),
        issue(
            "C",
            "Ship follow-up",
            links=(DependencyLink("C", "B", "blocks"),),
        ),
    )

    packet = build_freshness_shadow_packet(
        (candidate("B", "A", kind="completed-work-echo"),),
        issues,
    )

    item = packet["ranked_candidates"][0]
    assert item["likely_action"] == "intentional-follow-up"
    assert item["review_tier"] == "informational"
    context_by_id = {context["issue_id"]: context for context in packet["relationship_contexts"]}
    incoming = context_by_id["B"]["incoming"]
    assert incoming == [
        {
            "source_id": "C",
            "target_id": "B",
            "type": "blocks",
        }
    ]


def test_candidate_counterpart_is_not_mistaken_for_a_third_party_consumer() -> None:
    issues = (
        issue(
            "A",
            "Alpha",
            links=(DependencyLink("A", "B", "relates-to"),),
        ),
        issue("B", "Beta"),
    )

    packet = build_freshness_shadow_packet((candidate("A", "B"),), issues)

    assert packet["ranked_candidates"][0]["likely_action"] == "uncertain"
    assert packet["ranked_candidates"][0]["review_tier"] == "informational"


def test_degraded_structure_is_explicit_and_suppresses_missing_relation() -> None:
    issues = (
        issue("A", "Implement parser", description="Blocked by B."),
        issue("B", "Land tokenizer"),
    )

    packet = build_freshness_shadow_packet(
        (candidate("A", "B"),),
        issues,
        relationship_scope_complete=True,
        structure_degraded=True,
    )

    assert packet["analysis_status"] == "degraded"
    assert packet["ranked_candidates"][0]["likely_action"] == "uncertain"
    assert "missing-relation" not in packet["summary"]["by_likely_action"]


def test_packet_is_deterministic_and_contains_no_issue_text() -> None:
    private = "PRIVATE SENTENCE THAT MUST NOT LEAK"
    issues = (
        issue("A", "Alpha", description=private),
        issue("B", "Beta", description=f"{private}; blocked by A"),
    )
    pool = (candidate("A", "B"),)

    first = build_freshness_shadow_packet(pool, issues)
    second = build_freshness_shadow_packet(pool, issues)
    rendered = json.dumps(first, sort_keys=True)

    assert first == second
    assert private not in rendered
    assert first["shadow_fingerprint"] == second["shadow_fingerprint"]
    assert first["evaluation_rubric"]["top_10"]["actionable_precision_target"] == 0.70


def test_top_10_is_a_strict_prefix_of_top_20_when_the_pool_is_large_enough() -> None:
    issues = tuple(issue(f"I-{index}", f"Distinct work {index}") for index in range(40))
    pool = tuple(candidate(f"I-{index}", f"I-{index + 20}") for index in range(20))

    packet = build_freshness_shadow_packet(pool, issues)

    assert len(packet["prefixes"]["top_10"]) == 10
    assert len(packet["prefixes"]["top_20"]) == 20
    assert packet["prefixes"]["top_10_is_strict_prefix_of_top_20"] is True


def test_fixed_pool_rejects_duplicates_and_unknown_endpoints() -> None:
    issues = (issue("A", "Alpha"), issue("B", "Beta"))
    duplicate = candidate("A", "B")

    with pytest.raises(ValueError, match="duplicate freshness candidate"):
        build_freshness_shadow_packet((duplicate, duplicate), issues)
    with pytest.raises(ValueError, match="absent"):
        build_freshness_shadow_packet((candidate("A", "C"),), issues)
