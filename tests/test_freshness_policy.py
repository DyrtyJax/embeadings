from dataclasses import asdict

import pytest

from embead.freshness_policy import (
    FreshnessRelationship,
    FreshnessRelationshipContext,
    classify_freshness,
)
from embead.models import IssueRecord


def issue(
    identifier: str,
    title: str,
    *,
    status: str = "open",
    description: str = "",
    parent_id: str | None = None,
    notes: str = "",
    acceptance_criteria: str = "",
    design: str = "",
) -> IssueRecord:
    return IssueRecord(
        id=identifier,
        title=title,
        status=status,
        description=description,
        parent_id=parent_id,
        notes=notes,
        acceptance_criteria=acceptance_criteria,
        design=design,
    )


def test_exact_normalized_active_titles_are_an_actionable_duplicate() -> None:
    left = issue("PRJ-1", "Add: Unicode café command")
    right = issue("PRJ-2", "  ADD unicode cafe\u0301 command! ")

    result = classify_freshness(left, right)

    assert result.likely_action == "duplicate"
    assert result.review_tier == "action"
    assert result.evidence_codes == (
        "relationship-scope-complete",
        "exact-normalized-title",
        "lifecycle-active-active",
    )


def test_exact_active_closed_identity_is_a_superseded_open_candidate() -> None:
    left = issue("PRJ-1", "Repair parser invariant")
    right = issue("PRJ-2", "repair parser invariant", status="closed")

    result = classify_freshness(left, right, {"kind": "completed-work-echo"})

    assert result.likely_action == "superseded-open"
    assert result.review_tier == "action"
    assert "lifecycle-active-closed" in result.evidence_codes


def test_cosine_alone_does_not_confuse_command_argument_with_command_palette() -> None:
    left = issue("PRJ-1", "Build command argument parser")
    right = issue("PRJ-2", "Add command palette keyboard shortcut")

    result = classify_freshness(
        left,
        right,
        {"kind": "possible-overlap", "similarity": 0.99},
    )

    assert result.likely_action == "uncertain"
    assert result.review_tier == "informational"
    assert result.evidence_codes == (
        "relationship-scope-complete",
        "candidate-possible-overlap",
        "semantic-candidate-only",
        "no-actionable-evidence",
    )


@pytest.mark.parametrize(
    ("relationship_type", "evidence_code"),
    [
        ("parent-child", "direct-parent-child"),
        ("blocks", "direct-blocks"),
        ("depends-on", "direct-depends-on"),
        ("discovered-from", "direct-discovered-from"),
    ],
)
def test_direct_explanatory_relation_is_informational_counterevidence(
    relationship_type: str,
    evidence_code: str,
) -> None:
    left = issue("PRJ-1", "Repair parser invariant")
    right = issue("PRJ-2", "Repair parser invariant")
    context = FreshnessRelationshipContext(
        relationships=(FreshnessRelationship("PRJ-1", "PRJ-2", relationship_type),),
    )

    result = classify_freshness(left, right, relationship_context=context)

    assert result.likely_action == "intentional-follow-up"
    assert result.review_tier == "informational"
    assert evidence_code in result.evidence_codes
    assert "exact-normalized-title" not in result.evidence_codes


def test_depends_on_edge_prevents_a_false_missing_relation_action() -> None:
    left = issue(
        "PRJ-1",
        "Complete adapter",
        description="Follow-up to PRJ-248: preserve its parser invariant.",
    )
    right = issue("PRJ-248", "Repair parser invariant")
    context = FreshnessRelationshipContext(
        relationships=(FreshnessRelationship("PRJ-1", "PRJ-248", "depends_on"),),
    )

    result = classify_freshness(left, right, relationship_context=context)

    assert result.likely_action == "intentional-follow-up"
    assert result.review_tier == "informational"
    assert "direct-depends-on" in result.evidence_codes
    assert "no-direct-explanatory-relationship" not in result.evidence_codes


def test_parent_id_is_direct_parent_child_counterevidence() -> None:
    parent = issue("PRJ-1", "Parser work")
    child = issue("PRJ-2", "Parser work", parent_id="PRJ-1")

    result = classify_freshness(parent, child)

    assert result.likely_action == "intentional-follow-up"
    assert result.evidence_codes[0] == "direct-parent-child"


def test_active_incoming_consumer_is_informational_counterevidence() -> None:
    left = issue("PRJ-1", "Publish parser contract", status="closed")
    right = issue("PRJ-2", "Consume parser contract")
    context = FreshnessRelationshipContext(
        active_incoming_consumers=frozenset({"PRJ-1"}),
    )

    result = classify_freshness(left, right, relationship_context=context)

    assert result.likely_action == "intentional-follow-up"
    assert result.review_tier == "informational"
    assert result.evidence_codes[0] == "active-incoming-consumer"


def test_exact_reference_and_bounded_cue_can_flag_a_missing_relation() -> None:
    left = issue(
        "PRJ-1",
        "Complete adapter",
        description="Follow-up to PRJ-248: preserve its parser invariant.",
    )
    right = issue("PRJ-248", "Repair parser invariant", status="closed")

    result = classify_freshness(left, right)

    assert result.likely_action == "missing-relation"
    assert result.review_tier == "action"
    assert result.evidence_codes == (
        "explicit-issue-id-reference",
        "bounded-relationship-cue",
        "relationship-scope-complete",
        "no-direct-explanatory-relationship",
    )


@pytest.mark.parametrize(
    ("field_name", "text"),
    [
        ("description", "Decision from PRJ-248: keep the parser invariant."),
        ("acceptance_criteria", "Split from PRJ-248; preserve the adapter contract."),
        ("design", "PRJ-248 re-review found a second convergence hazard."),
        ("description", "Found by re-review of PRJ-248 during the audit."),
        ("acceptance_criteria", "PRJ-248 removed the old guard but left retry uncovered."),
        ("design", "From PRJ-248 adversarial review, retain the fail-closed check."),
    ],
)
def test_audited_lineage_cues_flag_missing_relation(
    field_name: str,
    text: str,
) -> None:
    kwargs = {field_name: text}
    left = issue("PRJ-1", "Complete adapter", **kwargs)
    right = issue("PRJ-248", "Prior parser work", status="closed")

    result = classify_freshness(left, right)

    assert result.likely_action == "missing-relation"
    assert result.review_tier == "action"
    assert "explicit-issue-id-reference" in result.evidence_codes
    assert "bounded-relationship-cue" in result.evidence_codes


@pytest.mark.parametrize(
    "text",
    [
        "Copied an example from PRJ-248.",
        "See PRJ-248 for the decision table.",
        "PRJ-248 was reviewed yesterday.",
        "Adversarial review guidance is documented in PRJ-248.",
        "Removed PRJ-248 from the inventory but retained the documentation.",
        "The re-review process is documented elsewhere. PRJ-248 is merely cited.",
        "The split-fromage example PRJ-248 is a coincidental substring.",
        "The plan builds PRJ-248 on an unrelated example.",
    ],
)
def test_generic_reference_language_does_not_create_lineage_action(text: str) -> None:
    left = issue("PRJ-1", "Complete adapter", description=text)
    right = issue("PRJ-248", "Prior parser work", status="closed")

    result = classify_freshness(left, right)

    assert result.likely_action == "uncertain"
    assert "explicit-issue-id-reference" not in result.evidence_codes


@pytest.mark.parametrize(
    ("left_status", "right_status", "candidate_evidence", "expected_codes"),
    [
        (
            "open",
            "open",
            {
                "kind": "possible-overlap",
                "admission_reason": "semantic-threshold",
                "similarity": 0.91,
            },
            {"candidate-possible-overlap", "semantic-threshold-admission"},
        ),
        (
            "open",
            "open",
            {
                "kind": "possible-overlap",
                "admission_reason": "reciprocal-neighbor-threshold-exception",
                "signal_quality": "discriminative-local-evidence",
                "reciprocal_evidence": "discriminative-field-phrase",
            },
            {"candidate-possible-overlap", "reciprocal-local-evidence"},
        ),
        (
            "open",
            "closed",
            {
                "kind": "completed-work-echo",
                "admission_reason": "semantic-threshold",
                "similarity": 0.89,
            },
            {"candidate-completed-work-echo", "semantic-threshold-admission"},
        ),
        (
            "open",
            "closed",
            {
                "kind": "completed-work-echo",
                "admission_reason": "semantic-threshold",
                "similarity": 0.84,
            },
            {"candidate-completed-work-echo", "semantic-threshold-admission"},
        ),
    ],
)
def test_audited_actionable_uncertainty_signatures_remain_informational_without_contract_evidence(
    left_status: str,
    right_status: str,
    candidate_evidence: dict[str, object],
    expected_codes: set[str],
) -> None:
    left = issue("PRJ-1", "Specific implementation work", status=left_status)
    right = issue("PRJ-2", "Related subsystem work", status=right_status)

    result = classify_freshness(left, right, candidate_evidence)

    assert result.likely_action == "uncertain"
    assert result.review_tier == "informational"
    assert expected_codes <= set(result.evidence_codes)
    assert "no-actionable-evidence" in result.evidence_codes


@pytest.mark.parametrize(
    "candidate_evidence",
    [
        {
            "kind": "possible-overlap",
            "admission_reason": "semantic-threshold",
            "similarity": 0.99,
        },
        {
            "kind": "possible-overlap",
            "admission_reason": "reciprocal-neighbor-threshold-exception",
            "signal_quality": "semantic",
            "reciprocal_evidence": "unbounded-private-phrase",
        },
        {
            "kind": "completed-work-echo",
            "admission_reason": "semantic-threshold",
            "similarity": 0.95,
        },
    ],
)
def test_uncertainty_receipts_do_not_promote_semantic_hard_negatives(
    candidate_evidence: dict[str, object],
) -> None:
    left = issue("PRJ-1", "Command argument builder")
    right = issue("PRJ-2", "Command palette shortcut")

    result = classify_freshness(left, right, candidate_evidence)

    assert result.likely_action == "uncertain"
    assert result.review_tier == "informational"
    assert "semantic-candidate-only" in result.evidence_codes
    assert "reciprocal-local-evidence" not in result.evidence_codes or (
        candidate_evidence.get("signal_quality") == "discriminative-local-evidence"
    )


@pytest.mark.parametrize(
    "context",
    [
        FreshnessRelationshipContext(scope_complete=False),
        FreshnessRelationshipContext(scope_complete=True, degraded=True),
    ],
)
def test_incomplete_or_degraded_structure_suppresses_absence_based_conclusions(
    context: FreshnessRelationshipContext,
) -> None:
    left = issue("PRJ-1", "Complete adapter", description="Follow-up to PRJ-248.")
    right = issue("PRJ-248", "Repair parser invariant", status="closed")

    result = classify_freshness(left, right, relationship_context=context)

    assert result.likely_action == "uncertain"
    assert result.review_tier == "informational"
    assert "explicit-issue-id-reference" in result.evidence_codes
    assert "relationship-scope-complete" not in result.evidence_codes


def test_reference_requires_exact_id_boundary_and_bounded_relationship_cue() -> None:
    referenced = issue(
        "PRJ-1",
        "Complete adapter",
        description="Inspect PRJ-2480. " + ("x" * 120) + " Follow-up work.",
    )
    target = issue("PRJ-248", "Repair parser invariant")

    result = classify_freshness(referenced, target)

    assert result.likely_action == "uncertain"
    assert "explicit-issue-id-reference" not in result.evidence_codes


def test_historical_notes_do_not_create_a_missing_relation_action() -> None:
    left = issue(
        "PRJ-1",
        "Complete adapter",
        notes="Historical follow-up to PRJ-248 before the scope changed.",
    )
    right = issue("PRJ-248", "Repair parser invariant")

    result = classify_freshness(left, right)

    assert result.likely_action == "uncertain"
    assert "explicit-issue-id-reference" not in result.evidence_codes


def test_unknown_lifecycle_does_not_promote_exact_identity() -> None:
    left = issue("PRJ-1", "Repair parser invariant", status="")
    right = issue("PRJ-2", "Repair parser invariant")

    result = classify_freshness(left, right)

    assert result.likely_action == "uncertain"
    assert "lifecycle-unknown" in result.evidence_codes


def test_empty_titles_are_not_identity_evidence_for_duck_typed_inputs() -> None:
    result = classify_freshness(
        {"id": "PRJ-1", "title": "", "status": "open"},
        {"id": "PRJ-2", "title": "", "status": "open"},
    )

    assert result.likely_action == "uncertain"
    assert "exact-normalized-title" not in result.evidence_codes


def test_output_is_finite_deterministic_and_contains_no_tracker_text_or_ids() -> None:
    secret = "customer-secret-purple-otter"
    left = issue(
        "PRIVATE-991",
        f"Repair {secret}",
        description=f"Follow-up to PRIVATE-992 for {secret}.",
    )
    right = issue("PRIVATE-992", f"Different {secret}", status="closed")

    first = classify_freshness(left, right, {"similarity": 0.987654})
    second = classify_freshness(left, right, {"similarity": 0.987654})
    serialized = repr(asdict(first))

    assert first == second
    assert secret not in serialized
    assert "PRIVATE-991" not in serialized
    assert "PRIVATE-992" not in serialized
    assert set(asdict(first)) == {"likely_action", "review_tier", "evidence_codes"}
