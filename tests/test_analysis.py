from dataclasses import dataclass

import pytest

from embead.analysis import balanced_batches, cosine_similarity, nearest_neighbors


@dataclass
class Issue:
    id: str
    status: str = "open"


def test_cosine_similarity_normalizes_and_validates() -> None:
    assert cosine_similarity([2, 0], [4, 0]) == pytest.approx(1)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0)
    with pytest.raises(ValueError):
        cosine_similarity([1], [1, 2])


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
    second = balanced_batches(list(reversed(issues)), vectors, target_size=4)

    assert [[item.id for item in batch] for batch in first] == [
        [item.id for item in batch] for batch in second
    ]
    assert sorted(item.id for batch in first for item in batch) == [str(i) for i in range(10)]
    assert max(map(len, first)) - min(map(len, first)) <= 1


def test_balanced_batches_reject_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        balanced_batches([Issue("A"), Issue("A")], {"A": [1, 0]})
