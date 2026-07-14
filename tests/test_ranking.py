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


def test_dependency_admits_bounded_threshold_exception() -> None:
    issues = [issue("A", dependencies=("B",)), issue("B")]

    result = rank_candidates(issues, issues, Scores({("A", "B"): 0.71}), policy())

    assert result.candidates[0]["admission_reason"] == "dependency-threshold-exception"


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
    issues = [issue("A"), issue("B"), issue("C")]
    scores = Scores({("A", "B"): 0.75, ("A", "C"): 0.2, ("B", "C"): 0.1})

    result = rank_candidates(issues, issues, scores, policy(reciprocal_rank=1))

    assert len(result.candidates) == 1
    assert result.candidates[0]["admission_reason"] == ("reciprocal-neighbor-threshold-exception")
    assert result.candidates[0]["reciprocal_ranks"] == {"issue": 1, "related_issue": 1}


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


def test_vocabulary_only_reciprocal_candidate_is_demoted() -> None:
    issues = [
        issue("A", title="generic cache"),
        issue("B", title="generic cache"),
        issue("C", title="red"),
        issue("D", title="blue"),
    ]
    scores = Scores({("A", "B"): 0.76, ("C", "D"): 0.75})

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
