import json
import subprocess

from embead.beads import BeadsAdapter
from embead.models import DependencyLink, IssueRecord
from embead.ranking import CandidatePolicy, rank_candidates


class Scores:
    def __init__(self, values):
        self.values = {frozenset(pair): score for pair, score in values.items()}

    def score(self, left_id, right_id):
        if left_id == right_id:
            return 1.0
        return self.values.get(frozenset((left_id, right_id)), 0.0)


def issue(
    identifier,
    *,
    status="open",
    parent=None,
    dependencies=(),
    title=None,
    description="",
):
    return IssueRecord(
        id=identifier,
        title=title or identifier,
        description=description,
        status=status,
        parent_id=parent,
        dependencies=dependencies,
    )


def policy(**overrides):
    values = {
        "echo_threshold": 0.8,
        "overlap_threshold": 0.8,
        "exception_margin": 0.1,
        "reciprocal_rank": 0,
        "max_per_issue": 3,
        "max_total": 20,
    }
    values.update(overrides)
    return CandidatePolicy(**values)


def test_shared_parent_admits_bounded_threshold_exception() -> None:
    issues = [issue("A", parent="P"), issue("B", parent="P")]

    result = rank_candidates(issues, issues, Scores({("A", "B"): 0.75}), policy())

    assert len(result.candidates) == 1
    assert result.candidates[0]["admission_reason"] == "shared-parent-threshold-exception"
    assert result.candidates[0]["structural_context"] == "same parent P"
    assert result.candidates[0]["candidate_evidence"] == {
        "evidence_basis": "structurally-corroborated",
        "structural_corroboration": "shared-parent",
        "admission_path": "shared-parent-threshold-exception",
        "uncertainty": "structural-corroboration-recorded",
    }


def test_dependency_admits_bounded_threshold_exception() -> None:
    issues = [issue("A", dependencies=("B",)), issue("B")]

    result = rank_candidates(issues, issues, Scores({("A", "B"): 0.71}), policy())

    assert result.candidates[0]["admission_reason"] == "dependency-threshold-exception"
    assert result.candidates[0]["candidate_evidence"]["structural_corroboration"] == (
        "typed-dependency"
    )


def test_direct_and_reciprocal_semantic_candidates_expose_no_structural_corroboration() -> None:
    issues = [
        issue("A", title="Cache report", description="Preserve report checksum evidence"),
        issue("B", title="Cache report", description="Preserve report checksum evidence"),
    ]
    direct = rank_candidates(issues, issues, Scores({("A", "B"): 0.85}), policy())
    reciprocal = rank_candidates(
        issues,
        issues,
        Scores({("A", "B"): 0.75}),
        policy(reciprocal_rank=1),
    )

    assert direct.candidates[0]["candidate_evidence"] == {
        "evidence_basis": "semantic-only",
        "structural_corroboration": "none",
        "admission_path": "semantic-threshold",
        "uncertainty": "no-structural-corroboration",
    }
    assert reciprocal.candidates[0]["candidate_evidence"]["admission_path"] == (
        "reciprocal-neighbor-threshold-exception"
    )
    assert reciprocal.candidates[0]["candidate_evidence"]["uncertainty"] == (
        "no-structural-corroboration"
    )


def test_typed_dependency_preserves_direction_and_type_in_context() -> None:
    issues = [
        IssueRecord(
            id="A",
            title="A",
            status="open",
            dependencies=("B",),
            dependency_links=(DependencyLink("A", "B", "blocks"),),
        ),
        issue("B"),
    ]
    result = rank_candidates(
        issues,
        issues,
        Scores({("A", "B"): 0.78}),
        CandidatePolicy(overlap_threshold=0.82, exception_margin=0.08),
    )
    assert result.candidates[0]["structural_context"] == "A depends on B (blocks)"
    assert result.candidates[0]["dependency_evidence"] == {
        "source_id": "A",
        "target_id": "B",
        "type": "blocks",
    }
    assert result.candidates[0]["admission_reason"] == "dependency-threshold-exception"


def test_typed_dependency_takes_precedence_over_shared_parent_context() -> None:
    issues = [
        IssueRecord(
            id="A",
            title="A",
            status="open",
            parent_id="P",
            dependency_links=(DependencyLink("A", "B", "blocks"),),
        ),
        issue("B", parent="P"),
    ]

    result = rank_candidates(issues, issues, Scores({("A", "B"): 0.75}), policy())

    assert result.candidates[0]["lane"] == "dependency"
    assert result.candidates[0]["structural_context"] == "A depends on B (blocks)"


def test_current_beads_payload_routes_typed_dependency_to_protected_lane() -> None:
    payload = [
        {
            "id": "source",
            "title": "Source",
            "status": "open",
            "dependencies": [{"issue_id": "source", "depends_on_id": "target", "type": "blocks"}],
        },
        {"id": "target", "title": "Target", "status": "open", "dependencies": []},
    ]

    def runner(argv):
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    issues = BeadsAdapter(runner=runner).list_issues()
    result = rank_candidates(
        issues,
        issues,
        Scores({("source", "target"): 0.75}),
        policy(),
    )

    assert result.candidates[0]["lane"] == "dependency"
    assert result.candidates[0]["dependency_evidence"]["target_id"] == "target"
    assert result.lanes["dependency"].admitted == 1


def test_typed_parent_child_link_does_not_enable_dependency_exception() -> None:
    issues = [
        IssueRecord(
            id="A",
            title="A",
            status="open",
            dependencies=("B",),
            dependency_links=(DependencyLink("A", "B", "parent-child"),),
        ),
        issue("B"),
    ]
    result = rank_candidates(
        issues,
        issues,
        Scores({("A", "B"): 0.78}),
        CandidatePolicy(overlap_threshold=0.82, exception_margin=0.08, reciprocal_rank=0),
    )
    assert result.candidates == ()


def test_parent_child_is_counterevidence_not_an_exception() -> None:
    below = [issue("A"), issue("B", parent="A")]
    assert not rank_candidates(below, below, Scores({("A", "B"): 0.79}), policy()).candidates

    above = rank_candidates(below, below, Scores({("A", "B"): 0.85}), policy()).candidates[0]
    assert above["admission_reason"] == "semantic-threshold"
    assert "parent/child scope" in above["counterevidence"]


def test_reciprocal_neighbor_rank_admits_exception() -> None:
    issues = [
        issue("A", description="Preserve the checksum contract"),
        issue("B", description="Verify the checksum contract"),
        issue("C"),
    ]
    scores = Scores({("A", "B"): 0.75, ("A", "C"): 0.2, ("B", "C"): 0.1})

    result = rank_candidates(issues, issues, scores, policy(reciprocal_rank=1))

    assert len(result.candidates) == 1
    assert result.candidates[0]["admission_reason"] == ("reciprocal-neighbor-threshold-exception")
    assert result.candidates[0]["reciprocal_ranks"] == {"issue": 1, "related_issue": 1}
    assert result.reciprocal_diagnostics == {
        "admitted": 1,
        "omitted": 0,
        "admission_reasons": {"discriminative-field-phrase": 1},
        "omission_reasons": {},
    }


def test_caps_are_deterministic_and_apply_to_both_endpoints() -> None:
    issues = [issue(identifier) for identifier in "DCBA"]
    pairs = (
        ("A", "B"),
        ("A", "C"),
        ("A", "D"),
        ("B", "C"),
        ("B", "D"),
        ("C", "D"),
    )
    scores = Scores({pair: 0.9 for pair in pairs})

    result = rank_candidates(
        issues,
        issues,
        scores,
        policy(overlap_threshold=-1, max_per_issue=1, max_total=10),
    )

    assert [(item["issue_id"], item["related_issue_id"]) for item in result.candidates] == [
        ("A", "B"),
        ("C", "D"),
    ]
    assert result.qualified == 6
    assert result.dropped_by_issue_cap == 4


def test_permissive_threshold_is_still_bounded_by_run_cap() -> None:
    issues = [issue(identifier) for identifier in "ABCDE"]

    result = rank_candidates(
        issues,
        issues,
        Scores({}),
        policy(overlap_threshold=-1, max_per_issue=10, max_total=2),
    )

    assert len(result.candidates) == 2
    assert result.qualified == 10
    assert result.dropped_by_run_cap == 8


def test_completed_echo_keeps_only_best_eligible_closed_record() -> None:
    active = issue("A")
    closed_b = issue("B", status="closed")
    closed_c = issue("C", status="closed")
    scores = Scores({("A", "B"): 0.9, ("A", "C"): 0.85})

    result = rank_candidates([active], [active, closed_c, closed_b], scores, policy())

    assert len(result.candidates) == 1
    assert result.candidates[0]["kind"] == "completed-work-echo"
    assert result.candidates[0]["related_issue_id"] == "B"


def test_policy_rejects_unbounded_or_invalid_controls() -> None:
    issues = [issue("A")]
    for bad_policy in (
        policy(max_total=0),
        policy(max_per_issue=0),
        policy(reciprocal_rank=-1),
        policy(exception_margin=-0.1),
        policy(max_dependencies=-1),
        policy(max_dependencies_per_issue=-1),
    ):
        try:
            rank_candidates(issues, issues, Scores({}), bad_policy)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid candidate policy was accepted")


def test_dependency_lane_is_admitted_before_semantic_candidates() -> None:
    issues = [issue("A", dependencies=("B",)), issue("B"), issue("C"), issue("D")]
    scores = Scores({("A", "B"): 0.81, ("C", "D"): 0.99})

    result = rank_candidates(
        issues,
        issues,
        scores,
        policy(max_total=1, max_per_issue=3),
    )

    assert [(item["issue_id"], item["related_issue_id"]) for item in result.candidates] == [
        ("A", "B")
    ]
    assert result.candidates[0]["lane"] == "dependency"
    assert result.lanes["dependency"].admitted == 1
    assert result.lanes["overlap"].dropped_by_run_cap == 1


def test_high_confidence_echo_is_admitted_before_overlap_under_total_budget() -> None:
    active = [issue("A"), issue("B"), issue("C")]
    closed = issue("Z", status="closed")
    scores = Scores({("A", "Z"): 0.9, ("B", "C"): 0.99})

    result = rank_candidates(
        active,
        [*active, closed],
        scores,
        policy(max_total=1, max_per_issue=3),
    )

    assert len(result.candidates) == 1
    assert result.candidates[0]["kind"] == "completed-work-echo"
    assert result.candidates[0]["admission_reason"] == "semantic-threshold"
    assert result.lanes["echo"].admitted == 1
    assert result.lanes["overlap"].dropped_by_run_cap == 1


def test_lane_budgets_are_independent_and_report_drops() -> None:
    active = [
        issue("A", dependencies=("B",)),
        issue("B"),
        issue("C"),
        issue("D"),
    ]
    closed = issue("Z", status="closed")
    scores = Scores({("A", "B"): 0.9, ("C", "D"): 0.9, ("C", "Z"): 0.95})

    result = rank_candidates(
        active,
        [*active, closed],
        scores,
        policy(max_dependencies=1, max_echoes=1, max_overlaps=0, max_total=10),
    )

    assert [item["lane"] for item in result.candidates] == ["dependency", "echo"]
    assert result.lanes["overlap"].qualified == 1
    assert result.lanes["overlap"].dropped_by_lane_cap == 1
    assert result.dropped_by_lane_cap == 1


def test_multiple_completed_dependency_edges_are_not_collapsed_into_one_echo() -> None:
    active = issue("A", dependencies=("X", "Y"))
    closed = [issue("X", status="closed"), issue("Y", status="closed")]
    scores = Scores({("A", "X"): 0.81, ("A", "Y"): 0.82})

    result = rank_candidates(
        [active],
        [active, *closed],
        scores,
        policy(max_dependencies=5, max_echoes=5, max_per_issue=3),
    )

    assert {
        (item["issue_id"], item["related_issue_id"], item["lane"]) for item in result.candidates
    } == {("A", "X", "dependency"), ("A", "Y", "dependency")}


def test_dependency_per_issue_allowance_is_independent_and_summarizes_capped_edges() -> None:
    """Reproduce the observed dependency-hub loss at a small 3-of-5 scale."""

    hub = IssueRecord(
        id="A",
        title="dependency hub",
        status="open",
        dependency_links=tuple(DependencyLink("A", target, "blocks") for target in "BCDEF"),
    )
    issues = [hub, *(issue(identifier) for identifier in "BCDEFG")]
    scores = Scores(
        {
            **{("A", target): 0.9 - index / 100 for index, target in enumerate("BCDEF")},
            ("A", "G"): 0.99,
        }
    )

    result = rank_candidates(
        issues,
        issues,
        scores,
        policy(
            max_per_issue=1,
            max_dependencies_per_issue=2,
            max_dependencies=10,
            max_overlaps=10,
        ),
    )

    assert [item["lane"] for item in result.candidates].count("dependency") == 2
    assert any(item["lane"] == "overlap" and item["issue_id"] == "A" for item in result.candidates)
    assert result.lanes["dependency"].dropped_by_dependency_issue_cap == 3
    assert result.dropped_by_dependency_issue_cap == 3
    assert result.capped_typed_dependencies == (
        {
            "source_id": "A",
            "target_id": "D",
            "type": "blocks",
            "drop_reason": "dependency-per-issue-cap",
        },
        {
            "source_id": "A",
            "target_id": "E",
            "type": "blocks",
            "drop_reason": "dependency-per-issue-cap",
        },
        {
            "source_id": "A",
            "target_id": "F",
            "type": "blocks",
            "drop_reason": "dependency-per-issue-cap",
        },
    )


def test_all_typed_dependency_cap_reasons_are_summarized() -> None:
    issues = [issue("A", dependencies=("B", "C")), issue("B"), issue("C")]
    result = rank_candidates(
        issues,
        issues,
        Scores({("A", "B"): 0.9, ("A", "C"): 0.8}),
        policy(max_dependencies=1, max_dependencies_per_issue=5),
    )

    assert result.capped_typed_dependencies == (
        {
            "source_id": "A",
            "target_id": "C",
            "type": "depends-on",
            "drop_reason": "lane-cap",
        },
    )

    run_capped = rank_candidates(
        issues,
        issues,
        Scores({("A", "B"): 0.9, ("A", "C"): 0.8}),
        policy(max_total=1, max_dependencies=5, max_dependencies_per_issue=5),
    )
    assert run_capped.capped_typed_dependencies[0]["drop_reason"] == "run-cap"
    assert result.dependency_funnel.omitted_by_lane_cap == 1
    assert run_capped.dependency_funnel.omitted_by_run_cap == 1


def test_dependency_funnel_zero_structure_is_explicit_and_conserved() -> None:
    issues = [issue("A"), issue("B", status="closed")]

    result = rank_candidates(issues[:1], issues, Scores({}), policy())

    assert result.dependency_funnel.total_non_parent_typed == 0
    assert result.dependency_funnel.inactive_or_closed_only == 0
    assert result.dependency_funnel.eligible == 0
    result.dependency_funnel.validate()


def test_dependency_funnel_identifies_closed_only_structure() -> None:
    issues = [
        IssueRecord(
            id="A",
            title="A",
            status="closed",
            dependency_links=(DependencyLink("A", "B", "blocks"),),
        ),
        IssueRecord(
            id="B",
            title="B",
            status="closed",
            dependency_links=(DependencyLink("B", "C", "relates-to"),),
        ),
        IssueRecord(
            id="C",
            title="C",
            status="closed",
            dependency_links=(DependencyLink("C", "A", "discovered-from"),),
        ),
        issue("D"),
    ]

    result = rank_candidates([issues[-1]], issues, Scores({}), policy())

    assert result.dependency_funnel.total_non_parent_typed == 3
    assert result.dependency_funnel.inactive_or_closed_only == 3
    assert result.dependency_funnel.below_qualification == 0
    assert result.dependency_funnel.eligible == 0
    result.dependency_funnel.validate()


def test_dependency_funnel_reconciles_rich_structure_without_endpoints() -> None:
    hub = IssueRecord(
        id="A",
        title="A",
        status="open",
        dependency_links=tuple(
            DependencyLink("A", target, "blocks") for target in ("B", "C", "D", "E")
        ),
    )
    closed_source = IssueRecord(
        id="X",
        title="X",
        status="closed",
        dependency_links=(DependencyLink("X", "Y", "blocks"),),
    )
    issues = [
        hub,
        *(issue(identifier) for identifier in "BCDE"),
        closed_source,
        issue("Y", status="closed"),
    ]

    result = rank_candidates(
        issues[:5],
        issues,
        Scores(
            {
                ("A", "B"): 0.90,
                ("A", "C"): 0.85,
                ("A", "D"): 0.75,
                ("A", "E"): 0.60,
            }
        ),
        policy(max_dependencies_per_issue=1),
    )

    funnel = result.dependency_funnel
    assert funnel.total_non_parent_typed == 5
    assert funnel.inactive_or_closed_only == 1
    assert funnel.below_qualification == 1
    assert funnel.eligible == 3
    assert funnel.admitted == 1
    assert funnel.omitted_by_per_issue_cap == 2
    assert not hasattr(funnel, "source_id")
    funnel.validate()


def test_sensitivity_run_preserves_baseline_queue_under_caps() -> None:
    issues = [issue(identifier) for identifier in "ABCD"]
    scores = Scores({("A", "B"): 0.9, ("C", "D"): 0.7})
    baseline_policy = policy(max_total=1, max_per_issue=3)
    sensitivity_policy = policy(overlap_threshold=0.65, max_total=1, max_per_issue=3)

    baseline = rank_candidates(issues, issues, scores, baseline_policy)
    sensitivity = rank_candidates(issues, issues, scores, sensitivity_policy)

    baseline_ids = {
        (item["kind"], item["issue_id"], item["related_issue_id"]) for item in baseline.candidates
    }
    sensitivity_ids = {
        (item["kind"], item["issue_id"], item["related_issue_id"])
        for item in sensitivity.candidates
    }
    assert baseline_ids <= sensitivity_ids
    assert sensitivity.baseline_protected == 1
    assert sensitivity.candidates[0]["baseline_protected"] is True


def test_generic_vocabulary_only_reciprocal_candidate_is_rejected() -> None:
    issues = [
        issue("A", title="architecture workflow", description="update system lifecycle"),
        issue("B", title="architecture workflow", description="change system lifecycle"),
        issue("C", title="red"),
        issue("D", title="blue"),
    ]
    scores = Scores({("A", "B"): 0.76, ("C", "D"): 0.81})

    result = rank_candidates(
        issues,
        issues,
        scores,
        policy(reciprocal_rank=1, max_total=1, max_per_issue=3),
    )

    assert (result.candidates[0]["issue_id"], result.candidates[0]["related_issue_id"]) == (
        "C",
        "D",
    )
    assert result.candidates[0]["signal_quality"] == "semantic"
    assert result.reciprocal_diagnostics["omission_reasons"] == {
        "no-discriminative-local-evidence": 1
    }


def test_long_broad_descriptions_do_not_qualify_reciprocal_exception() -> None:
    issues = [
        issue(
            "A", title="First path", description="Support resource handling across runtime platform"
        ),
        issue(
            "B", title="Second path", description="Improve resource handling for runtime platform"
        ),
        issue("C", title="Unrelated"),
    ]

    result = rank_candidates(
        issues,
        issues,
        Scores({("A", "B"): 0.76}),
        policy(reciprocal_rank=1),
    )

    assert result.candidates == ()
    assert result.reciprocal_diagnostics["omission_reasons"] == {
        "no-discriminative-local-evidence": 1
    }


def test_sparse_title_led_pair_qualifies_with_redacted_reason_category() -> None:
    issues = [
        issue("A", title="Delta parser"),
        issue("B", title="Delta validation"),
        issue("C", title="Unrelated"),
    ]

    result = rank_candidates(
        issues,
        issues,
        Scores({("A", "B"): 0.76}),
        policy(reciprocal_rank=1),
    )

    assert len(result.candidates) == 1
    assert result.candidates[0]["reciprocal_evidence"] == "discriminative-title-token"
    assert "delta" not in json.dumps(result.reciprocal_diagnostics)


def test_title_entity_aligned_to_description_preserves_sparse_subsystem_pair() -> None:
    issues = [
        issue("A", title="Add command palette", description="Open it inside the Chat interface"),
        issue("B", title="ChatView paste handling", status="closed"),
        issue("C", title="Unrelated"),
    ]

    result = rank_candidates(
        [issues[0], issues[2]],
        issues,
        Scores({("A", "B"): 0.76}),
        policy(reciprocal_rank=1),
    )

    assert len(result.candidates) == 1
    assert result.candidates[0]["reciprocal_evidence"] == "discriminative-title-alignment"


def test_sparse_empty_body_title_pair_uses_narrow_fallback() -> None:
    issues = [
        issue("A", title="Define task execution engine", description="Run configured actions"),
        issue("B", title="Implement direct task reference", status="closed"),
        issue("C", title="Unrelated"),
    ]

    result = rank_candidates(
        [issues[0], issues[2]],
        issues,
        Scores({("A", "B"): 0.76}),
        policy(reciprocal_rank=1),
    )

    assert len(result.candidates) == 1
    assert result.candidates[0]["reciprocal_evidence"] == "sparse-title-alignment"


def test_corpus_common_title_token_is_not_discriminative() -> None:
    issues = [
        issue("A", title="Parser alpha"),
        issue("B", title="Parser beta"),
        issue("C", title="Parser gamma"),
        issue("D", title="Parser theta"),
        issue("E", title="Other epsilon"),
        issue("F", title="Other zeta"),
    ]

    result = rank_candidates(
        issues,
        issues,
        Scores({("A", "B"): 0.76}),
        policy(reciprocal_rank=1),
    )

    assert result.candidates == ()


def test_conservative_threshold_reports_cap_driven_replacement() -> None:
    issues = [
        issue("A", description="architecture lifecycle"),
        issue("B", description="architecture lifecycle"),
        issue("C", description="preserve checksum contract"),
        issue("D", description="validate checksum contract"),
    ]
    scores = Scores({("A", "B"): 0.81, ("C", "D"): 0.805})

    result = rank_candidates(
        issues,
        issues,
        scores,
        policy(
            overlap_threshold=0.82,
            baseline_overlap_threshold=0.8,
            reciprocal_rank=1,
            max_total=1,
        ),
    )

    assert [(item["issue_id"], item["related_issue_id"]) for item in result.candidates] == [
        ("C", "D")
    ]
    assert result.cap_replacements == (
        {
            "candidate_id": "possible-overlap|C|D",
            "governing_cap": "run-cap",
            "displaced_candidate_ids": ["possible-overlap|A|B"],
            "causal_chain": [
                {
                    "candidate_id": "possible-overlap|A|B",
                    "event": "qualification-removed",
                    "resource": "run",
                },
                {
                    "candidate_id": "possible-overlap|C|D",
                    "event": "selection-admitted",
                    "resource": "run",
                },
            ],
        },
    )


def test_cross_lane_cap_replacement_has_complete_causal_chain() -> None:
    active = [issue("A"), issue("B")]
    closed = issue("X", status="closed")
    scores = Scores({("A", "X"): 0.81, ("A", "B"): 0.805})

    result = rank_candidates(
        active,
        [*active, closed],
        scores,
        policy(
            echo_threshold=0.82,
            baseline_echo_threshold=0.8,
            overlap_threshold=0.8,
            baseline_overlap_threshold=0.8,
            max_per_issue=1,
        ),
    )

    identities = [
        (item["kind"], item["issue_id"], item["related_issue_id"]) for item in result.candidates
    ]
    assert identities == [("possible-overlap", "A", "B")]
    assert result.cap_replacements == (
        {
            "candidate_id": "possible-overlap|A|B",
            "governing_cap": "max-candidates-per-issue",
            "displaced_candidate_ids": ["completed-work-echo|A|X"],
            "causal_chain": [
                {
                    "candidate_id": "completed-work-echo|A|X",
                    "event": "qualification-removed",
                    "resource": "semantic-issue:A",
                },
                {
                    "candidate_id": "possible-overlap|A|B",
                    "event": "selection-admitted",
                    "resource": "semantic-issue:A",
                },
            ],
        },
    )


def test_incremental_eligibility_filters_before_caps_but_keeps_unchanged_context() -> None:
    issues = [issue(identifier) for identifier in "ABC"]
    scores = Scores({("A", "B"): 0.95, ("B", "C"): 0.94, ("A", "C"): 0.93})

    result = rank_candidates(
        issues,
        issues,
        scores,
        policy(max_total=10, max_per_issue=3),
        eligible_issue_ids=frozenset({"C"}),
    )

    assert {(item["issue_id"], item["related_issue_id"]) for item in result.candidates} == {
        ("A", "C"),
        ("B", "C"),
    }
