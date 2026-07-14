from embead.models import IssueRecord
from embead.ranking import CandidatePolicy, rank_candidates


class Scores:
    def __init__(self, values):
        self.values = {frozenset(pair): score for pair, score in values.items()}

    def score(self, left_id, right_id):
        if left_id == right_id:
            return 1.0
        return self.values.get(frozenset((left_id, right_id)), 0.0)


def issue(identifier, *, status="open", parent=None, dependencies=()):
    return IssueRecord(
        id=identifier,
        title=identifier,
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
    ):
        try:
            rank_candidates(issues, issues, Scores({}), bad_policy)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid candidate policy was accepted")
