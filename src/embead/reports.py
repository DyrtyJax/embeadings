"""Stable, read-only report payloads and human-friendly Markdown renderers.

This module deliberately knows nothing about the embedding or Beads adapters.  Inputs
may be mappings, dataclasses, named tuples, or ordinary objects with public
attributes.  Every builder returns values accepted by :mod:`json`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ADVISORY_NOTICE = (
    "Semantic similarity is advisory evidence, not tracker truth. "
    "Verify against current project state before taking action."
)
READ_ONLY_NOTICE = (
    "Read-only report: emBEADings did not change issues and this report does not "
    "recommend lifecycle changes."
)


def _field(value: Any, *names: str, default: Any = None) -> Any:
    """Read the first available field without requiring a concrete input type."""

    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _jsonable(value: Any) -> Any:
    """Convert common Python values to deterministic JSON-compatible values."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("report values must not contain non-finite numbers")
        return value
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _jsonable(value.model_dump())
    if hasattr(value, "_asdict"):
        return _jsonable(value._asdict())
    if isinstance(value, (set, frozenset)):
        converted = [_jsonable(item) for item in value]
        return sorted(converted, key=_sort_repr)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dict__"):
        return _jsonable(
            {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_") and not callable(item)
            }
        )
    slots = getattr(type(value), "__slots__", ())
    if isinstance(slots, str):
        slots = (slots,)
    if slots:
        return _jsonable(
            {
                name: getattr(value, name)
                for name in slots
                if not name.startswith("_") and hasattr(value, name)
            }
        )
    raise TypeError(f"unsupported report value: {type(value).__name__}")


def _sort_repr(value: Any) -> str:
    if isinstance(value, Mapping):
        return "|".join(f"{key}={_sort_repr(item)}" for key, item in value.items())
    if isinstance(value, list):
        return "[" + ",".join(_sort_repr(item) for item in value) + "]"
    return str(value)


def _record(value: Any) -> dict[str, Any]:
    record = _jsonable(value)
    if not isinstance(record, dict):
        raise TypeError("issues and evidence must be mapping-like objects")
    if "id" not in record:
        issue_id = _field(value, "issue_id")
        if issue_id is not None:
            record["id"] = _jsonable(issue_id)
    return dict(sorted(record.items()))


def _identity(value: Any) -> str:
    return str(_field(value, "id", "issue_id", default=""))


def _score(value: Any) -> float:
    raw = _field(value, "similarity", "score", default=-1.0)
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return -1.0
    return score if math.isfinite(score) else -1.0


def _evidence_key(value: Any) -> tuple[float, str, str]:
    return (
        -_score(value),
        str(_field(value, "id", "issue_id", "source_id", default="")),
        str(_field(value, "neighbor_id", "related_issue_id", "target_id", default="")),
    )


def _candidate_key(value: Any) -> tuple[int, float, str, str, str]:
    admission = str(_field(value, "admission_reason", default="semantic-threshold"))
    return (
        int(admission != "semantic-threshold"),
        -_score(value),
        str(_field(value, "kind", "type", default="")),
        str(_field(value, "issue_id", "id", default="")),
        str(_field(value, "related_issue_id", "neighbor_id", default="")),
    )


def build_neighbors_payload(
    issue: Any,
    neighbors: Iterable[Any],
    *,
    snapshot: Any,
    model: Any,
    cache: Any | None = None,
) -> dict[str, Any]:
    """Build the versioned machine payload for a nearest-neighbor query."""

    ordered = sorted(neighbors, key=_evidence_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "neighbors",
        "policy": {
            "read_only": True,
            "tracker_mutation_allowed": False,
            "advisory": True,
            "notice": f"{READ_ONLY_NOTICE} {ADVISORY_NOTICE}",
        },
        "snapshot": _jsonable(snapshot),
        "model": _jsonable(model),
        "cache": _jsonable(cache or {}),
        "issue": _record(issue),
        "neighbors": [_record(neighbor) for neighbor in ordered],
    }


def build_batch_manifest(
    run_id: str,
    batch: int,
    issues: Iterable[Any],
    neighbor_evidence: Iterable[Any],
    review_rubric: Iterable[Any],
    *,
    snapshot: Any,
    model: Any,
    cache: Any | None = None,
    batch_kind: str = "connected-component",
    review_units: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic, disposable review-batch manifest."""

    ordered_issues = sorted(issues, key=_identity)
    ordered_evidence = sorted(neighbor_evidence, key=_evidence_key)
    rubric = [_jsonable(item) for item in review_rubric]
    normalized_units = (
        [_jsonable(item) for item in review_units]
        if review_units is not None
        else [
            {
                "issue_ids": [
                    str(_field(issue, "id", "issue_id", default="")) for issue in ordered_issues
                ]
            }
        ]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "batch",
        "run_id": str(run_id),
        "batch": int(batch),
        "kind": str(batch_kind),
        "review_units": normalized_units,
        "snapshot": _jsonable(snapshot),
        "model": _jsonable(model),
        "cache": _jsonable(cache or {}),
        "policy": {
            "read_only": True,
            "implementation_allowed": False,
            "tracker_mutation_allowed": False,
            "advisory": True,
            "notice": f"{READ_ONLY_NOTICE} {ADVISORY_NOTICE}",
        },
        "issues": [_record(issue) for issue in ordered_issues],
        "neighbor_evidence": [_record(item) for item in ordered_evidence],
        "review_rubric": rubric,
    }


def build_sweep_payload(
    run_id: str,
    candidates: Iterable[Any],
    batches: Iterable[Any],
    *,
    snapshot: Any,
    model: Any,
    cache: Any | None = None,
    filters: Any | None = None,
    thresholds: Any | None = None,
    candidate_policy: Any | None = None,
    no_signal: Any | None = None,
    excluded: Any | None = None,
    target_batch_size: int | None = None,
    batch_diagnostics: Any | None = None,
    warnings: Iterable[str] = (),
    duration_ms: int | float | None = None,
) -> dict[str, Any]:
    """Build a versioned summary of one synchronous or asynchronous sweep."""

    ordered_candidates = sorted(candidates, key=_candidate_key)
    normalized_batches = [_jsonable(item) for item in batches]
    normalized_batches.sort(key=lambda item: int(_field(item, "batch", "batch_number", default=0)))
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_type": "sweep",
        "run_id": str(run_id),
        "policy": {
            "read_only": True,
            "tracker_mutation_allowed": False,
            "advisory": True,
            "notice": f"{READ_ONLY_NOTICE} {ADVISORY_NOTICE}",
        },
        "snapshot": _jsonable(snapshot),
        "model": _jsonable(model),
        "cache": _jsonable(cache or {}),
        "parameters": {
            "filters": _jsonable(filters or {}),
            "thresholds": _jsonable(thresholds or {}),
            "candidate_policy": _jsonable(candidate_policy or {}),
            "target_batch_size": target_batch_size,
            "max_batch_size": target_batch_size,
        },
        "candidates": [_record(candidate) for candidate in ordered_candidates],
        "batches": normalized_batches,
        "no_signal": _jsonable(no_signal or {"count": 0, "issue_ids": []}),
        "excluded": _jsonable(excluded or {"count": 0, "by_reason": {}, "issue_ids": []}),
        "warnings": sorted(str(warning) for warning in warnings),
        "batch_diagnostics": _jsonable(batch_diagnostics or {}),
    }
    if duration_ms is not None:
        payload["duration_ms"] = _jsonable(duration_ms)
    return payload


def _escape(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _counterevidence_text(value: Any) -> str:
    counterevidence = _field(value, "counterevidence", default=[])
    if isinstance(counterevidence, str):
        return counterevidence or "none recorded"
    return "; ".join(str(item) for item in counterevidence or []) or "none recorded"


def _dependency_text(value: Any) -> str | None:
    evidence = _field(value, "dependency_evidence")
    if not evidence:
        return None
    source = _field(evidence, "source_id", default="unknown")
    target = _field(evidence, "target_id", default="unknown")
    relationship_type = _field(evidence, "type", "relationship_type", default="depends-on")
    return f"{source} → {target} ({relationship_type})"


def _metadata_lines(payload: Mapping[str, Any]) -> list[str]:
    snapshot = payload.get("snapshot") or {}
    model = payload.get("model") or {}
    cache = payload.get("cache") or {}
    workspace = _field(snapshot, "workspace_id", "workspace", default="unknown")
    beads_version = _field(snapshot, "beads_version", default="unknown")
    model_id = _field(model, "id", "model_id", "name", default="unknown")
    revision = _field(model, "revision", "model_revision", default="unknown")
    hits = _field(cache, "hits", "cache_hits", default=0)
    misses = _field(cache, "misses", "cache_misses", default=0)
    source = _field(snapshot, "acquisition_source", default="unknown")
    live_count = _field(snapshot, "live_issue_count", default="unknown")
    export_count = _field(snapshot, "export_issue_count", default=None)
    warnings = _field(snapshot, "source_warnings", default=[]) or []
    lines = [
        f"- Workspace snapshot: `{_escape(workspace)}` (Beads `{_escape(beads_version)}`)",
        f"- Acquisition source: `{_escape(source)}` ({_escape(live_count)} live issues)",
        f"- Embedding model: `{_escape(model_id)}` revision `{_escape(revision)}`",
        f"- Cache: {_escape(hits)} hits, {_escape(misses)} misses",
    ]
    if export_count is not None:
        lines.append(f"- Discoverable JSONL export: {_escape(export_count)} issues")
    lines.extend(f"- Source warning: {_escape(warning)}" for warning in warnings)
    return lines


def render_neighbors_markdown(payload: Mapping[str, Any]) -> str:
    """Render a compact neighbors report; intentionally not a similarity matrix."""

    issue = payload.get("issue") or {}
    neighbors = payload.get("neighbors") or []
    issue_id = _field(issue, "id", "issue_id", default="unknown")
    title = _field(issue, "title", default="Untitled issue")
    lines = [
        f"# Semantic neighbors for {_escape(issue_id)}",
        "",
        f"**{_escape(title)}**",
        "",
        f"> {READ_ONLY_NOTICE} {ADVISORY_NOTICE}",
        "",
        "## Snapshot",
        "",
        *_metadata_lines(payload),
        "",
        "## Nearest semantic neighbors",
        "",
    ]
    if not neighbors:
        lines.extend(
            [
                "No semantic neighbors were found in the selected population.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "| Issue | Status | Title | Similarity | Structural context |",
                "|---|---|---|---:|---|",
            ]
        )
        for neighbor in neighbors:
            score = _score(neighbor)
            score_text = f"{score:.2f}" if score >= 0 else "—"
            context = _field(
                neighbor, "structural_context", "relationship", default="none recorded"
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape(_field(neighbor, "id", "issue_id", default="unknown")),
                        _escape(_field(neighbor, "status", default="unknown")),
                        _escape(_field(neighbor, "title", default="Untitled issue")),
                        score_text,
                        _escape(context),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "Scores are advisory; proximity can reflect shared context rather than overlap.",
                "",
            ]
        )
    lines.extend(
        [
            "## What to do next",
            "",
            "Verify relevant candidates against current project state and record evidence "
            "separately before considering any tracker action.",
            "",
        ]
    )
    return "\n".join(lines)


def _kind_label(value: Any) -> str:
    raw = str(_field(value, "kind", "type", default="review candidate"))
    normalized = raw.lower().replace("_", "-").replace(" ", "-")
    if normalized in {"completed-work-echo", "echo", "completed-echo"}:
        return "Completed-work echo"
    if normalized in {"possible-overlap", "overlap", "duplicate-candidate"}:
        return "Possible overlap"
    return raw.replace("_", " ").replace("-", " ").capitalize()


def render_batch_markdown(payload: Mapping[str, Any]) -> str:
    """Render one bounded reviewer handoff."""

    batch = payload.get("batch", "?")
    issues = payload.get("issues") or []
    evidence = payload.get("neighbor_evidence") or []
    rubric = payload.get("review_rubric") or []
    batch_kind = payload.get("kind", "connected-component")
    lines = [
        f"# Review batch {_escape(batch)}",
        "",
        f"> {READ_ONLY_NOTICE} {ADVISORY_NOTICE}",
        "",
        "## Snapshot",
        "",
        *_metadata_lines(payload),
        "",
        f"## Issues ({len(issues)})",
        "",
    ]
    if batch_kind == "singleton-envelope":
        lines.extend(
            [
                "This is an agent envelope of independent one-issue review units; "
                "its items are not presented as a semantic cluster.",
                "",
            ]
        )
    for issue in issues:
        lines.append(
            f"- `{_escape(_field(issue, 'id', 'issue_id', default='unknown'))}` "
            f"— {_escape(_field(issue, 'title', default='Untitled issue'))} "
            f"({_escape(_field(issue, 'status', default='unknown'))})"
        )
    if not issues:
        lines.append("No issues are assigned to this batch.")
    lines.extend(["", "## Why these items were surfaced", ""])
    if not evidence:
        lines.append("No neighbor evidence was recorded.")
    for item in evidence:
        source = _field(item, "issue_id", "source_id", "id", default="unknown")
        related = _field(item, "related_issue_id", "neighbor_id", "target_id", default="unknown")
        score = _score(item)
        score_text = f"{score:.2f}" if score >= 0 else "not recorded"
        context = _field(item, "structural_context", "relationship", default="none recorded")
        detail = [
            f"### {_kind_label(item)}: `{_escape(source)}` ↔ `{_escape(related)}`",
            "",
            f"- Similarity: {score_text} (advisory)",
            "- Admission reason: "
            + _escape(_field(item, "admission_reason", default="semantic-threshold")),
            f"- Pattern: {_escape(_field(item, 'pattern', default='not classified'))}",
            "- Why surfaced: " + _escape(_field(item, "why_surfaced", default="not recorded")),
            f"- Structural context: {_escape(context)}",
        ]
        dependency = _dependency_text(item)
        if dependency:
            detail.append(f"- Typed dependency: {_escape(dependency)}")
        detail.extend(
            [
                "- Counterevidence: " + _escape(_counterevidence_text(item)),
                "- What to verify: "
                + _escape(
                    _field(
                        item,
                        "what_to_verify",
                        "verify",
                        default="Compare both records with current project state.",
                    )
                ),
                "",
            ]
        )
        lines.extend(detail)
    lines.extend(["## Review rubric", ""])
    if rubric:
        for item in rubric:
            if isinstance(item, Mapping):
                text = _field(item, "text", "instruction", "question", default=_sort_repr(item))
            else:
                text = item
            lines.append(f"- {_escape(text)}")
    else:
        lines.append("- Verify every observation against current project evidence.")
    lines.extend(["", "Do not implement changes or mutate the tracker as part of this review.", ""])
    return "\n".join(lines)


def render_sweep_markdown(payload: Mapping[str, Any]) -> str:
    """Render the sweep outcome and bounded candidate evidence."""

    candidates = payload.get("candidates") or []
    batches = payload.get("batches") or []
    warnings = payload.get("warnings") or []
    no_signal = payload.get("no_signal") or {}
    excluded = payload.get("excluded") or {}
    candidate_policy = _field(payload.get("parameters") or {}, "candidate_policy", default={}) or {}
    lane_metrics = _field(candidate_policy, "lanes", default={}) or {}
    diagnostics = payload.get("batch_diagnostics") or {}
    echo_count = sum(_kind_label(item) == "Completed-work echo" for item in candidates)
    overlap_count = sum(_kind_label(item) == "Possible overlap" for item in candidates)
    lines = [
        f"# emBEADings sweep {_escape(payload.get('run_id', 'unknown'))}",
        "",
        f"> {READ_ONLY_NOTICE} {ADVISORY_NOTICE}",
        "",
        "## Outcome",
        "",
        f"Found {len(candidates)} review candidates across {len(batches)} batches.",
        "",
        f"- Completed-work echoes: {echo_count}",
        f"- Possible overlaps: {overlap_count}",
        f"- Other review candidates: {len(candidates) - echo_count - overlap_count}",
        f"- No-signal records: {_field(no_signal, 'count', default=0)}",
        f"- Excluded records: {_field(excluded, 'count', default=0)}",
        f"- Singleton components: {_field(diagnostics, 'singleton_component_count', default=0)}",
        f"- Singleton agent envelopes: {_field(diagnostics, 'agent_envelope_count', default=0)}",
        "- Cross-batch candidate edges: "
        + str(_field(diagnostics, "cross_batch_candidate_edges", default=0)),
        "",
    ]
    lines.extend(["## Candidate lanes", ""])
    if lane_metrics:
        for lane in ("dependency", "echo", "overlap"):
            metrics = _field(lane_metrics, lane, default={}) or {}
            lines.append(
                f"- {lane.capitalize()}: {_field(metrics, 'admitted', default=0)} admitted / "
                f"{_field(metrics, 'qualified', default=0)} qualified; "
                f"{_field(metrics, 'dropped_by_lane_cap', default=0)} dropped by lane budget"
            )
        lines.append(
            "- Baseline candidates protected in sensitivity mode: "
            f"{_field(candidate_policy, 'baseline_protected', default=0)}"
        )
    else:
        lines.append("Lane metrics were not recorded by this producer.")
    lines.extend(
        [
            "",
            "## Snapshot",
            "",
            *_metadata_lines(payload),
            "",
            "## Candidates",
            "",
        ]
    )
    if not candidates:
        lines.extend(["No review candidates were found in the selected population.", ""])
    for item in candidates:
        issue_id = _field(item, "issue_id", "id", default="unknown")
        related = _field(item, "related_issue_id", "neighbor_id", default="unknown")
        score = _score(item)
        score_text = f"{score:.2f}" if score >= 0 else "not recorded"
        detail = [
            f"### {_kind_label(item)}: `{_escape(issue_id)}` ↔ `{_escape(related)}`",
            "",
            f"- Similarity: {score_text} (advisory)",
            "- Admission reason: "
            + _escape(_field(item, "admission_reason", default="semantic-threshold")),
            f"- Pattern: {_escape(_field(item, 'pattern', default='not classified'))}",
            "- Why surfaced: " + _escape(_field(item, "why_surfaced", default="not recorded")),
            "- Structural context: "
            + _escape(
                _field(
                    item,
                    "structural_context",
                    "relationship",
                    default="none recorded",
                )
            ),
        ]
        dependency = _dependency_text(item)
        if dependency:
            detail.append(f"- Typed dependency: {_escape(dependency)}")
        detail.extend(
            [
                "- Counterevidence: " + _escape(_counterevidence_text(item)),
                "- What to verify: "
                + _escape(
                    _field(
                        item,
                        "what_to_verify",
                        "verify",
                        default="Compare both records with current project state.",
                    )
                ),
                "",
            ]
        )
        lines.extend(detail)
    lines.extend(["## Batches", ""])
    if not batches:
        lines.append("No batches were generated.")
    for batch in batches:
        number = _field(batch, "batch", "batch_number", default="?")
        members = _field(batch, "issues", "issue_ids", default=[]) or []
        issue_count = len(members)
        kind = _field(batch, "kind", default="connected-component")
        lines.append(f"- Batch {_escape(number)}: {issue_count} issues ({_escape(kind)})")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {_escape(warning)}" for warning in warnings)
    lines.extend(
        [
            "",
            "Verify candidates against current project state; this report does not decide "
            "whether any issue should change.",
            "",
        ]
    )
    return "\n".join(lines)
