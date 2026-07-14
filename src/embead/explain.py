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

# Only terms from these fixed vocabularies may be copied into an explanation.
# Arbitrary tracker tokens can contain customer names, credentials, or internal
# identifiers, so shared free-form terms remain counts rather than report text.
# These maps are deliberately finite output vocabularies. Input aliases improve coverage, but
# never become output; this prevents customer names, credentials, hostnames, and arbitrary tracker
# text from leaking into reports. Order is a deterministic preference order.
_ACTION_ALIASES = {
    "authenticate": {"authenticate", "authentication", "login", "signin"},
    "authorize": {"authorize", "authorization", "permission", "permissions"},
    "batch": {"batch", "batching", "group", "package"},
    "cache": {"cache", "cached", "caching", "memoize"},
    "configure": {"configure", "configured", "configuration", "setup"},
    "create": {"add", "build", "create", "generate", "introduce"},
    "delete": {"delete", "purge", "remove"},
    "deploy": {"deploy", "deployment", "publish", "release"},
    "embed": {"embed", "embedding", "embeddings", "vectorize"},
    "export": {"export", "serialize", "write"},
    "filter": {"exclude", "filter", "select"},
    "import": {"deserialize", "import", "load", "read"},
    "migrate": {"convert", "migration", "migrate", "upgrade"},
    "parse": {"ingest", "parse", "parser", "scan"},
    "persist": {"persist", "save", "store"},
    "rank": {"prioritize", "rank", "ranking", "score", "sort"},
    "render": {"display", "format", "render", "show"},
    "retry": {"recover", "retry", "resume"},
    "search": {"find", "lookup", "query", "search"},
    "synchronize": {"merge", "sync", "synchronize", "update"},
    "test": {"assert", "benchmark", "test", "verify"},
    "validate": {"check", "reject", "validate", "validation"},
    "analyze": {"analyze", "audit", "evaluate", "inspect", "review"},
    "document": {"describe", "document", "explain", "guide"},
    "limit": {"bound", "cap", "limit", "restrict"},
    "optimize": {"improve", "optimize", "reduce", "tune"},
    "protect": {"isolate", "preserve", "protect", "redact"},
}
_ENTITY_ALIASES = {
    "API": {"api", "endpoint", "request", "response"},
    "artifact": {"artifact", "file", "manifest", "output"},
    "batch": {"batch", "component", "envelope", "group"},
    "cache": {"cache", "cached", "caching"},
    "configuration": {"config", "configuration", "option", "preset", "setting"},
    "database": {"database", "db", "dolt", "postgres", "sqlite"},
    "dependency": {"dependencies", "dependency", "depends", "relationship"},
    "embedding": {"embedding", "embeddings", "vector", "vectors"},
    "error": {"error", "exception", "failure", "warning"},
    "environment": {"environment", "runtime", "venv", "worktree"},
    "issue": {"bead", "beads", "issue", "issues", "record", "tracker"},
    "model": {"model", "provider"},
    "permission": {"access", "authorization", "permission", "permissions"},
    "queue": {"candidate", "candidates", "queue"},
    "report": {"diagnostic", "report", "summary"},
    "schema": {"contract", "schema", "validation"},
    "interface": {"cli", "command", "commands", "interface", "ui"},
    "session": {"session", "sessions"},
    "token": {"credential", "token", "tokens"},
    "workflow": {"pipeline", "process", "workflow"},
}
_OWNERSHIP_TERMS = frozenset(
    {"assign", "assigned", "assignee", "handoff", "owner", "ownership", "transfer"}
)
_INVARIANT_TERMS = frozenset(
    {"ensure", "fix", "invariant", "must", "never", "prevent", "regression", "repair", "restore"}
)
_IMPLEMENTATION_TERMS = frozenset(
    {"architecture", "backend", "configure", "design", "implement", "implementation", "provider"}
)
_CONCRETE_CHECK_TERMS = frozenset(
    {
        "acceptance",
        "assert",
        "contract",
        "ensure",
        "invariant",
        "must",
        "never",
        "prevent",
        "regression",
        "requirement",
        "test",
        "verify",
    }
)
# These safe pairs often describe a work category without identifying a fact, test, or invariant.
# Keep them useful as extraction diagnostics, but abstain from dressing them up as specific checks.
_BROAD_ANCHOR_PAIRS = frozenset(
    {
        ("analyze", "issue"),
        ("analyze", "workflow"),
        ("create", "artifact"),
        ("create", "issue"),
        ("document", "API"),
        ("document", "interface"),
        ("document", "issue"),
        ("document", "workflow"),
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


def _all_tokens(issue: IssueRecord) -> frozenset[str]:
    return frozenset().union(*(_tokens(getattr(issue, attribute)) for _label, attribute in _FIELDS))


def _normalized_match(tokens: frozenset[str], vocabulary: dict[str, set[str]]) -> str | None:
    return next(
        (normalized for normalized, aliases in vocabulary.items() if tokens & aliases), None
    )


def _normalized_match_in_text(
    value: str, eligible: frozenset[str], vocabulary: dict[str, set[str]]
) -> str | None:
    """Prefer the first shared safe concept in field order (usually the title verb)."""

    for token in re.findall(r"[a-z0-9]+", value.casefold()):
        if token not in eligible:
            continue
        match = next(
            (normalized for normalized, aliases in vocabulary.items() if token in aliases), None
        )
        if match:
            return match
    return None


def _category(
    left_tokens: frozenset[str],
    right_tokens: frozenset[str],
    *,
    kind: str,
    fields: list[dict[str, Any]],
) -> tuple[str, bool]:
    """Return a safe category and whether both records support its classification."""

    # Ownership is intentionally strict. The old `combined` test classified a pair as transferred
    # ownership when just one issue happened to mention an owner.
    ownership_corroborated = bool(left_tokens & _OWNERSHIP_TERMS) and bool(
        right_tokens & _OWNERSHIP_TERMS
    )
    invariant_corroborated = bool(left_tokens & _INVARIANT_TERMS) and bool(
        right_tokens & _INVARIANT_TERMS
    )
    implementation_corroborated = bool(left_tokens & _IMPLEMENTATION_TERMS) and bool(
        right_tokens & _IMPLEMENTATION_TERMS
    )
    if ownership_corroborated:
        return "transferred ownership", True
    if invariant_corroborated:
        return "repaired invariant", True
    if implementation_corroborated or any(
        item["field"] == "design" and item["score"] >= 0.2 for item in fields
    ):
        return "implementation choice", implementation_corroborated
    if kind == "completed-work-echo":
        return "completed outcome", True
    return "intended outcome", False


def _verification_anchor(
    left: IssueRecord,
    right: IssueRecord,
    *,
    kind: str,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    left_tokens = _all_tokens(left)
    right_tokens = _all_tokens(right)
    shared = left_tokens & right_tokens
    # Acceptance conditions are the most useful contract source, followed by title and design.
    # Extraction is anchored in the active (left) record. Pairwise overlap still controls evidence
    # and confidence, but does not erase a useful safe action just because the related record uses a
    # synonym or describes a different lifecycle phase.
    eligible_fields = [
        label
        for label in ("acceptance criteria", "title", "design", "description", "notes")
        if getattr(left, next(attribute for field, attribute in _FIELDS if field == label))
    ]
    shared_by_field: dict[str, frozenset[str]] = {}
    left_by_field: dict[str, frozenset[str]] = {}
    for label in eligible_fields:
        attribute = next(attribute for field_label, attribute in _FIELDS if field_label == label)
        left_by_field[label] = _tokens(getattr(left, attribute))
        shared_by_field[label] = _tokens(getattr(left, attribute)) & _tokens(
            getattr(right, attribute)
        )
    source_field = next(
        (
            label
            for label in eligible_fields
            if _normalized_match(left_by_field[label], _ACTION_ALIASES)
            and _normalized_match(left_by_field[label], _ENTITY_ALIASES)
        ),
        eligible_fields[0] if eligible_fields else "whole-record semantics",
    )
    source_attribute = next(
        (attribute for label, attribute in _FIELDS if label == source_field), None
    )
    source_shared = frozenset()
    if source_attribute:
        source_shared = shared_by_field[source_field]

    category, category_corroborated = _category(left_tokens, right_tokens, kind=kind, fields=fields)
    source_text = getattr(left, source_attribute) if source_attribute else ""
    source_tokens = left_by_field.get(source_field, frozenset())
    operation = _normalized_match_in_text(source_text, source_tokens, _ACTION_ALIASES) or (
        _normalized_match(shared, _ACTION_ALIASES)
    )
    entity = _normalized_match_in_text(source_text, source_tokens, _ENTITY_ALIASES) or (
        _normalized_match(shared, _ENTITY_ALIASES)
    )
    generic_fallback = operation is None or entity is None
    operation = operation or "compare"
    entity = entity or "acceptance condition"
    source_specific = bool(source_tokens) and (
        _normalized_match(source_tokens, _ACTION_ALIASES) is not None
        and _normalized_match(source_tokens, _ENTITY_ALIASES) is not None
    )
    pair_corroborated = (
        _normalized_match(source_shared, _ACTION_ALIASES) is not None
        and _normalized_match(source_shared, _ENTITY_ALIASES) is not None
    )
    confidence = (
        "high"
        if source_specific and pair_corroborated and category_corroborated
        else "medium"
        if not generic_fallback
        else "low"
    )
    has_concrete_language = bool(source_tokens & _CONCRETE_CHECK_TERMS)
    broad_pair = (operation, entity) in _BROAD_ANCHOR_PAIRS
    specificity = (
        "generic"
        if generic_fallback or (broad_pair and not has_concrete_language)
        else "concrete-check"
        if source_field == "acceptance criteria" and (pair_corroborated or category_corroborated)
        else "category-check"
    )
    return {
        "category": category,
        "outcome_or_invariant": category,
        "operation": operation,
        "action": operation,
        "entity_class": entity,
        "entity": entity,
        "source_field": source_field,
        "confidence": confidence,
        "extraction_confidence": confidence,
        "confidence_scope": "anchor-extraction",
        "specificity": specificity,
        "generic_fallback": generic_fallback,
    }


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
    anchor = _verification_anchor(left, right, kind=kind, fields=fields)
    strongest = _join_fields(fields)
    lifecycle = f"{left.status or 'unknown'} to {right.status or 'unknown'}"
    why = (
        f"Overall similarity {similarity:.2f}; strongest field alignment: {strongest}; "
        f"lifecycle contrast: {lifecycle}; structure: {structural_context}."
    )

    if anchor["specificity"] == "generic":
        anchor_text = "a generic local comparison; inspect the recorded acceptance conditions"
    else:
        anchor_text = (
            f"{anchor['category']} — {anchor['operation']} {anchor['entity_class']} "
            f"(derived from {anchor['source_field']})"
        )
    if kind == "completed-work-echo":
        verify = (
            f"Use this privacy-safe review anchor: {anchor_text}. Inspect whether verified "
            f"completion evidence for closed issue {right.id} changes the remaining scope of "
            f"active issue {left.id}; semantic similarity alone does not establish that it does."
        )
    else:
        verify = (
            f"Use this privacy-safe review anchor: {anchor_text}. Compare the recorded acceptance "
            f"conditions of {left.id} and {right.id}; similarity alone does not establish a "
            "shared contract or outcome."
        )
    return {
        "pattern": pattern,
        "why_surfaced": why,
        "field_evidence": fields[:3],
        "counterevidence": counterevidence,
        "verification_anchor": anchor,
        "what_to_verify": verify,
    }
