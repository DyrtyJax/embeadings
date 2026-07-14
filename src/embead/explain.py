"""Deterministic, content-safe explanations for semantic review candidates."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .models import IssueRecord

_FIELDS = (
    ("title", "title"),
    ("description", "description"),
    ("acceptance criteria", "acceptance_criteria"),
    ("design", "design"),
    ("notes", "notes"),
)
_FIELD_PRIORITY = {label: index for index, (label, _attribute) in enumerate(_FIELDS)}
_STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "been",
        "before",
        "being",
        "between",
        "from",
        "have",
        "into",
        "only",
        "should",
        "that",
        "their",
        "then",
        "this",
        "through",
        "using",
        "when",
        "where",
        "with",
    }
)


def _tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) >= 3 and token not in _STOP_WORDS
    )


def _dice(left: str, right: str) -> tuple[float, int]:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0, 0
    shared = len(left_tokens & right_tokens)
    return (2.0 * shared / (len(left_tokens) + len(right_tokens))), shared


def _field_evidence(left: IssueRecord, right: IssueRecord) -> list[dict[str, Any]]:
    evidence = []
    for label, attribute in _FIELDS:
        score, shared_count = _dice(getattr(left, attribute), getattr(right, attribute))
        if score > 0:
            evidence.append(
                {
                    "field": label,
                    "score": round(score, 3),
                    "shared_term_count": shared_count,
                }
            )
    evidence.sort(key=lambda item: (-item["score"], _FIELD_PRIORITY[item["field"]]))
    return evidence


def _is_parent_child(left: IssueRecord, right: IssueRecord) -> bool:
    return left.parent_id == right.id or right.parent_id == left.id


def _counterevidence(
    left: IssueRecord,
    right: IssueRecord,
    fields: list[dict[str, Any]],
    structural_context: str,
) -> list[str]:
    counterevidence: list[str] = []
    if _is_parent_child(left, right):
        counterevidence.append("direct parent/child scope can explain semantic similarity")
    elif structural_context == "none recorded":
        counterevidence.append("no structural relationship is recorded")

    acceptance = next((item for item in fields if item["field"] == "acceptance criteria"), None)
    if (
        left.acceptance_criteria
        and right.acceptance_criteria
        and (acceptance is None or acceptance["score"] < 0.15)
    ):
        counterevidence.append("acceptance criteria have little lexical alignment")
    if not fields:
        counterevidence.append("no canonical field has meaningful lexical overlap")
    return counterevidence


def _pattern(
    kind: str,
    left: IssueRecord,
    right: IssueRecord,
    fields: list[dict[str, Any]],
) -> str:
    if _is_parent_child(left, right):
        return "parent-child"
    if kind == "completed-work-echo":
        return "completed-work"
    scores = {item["field"]: item["score"] for item in fields}
    if scores.get("title", 0) >= 0.5 and scores.get("acceptance criteria", 0) >= 0.35:
        return "same-outcome"
    if scores.get("description", 0) >= 0.25 or scores.get("design", 0) >= 0.25:
        return "shared-subsystem"
    if fields:
        return "vocabulary-only"
    return "semantic-only"


def _join_fields(fields: Iterable[dict[str, Any]]) -> str:
    selected = list(fields)[:2]
    if not selected:
        return "whole-record semantics"
    return " and ".join(f"{item['field']} ({item['score']:.2f})" for item in selected)


def explain_candidate(
    left: IssueRecord,
    right: IssueRecord,
    *,
    kind: str,
    similarity: float,
    structural_context: str,
) -> dict[str, Any]:
    """Explain a candidate without a generative model or revealing issue text."""

    fields = _field_evidence(left, right)
    counterevidence = _counterevidence(left, right, fields, structural_context)
    pattern = _pattern(kind, left, right, fields)
    strongest = _join_fields(fields)
    lifecycle = f"{left.status or 'unknown'} to {right.status or 'unknown'}"
    why = (
        f"Overall similarity {similarity:.2f}; strongest field alignment: {strongest}; "
        f"lifecycle contrast: {lifecycle}; structure: {structural_context}."
    )

    if kind == "completed-work-echo":
        verify = (
            f"Compare {strongest} in active issue {left.id} with the delivered outcome and "
            f"acceptance criteria of closed issue {right.id}."
        )
    else:
        verify = (
            f"Compare {strongest} and the acceptance criteria of {left.id} and {right.id} "
            "to determine whether their intended outcomes differ."
        )
    return {
        "pattern": pattern,
        "why_surfaced": why,
        "field_evidence": fields[:3],
        "counterevidence": counterevidence,
        "what_to_verify": verify,
    }
