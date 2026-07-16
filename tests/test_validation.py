from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

import pytest

from embead.validation import ArtifactValidationError, validate_artifact


@pytest.fixture
def valid_sweep() -> dict[str, object]:
    return {
        "report_type": "sweep",
        "parameters": {"max_batch_size": 3},
        "candidates": [
            {"issue_id": "active-a", "related_issue_id": "active-b"},
            {"issue_id": "active-c", "related_issue_id": "closed-z"},
        ],
        "batches": [
            {
                "batch": 1,
                "kind": "connected-component",
                "issue_ids": ["active-a", "active-b"],
                "review_units": [{"issue_ids": ["active-a", "active-b"]}],
            },
            {
                "batch": 2,
                "kind": "singleton-envelope",
                "issue_ids": ["active-c"],
                "review_units": [{"issue_ids": ["active-c"]}],
            },
        ],
        "no_signal": {"issue_ids": ["active-d"]},
    }


def test_valid_sweep_invariants_pass(valid_sweep: dict[str, object]) -> None:
    validate_artifact(valid_sweep)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda value: value["batches"][0].update(
                {"review_units": [{"issue_ids": ["active-a"]}]}
            ),
            "batch-1:review-units-not-exact-partition",
        ),
        (
            lambda value: value["batches"][0].update({"issue_ids": ["active-a", "active-a"]}),
            "batch-1:duplicate-member",
        ),
        (
            lambda value: value["candidates"].append(
                {"issue_id": "unpackaged-a", "related_issue_id": "unpackaged-b"}
            ),
            "candidate-3:no-packaged-endpoint",
        ),
        (
            lambda value: value["parameters"].update({"max_batch_size": 1}),
            "batch-1:hard-maximum-exceeded",
        ),
        (
            lambda value: value["candidates"].__setitem__(
                0, {"issue_id": "active-a", "related_issue_id": "closed-z"}
            ),
            "batch-1:unit-1:disconnected",
        ),
        (
            lambda value: value["no_signal"].update({"issue_ids": ["active-a"]}),
            "population:member-also-no-signal",
        ),
    ],
)
def test_invalid_sweep_invariants_fail_with_bounded_diagnostics(
    valid_sweep: dict[str, object],
    mutate: Callable[[dict[str, object]], None],
    expected: str,
) -> None:
    payload = deepcopy(valid_sweep)
    mutate(payload)

    with pytest.raises(ArtifactValidationError) as raised:
        validate_artifact(payload)

    assert expected in raised.value.errors
    assert "active-a" not in str(raised.value)
    assert "closed-z" not in str(raised.value)


def test_batch_manifest_accepts_legacy_endpoint_names() -> None:
    validate_artifact(
        {
            "report_type": "batch",
            "batch": 1,
            "kind": "connected-component",
            "issues": [{"id": "task-a"}, {"id": "task-b"}],
            "review_units": [{"issue_ids": ["task-a", "task-b"]}],
            "neighbor_evidence": [{"source_id": "task-a", "target_id": "task-b"}],
        }
    )
