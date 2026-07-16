"""Semantic validation for versioned review artifacts.

JSON Schema proves shape. These checks prove graph and partition invariants that a consumer would
otherwise have to infer from producer behavior.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


class ArtifactValidationError(ValueError):
    """Report bounded, content-free invariant failures."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("artifact semantic validation failed: " + "; ".join(self.errors))


def _items(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _identifier(value: Any) -> str:
    return str(value or "")


def _edges(candidates: Any, errors: list[str]) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for index, candidate in enumerate(_items(candidates), start=1):
        if not isinstance(candidate, Mapping):
            errors.append(f"candidate-{index}:not-object")
            continue
        left = _identifier(candidate.get("issue_id") or candidate.get("source_id"))
        right = _identifier(candidate.get("related_issue_id") or candidate.get("target_id"))
        if not left or not right:
            errors.append(f"candidate-{index}:missing-endpoint")
            continue
        if left == right:
            errors.append(f"candidate-{index}:self-endpoint")
            continue
        edges.append((left, right))
    return edges


def _is_connected(members: Sequence[str], edges: Sequence[tuple[str, str]]) -> bool:
    if len(members) < 2:
        return True
    member_set = set(members)
    adjacency: dict[str, set[str]] = defaultdict(set)
    for left, right in edges:
        if left in member_set and right in member_set:
            adjacency[left].add(right)
            adjacency[right].add(left)
    seen = {members[0]}
    pending = [members[0]]
    while pending:
        current = pending.pop()
        additions = adjacency[current] - seen
        seen.update(additions)
        pending.extend(additions)
    return seen == member_set


def _validate_batches(
    batches: Any,
    edges: Sequence[tuple[str, str]],
    errors: list[str],
    *,
    hard_max: int | None,
) -> set[str]:
    global_members: list[str] = []
    batch_numbers: list[int] = []
    for position, batch in enumerate(_items(batches), start=1):
        label = f"batch-{position}"
        if not isinstance(batch, Mapping):
            errors.append(f"{label}:not-object")
            continue
        try:
            batch_numbers.append(int(batch.get("batch", position)))
        except (TypeError, ValueError):
            errors.append(f"{label}:invalid-number")
        members = [_identifier(item) for item in _items(batch.get("issue_ids"))]
        if not members or any(not item for item in members):
            errors.append(f"{label}:missing-member")
        if len(members) != len(set(members)):
            errors.append(f"{label}:duplicate-member")
        if hard_max is not None and len(members) > hard_max:
            errors.append(f"{label}:hard-maximum-exceeded")

        units = _items(batch.get("review_units"))
        flattened: list[str] = []
        for unit_position, unit in enumerate(units, start=1):
            unit_label = f"{label}:unit-{unit_position}"
            if not isinstance(unit, Mapping):
                errors.append(f"{unit_label}:not-object")
                continue
            unit_members = [_identifier(item) for item in _items(unit.get("issue_ids"))]
            flattened.extend(unit_members)
            if not unit_members or any(not item for item in unit_members):
                errors.append(f"{unit_label}:missing-member")
            if not _is_connected(unit_members, edges):
                errors.append(f"{unit_label}:disconnected")
            if batch.get("kind") == "singleton-envelope" and len(unit_members) != 1:
                errors.append(f"{unit_label}:non-singleton-envelope-unit")
        if Counter(flattened) != Counter(members):
            errors.append(f"{label}:review-units-not-exact-partition")
        global_members.extend(members)

    if len(batch_numbers) != len(set(batch_numbers)):
        errors.append("batches:duplicate-number")
    if len(global_members) != len(set(global_members)):
        errors.append("batches:duplicate-member")
    return set(global_members)


def _validate_summary(payload: Mapping[str, Any], errors: list[str]) -> None:
    edges = _edges(payload.get("candidates"), errors)
    parameters = payload.get("parameters")
    batch_policy = payload.get("batch_policy")
    raw_max = None
    if isinstance(parameters, Mapping):
        raw_max = parameters.get("max_batch_size")
    elif isinstance(batch_policy, Mapping):
        raw_max = batch_policy.get("max_batch_size")
    try:
        hard_max = int(raw_max) if raw_max is not None else None
    except (TypeError, ValueError):
        hard_max = None
        errors.append("batches:invalid-hard-maximum")
    if hard_max is not None and hard_max < 1:
        errors.append("batches:invalid-hard-maximum")

    members = _validate_batches(payload.get("batches"), edges, errors, hard_max=hard_max)
    endpoints = {endpoint for edge in edges for endpoint in edge}
    for index, edge in enumerate(edges, start=1):
        if not members.intersection(edge):
            errors.append(f"candidate-{index}:no-packaged-endpoint")
    for position, member in enumerate(sorted(members), start=1):
        if member not in endpoints:
            errors.append(f"member-{position}:no-candidate-evidence")

    no_signal = payload.get("no_signal")
    if isinstance(no_signal, Mapping):
        no_signal_ids = {_identifier(item) for item in _items(no_signal.get("issue_ids"))}
        if members & no_signal_ids:
            errors.append("population:member-also-no-signal")


def _validate_batch_manifest(payload: Mapping[str, Any], errors: list[str]) -> None:
    issues = _items(payload.get("issues"))
    members = [
        _identifier(issue.get("id")) if isinstance(issue, Mapping) else "" for issue in issues
    ]
    if not members or any(not member for member in members):
        errors.append("batch:missing-member")
    if len(members) != len(set(members)):
        errors.append("batch:duplicate-member")
    summary = {
        "batches": [
            {
                "batch": payload.get("batch", 1),
                "kind": payload.get("kind"),
                "issue_ids": members,
                "review_units": payload.get("review_units"),
            }
        ],
        "candidates": payload.get("neighbor_evidence"),
    }
    _validate_summary(summary, errors)


def validate_artifact(payload: Mapping[str, Any]) -> None:
    """Validate semantic graph invariants or raise content-free diagnostics."""

    errors: list[str] = []
    report_type = payload.get("report_type")
    if report_type in {"sweep", "triage"}:
        _validate_summary(payload, errors)
    elif report_type == "batch":
        _validate_batch_manifest(payload, errors)
    else:
        errors.append("report:unsupported-type")
    if errors:
        raise ArtifactValidationError(tuple(dict.fromkeys(errors)))
