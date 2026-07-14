from dataclasses import dataclass

import pytest

from embead.analysis import (
    SimilarityIndex,
    balanced_batches,
    candidate_batches,
    cosine_similarity,
    nearest_neighbors,
)


@dataclass
class Issue:
    id: str
    status: str = "open"


def test_cosine_similarity_normalizes_and_validates() -> None:
    assert cosine_similarity([2, 0], [4, 0]) == pytest.approx(1)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0)
    with pytest.raises(ValueError):
        cosine_similarity([1], [1, 2])


def test_similarity_index_matches_scalar_cosine_and_ranks_ties_by_id() -> None:
    vectors = {"Q": [2, 0], "B": [1, 1], "A": [1, 1], "C": [0, 3]}
    index = SimilarityIndex(vectors)

    assert index.ids == ("A", "B", "C", "Q")
    assert index.score("Q", "B") == pytest.approx(cosine_similarity([2, 0], [1, 1]))
    assert index.ranked("Q", ["C", "B", "A"]) == [
        ("A", pytest.approx(2**-0.5)),
        ("B", pytest.approx(2**-0.5)),
        ("C", pytest.approx(0)),
    ]


@pytest.mark.parametrize(
    ("vectors", "message"),
    [
        ({"A": [1], "B": [1, 2]}, "same dimension"),
        ({"A": [0, 0]}, "zero vector"),
        ({"A": [float("nan"), 1]}, "finite"),
    ],
)
def test_similarity_index_rejects_malformed_vectors(vectors, message) -> None:
    with pytest.raises(ValueError, match=message):
        SimilarityIndex(vectors)


def test_similarity_index_reports_missing_issue() -> None:
    index = SimilarityIndex({"A": [1, 0]})
    with pytest.raises(KeyError, match="missing vector for issue 'B'"):
        index.score("A", "B")


def test_neighbors_filter_closed_and_break_ties_by_id() -> None:
    query = Issue("Q")
    candidates = [Issue("B"), Issue("A"), Issue("C", "closed")]
    vectors = {"Q": [1, 0], "A": [1, 0], "B": [1, 0], "C": [1, 0]}

    assert [item.issue_id for item in nearest_neighbors(query, candidates, vectors)] == ["A", "B"]
    assert [
        item.issue_id for item in nearest_neighbors(query, candidates, vectors, include_closed=True)
    ] == ["A", "B", "C"]


def test_balanced_batches_are_deterministic_complete_and_bounded() -> None:
    issues = [Issue(str(index)) for index in range(10)]
    vectors = {str(index): [1, index / 20] if index < 5 else [index / 20, 1] for index in range(10)}

    first = balanced_batches(issues, vectors, target_size=4)
    shared_index = SimilarityIndex(vectors)
    second = balanced_batches(
        list(reversed(issues)), vectors, target_size=4, similarity_index=shared_index
    )

    assert [[item.id for item in batch] for batch in first] == [
        [item.id for item in batch] for batch in second
    ]
    assert sorted(item.id for batch in first for item in batch) == [str(i) for i in range(10)]
    assert max(map(len, first)) - min(map(len, first)) <= 1


def test_balanced_batches_reject_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        balanced_batches([Issue("A"), Issue("A")], {"A": [1, 0]})


def test_candidate_batches_keep_disconnected_signal_components_separate() -> None:
    issues = [Issue("D"), Issue("C"), Issue("B"), Issue("A")]
    vectors = {
        "A": [1, 0],
        "B": [0.99, 0.01],
        "C": [0, 1],
        "D": [0.01, 0.99],
        "closed": [1, 0],
    }
    candidates = [
        {"issue_id": "A", "related_issue_id": "B"},
        {"issue_id": "C", "related_issue_id": "D"},
        {"issue_id": "A", "related_issue_id": "closed"},
    ]

    first = candidate_batches(issues, candidates, vectors, target_size=4)
    second = candidate_batches(
        list(reversed(issues)), list(reversed(candidates)), vectors, target_size=4
    )

    assert [[item.id for item in batch] for batch in first] == [
        [item.id for item in batch] for batch in second
    ]
    assert [{item.id for item in batch} for batch in first] == [{"A", "B"}, {"C", "D"}]


def test_candidate_batches_include_active_echo_source_but_not_closed_target_or_no_signal() -> None:
    issues = [Issue("active"), Issue("no-signal")]
    vectors = {"active": [1, 0], "no-signal": [0, 1], "closed": [1, 0]}

    batches = candidate_batches(
        issues,
        [{"issue_id": "active", "related_issue_id": "closed"}],
        vectors,
    )

    assert [[item.id for item in batch] for batch in batches] == [["active"]]
