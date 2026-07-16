"""Command-line interface for emBEADings."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_cache_path, user_state_path

from ._version import __version__
from .analysis import (
    MultiViewSimilarityIndex,
    SimilarityIndex,
    nearest_neighbors,
    package_candidate_batches,
)
from .beads import BeadsAdapter
from .cache import VectorCache
from .doctor import diagnose
from .explain import explain_candidate
from .incremental import (
    IncrementalScope,
    build_checkpoint,
    ensure_external_path,
    load_checkpoint,
    scope_since_timestamp,
)
from .linear import LinearAdapter
from .models import IssueRecord, WorkspaceSnapshot, canonical_text, semantic_field_texts
from .provider import HashingProvider, Model2VecProvider, provider_readiness
from .ranking import CandidatePolicy, CandidateRanking, rank_candidates, structural_context
from .reports import (
    build_batch_manifest,
    build_collisions_payload,
    build_neighbors_payload,
    build_sweep_payload,
    render_batch_markdown,
    render_collisions_markdown,
    render_neighbors_markdown,
    render_sweep_markdown,
)
from .surfaces import analyze_code_surfaces, parse_worktree_mappings
from .trackers import TrackerAdapter, TrackerError

ACTIVE_STATUSES = {"open", "in_progress", "blocked", "deferred"}
REVIEW_RUBRIC = (
    "Verify each candidate against current source, documentation, and shipped behavior.",
    "Record counterevidence when similar wording reflects different scope.",
    "Do not implement changes or mutate the tracker during this review.",
)
PRODUCER_CAPABILITIES = (
    "additive-fields",
    "advisory-evidence",
    "read-only-review",
    "code-surface-pointers",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="embead",
        description="Find related tracker work without changing your tracker.",
        epilog="Read-only • Issue text is embedded locally by default.",
    )
    parser.add_argument("--version", action="version", version=f"embead {__version__}")
    parser.add_argument(
        "--source",
        choices=("beads", "linear"),
        default=os.environ.get("EMBEAD_SOURCE", "beads"),
        help="Read work from Beads (default) or a Linear team",
    )
    parser.add_argument(
        "--linear-team",
        default=os.environ.get("LINEAR_TEAM"),
        metavar="ID|KEY|NAME",
        help="Linear team ID, key, or exact name (or set LINEAR_TEAM)",
    )
    parser.add_argument(
        "--provider",
        choices=("model2vec", "hashing"),
        default=os.environ.get("EMBEAD_PROVIDER", "model2vec"),
        help=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    neighbors = subparsers.add_parser("neighbors", help="Find nearest semantic neighbors")
    neighbors.add_argument("issue_id")
    neighbors.add_argument("--limit", type=int, default=5)
    neighbors.add_argument("--include-closed", action="store_true")
    neighbors.add_argument("--json", action="store_true", dest="as_json")
    neighbors.add_argument("--output", type=Path)

    sweep = subparsers.add_parser("sweep", help="Create disposable semantic review batches")
    sweep.add_argument(
        "--size", type=int, default=9, help="Hard maximum issues per agent review artifact"
    )
    sweep.add_argument(
        "--status",
        action="append",
        help="Include a stored status (repeatable; defaults to all active work)",
    )
    sweep.add_argument("--echo-threshold", type=float, default=0.72)
    sweep.add_argument("--overlap-threshold", type=float, default=0.82)
    sweep.add_argument(
        "--include-epics",
        action="store_true",
        help="Include epic/container records in candidate analysis (excluded by default)",
    )
    _candidate_policy_arguments(sweep)
    _semantic_retrieval_arguments(sweep)
    _incremental_arguments(sweep)
    _code_surface_arguments(sweep, opt_in=True)
    sweep.add_argument("--output", type=Path)
    sweep.add_argument("--json", action="store_true", dest="as_json")

    batch = subparsers.add_parser("batch", help="Alias for a synchronous sweep")
    batch.add_argument(
        "--size", type=int, default=9, help="Hard maximum issues per agent review artifact"
    )
    batch.add_argument("--status", action="append")
    batch.add_argument("--echo-threshold", type=float, default=0.72)
    batch.add_argument("--overlap-threshold", type=float, default=0.82)
    batch.add_argument("--include-epics", action="store_true")
    _candidate_policy_arguments(batch)
    _semantic_retrieval_arguments(batch)
    _incremental_arguments(batch)
    _code_surface_arguments(batch, opt_in=True)
    batch.add_argument("--output", type=Path)
    batch.add_argument("--json", action="store_true", dest="as_json")

    readiness = subparsers.add_parser(
        "readiness",
        help="Prepare the local embedding model without reading tracker issues",
    )
    readiness.add_argument(
        "--offline",
        action="store_true",
        help="Require model artifacts to already exist in the configured local cache",
    )
    readiness.add_argument("--json", action="store_true", dest="as_json")

    capabilities = subparsers.add_parser(
        "capabilities",
        help=(
            "Describe the report contract and producer capabilities without reading tracker issues"
        ),
    )
    capabilities.add_argument("--json", action="store_true", dest="as_json")

    doctor = subparsers.add_parser(
        "doctor",
        help="Inspect source, Git, model, and cache readiness without changing state",
    )
    doctor.add_argument(
        "--offline",
        action="store_true",
        help="Require pinned model artifacts to already exist in the local cache",
    )
    doctor.add_argument("--json", action="store_true", dest="as_json")

    collisions = subparsers.add_parser(
        "collisions",
        help="Find active work that points at the same local code surfaces",
    )
    collisions.add_argument(
        "--status",
        action="append",
        help="Include a stored status (repeatable; defaults to all active work)",
    )
    collisions.add_argument("--include-epics", action="store_true")
    _code_surface_arguments(collisions, opt_in=False)
    collisions.add_argument("--output", type=Path)
    collisions.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _candidate_policy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--exception-margin",
        type=float,
        default=0.08,
        help="Maximum below-threshold margin requiring corroborating evidence",
    )
    parser.add_argument(
        "--reciprocal-rank",
        type=int,
        default=5,
        help="Admit near-threshold pairs that mutually rank within this depth (0 disables)",
    )
    parser.add_argument("--max-candidates-per-issue", type=int, default=3)
    parser.add_argument(
        "--max-echoes-per-target",
        type=int,
        default=2,
        help=(
            "Maximum completed-work echoes that may point to the same closed record "
            "before deterministic backfill"
        ),
    )
    parser.add_argument(
        "--max-echo-alternatives-per-active",
        type=int,
        default=3,
        help="Bound completed-record fallbacks retained for each active issue",
    )
    parser.add_argument(
        "--max-dependency-candidates-per-issue",
        type=int,
        default=3,
        help="Independent per-issue allowance for typed dependency candidates",
    )
    total_budget = parser.add_mutually_exclusive_group()
    total_budget.add_argument("--max-candidates", type=int, default=None)
    total_budget.add_argument(
        "--weekly-review-budget",
        "--review-budget",
        type=int,
        metavar="CANDIDATES",
        help=(
            "Bound a weekly semantic queue with reserved access for dependency, echo, and "
            "overlap lanes; unused capacity reflows in dependency-to-echo-to-overlap order"
        ),
    )
    parser.add_argument(
        "--max-dependency-candidates",
        type=int,
        default=75,
        help="Independent budget for candidates backed by a typed dependency",
    )
    parser.add_argument("--max-echo-candidates", type=int, default=125)
    parser.add_argument("--max-overlap-candidates", type=int, default=125)


def _semantic_retrieval_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--objective",
        action="append",
        choices=("collision", "overlap", "echo", "structure"),
        help=(
            "Run an explicit review objective (repeatable). Selecting objectives separates "
            "typed structure from semantic novelty; omitted for legacy behavior."
        ),
    )
    parser.add_argument(
        "--semantic-view",
        choices=("whole", "fields"),
        default="whole",
        help=("Use the stable whole-record vector or experimental whole-plus-field retrieval"),
    )


def _incremental_arguments(parser: argparse.ArgumentParser) -> None:
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--changed-since",
        metavar="RFC3339",
        help="Review candidates touching active records updated after this timestamp",
    )
    scope.add_argument(
        "--since-checkpoint",
        type=Path,
        metavar="PATH",
        help="Review candidates touching active records changed since a prior checkpoint",
    )
    parser.add_argument(
        "--write-checkpoint",
        type=Path,
        metavar="PATH",
        help="Atomically write a portable metadata-only checkpoint outside the repository",
    )


def _code_surface_arguments(parser: argparse.ArgumentParser, *, opt_in: bool) -> None:
    if opt_in:
        parser.add_argument(
            "--code-surfaces",
            action="store_true",
            help="Add local explicit-reference and active-worktree collision evidence",
        )
    parser.add_argument(
        "--worktree-map",
        action="append",
        default=[],
        metavar="ISSUE_ID=PATH",
        help=(
            "Associate an active issue with a registered Git worktree; repeatable. "
            "Supplying a mapping enables code-surface analysis for sweeps."
        ),
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Local Git reference used to identify committed worktree changes",
    )
    parser.add_argument(
        "--max-hub-surface-issues",
        type=int,
        default=5,
        help=(
            "Summarize explicit-only paths/modules referenced by more than this many "
            "active records instead of emitting every pair"
        ),
    )


def _provider(name: str) -> Model2VecProvider | HashingProvider:
    if name == "hashing":
        return HashingProvider()
    return Model2VecProvider()


def _load_source(args: argparse.Namespace) -> tuple[WorkspaceSnapshot, tuple[IssueRecord, ...]]:
    adapter: TrackerAdapter
    if args.source == "linear":
        if not args.linear_team:
            raise ValueError("--linear-team or LINEAR_TEAM is required for the Linear source")
        adapter = LinearAdapter(team=args.linear_team)
    else:
        adapter = BeadsAdapter()
    return adapter.load()


def _workspace_paths(workspace_id: str) -> tuple[Path, Path]:
    namespace = workspace_id[:16]
    return (
        user_cache_path("embeadings") / "vectors" / namespace,
        user_state_path("embeadings") / "runs" / namespace,
    )


def _load_vectors(
    issues: tuple[IssueRecord, ...],
    provider: Model2VecProvider | HashingProvider,
    cache: VectorCache,
) -> tuple[dict[str, list[float]], dict[str, int]]:
    texts = [canonical_text(issue) for issue in issues]
    keys = [
        cache.key_for(
            text,
            model_id=provider.model_id,
            model_revision=provider.model_revision,
        )
        for text in texts
    ]
    hits = sum(
        cache.get(
            key,
            model_id=provider.model_id,
            model_revision=provider.model_revision,
        )
        is not None
        for key in keys
    )
    if isinstance(provider, Model2VecProvider) and hits < len(issues):
        print(
            f"Preparing local model {provider.model_id}@{provider.model_revision[:12]}. "
            "Issue text is not uploaded.",
            file=sys.stderr,
        )
    vectors = cache.encode(texts, provider)
    return dict(zip((issue.id for issue in issues), vectors, strict=True)), {
        "hits": hits,
        "misses": len(issues) - hits,
    }


def _load_field_similarity_index(
    issues: tuple[IssueRecord, ...],
    provider: Model2VecProvider | HashingProvider,
    cache: VectorCache,
    whole_record: SimilarityIndex,
) -> tuple[MultiViewSimilarityIndex, dict[str, Any]]:
    """Load addressable field views without changing the stable whole-record cache."""

    field_vectors: dict[str, dict[str, list[float]]] = {}
    field_hits = field_misses = 0
    view_counts: dict[str, int] = {}
    for field in ("title", "description", "acceptance_criteria", "design"):
        entries = [
            (issue.id, text) for issue in issues if (text := semantic_field_texts(issue).get(field))
        ]
        if not entries:
            continue
        canonicalization_version = f"field-aware-v1:{field}"
        keys = [
            cache.key_for(
                text,
                model_id=provider.model_id,
                model_revision=provider.model_revision,
                canonicalization_version=canonicalization_version,
            )
            for _identifier, text in entries
        ]
        hits = sum(
            cache.get(
                key,
                model_id=provider.model_id,
                model_revision=provider.model_revision,
            )
            is not None
            for key in keys
        )
        field_hits += hits
        field_misses += len(entries) - hits
        vectors = cache.encode(
            [text for _identifier, text in entries],
            provider,
            canonicalization_version=canonicalization_version,
        )
        field_vectors[field] = dict(
            zip((identifier for identifier, _text in entries), vectors, strict=True)
        )
        view_counts[field] = len(entries)
    return MultiViewSimilarityIndex(whole_record, field_vectors), {
        "field_hits": field_hits,
        "field_misses": field_misses,
        "field_view_counts": view_counts,
        "semantic_view": "fields",
    }


def _objective_for_candidate(candidate: dict[str, Any]) -> str:
    if candidate["lane"] == "dependency":
        return "structure"
    return "echo" if candidate["kind"] == "completed-work-echo" else "overlap"


def _retrieval_provenance(
    candidate: dict[str, Any],
    index: SimilarityIndex | MultiViewSimilarityIndex,
    *,
    active_ids: list[str],
    closed_ids: list[str],
) -> dict[str, Any]:
    left_id = candidate["issue_id"]
    right_id = candidate["related_issue_id"]
    if isinstance(index, MultiViewSimilarityIndex):
        channel_scores = index.channel_scores(left_id, right_id)
        selection_rule = "max-semantic-view"
    else:
        channel_scores = (("whole_record", index.score(left_id, right_id)),)
        selection_rule = "whole-record-cosine"
    forward_pool = closed_ids if candidate["kind"] == "completed-work-echo" else active_ids
    reverse_pool = active_ids
    best_score = max(score for _channel, score in channel_scores)
    receipts = []
    for channel, score in channel_scores:
        if isinstance(index, MultiViewSimilarityIndex):
            forward_rank = index.channel_rank(
                channel, left_id, right_id, [item for item in forward_pool if item != left_id]
            )
            reverse_rank = index.channel_rank(
                channel, right_id, left_id, [item for item in reverse_pool if item != right_id]
            )
        else:
            forward_rank = _rank_in_channel(
                index, left_id, right_id, [item for item in forward_pool if item != left_id]
            )
            reverse_rank = _rank_in_channel(
                index, right_id, left_id, [item for item in reverse_pool if item != right_id]
            )
        receipts.append(
            {
                "channel": (
                    "whole-record-semantic"
                    if channel == "whole_record"
                    else f"field-semantic:{channel}"
                ),
                "evidence_family": "tracker-text",
                "pair_score": round(score, 6),
                "selected": math.isclose(score, best_score, abs_tol=1e-12),
                "ranks": {
                    "issue_to_related": forward_rank,
                    "related_to_issue": reverse_rank,
                },
            }
        )
    relationship = candidate.get("dependency_evidence")
    if isinstance(relationship, dict):
        receipts.append(
            {
                "channel": "typed-tracker-relationship",
                "evidence_family": "tracker-structure",
                "relationship_type": relationship.get("type"),
                "selected": candidate["lane"] == "dependency",
            }
        )
    return {
        "selection_rule": selection_rule,
        "channels": receipts,
    }


def _rank_in_channel(
    index: SimilarityIndex,
    query_id: str,
    target_id: str,
    candidate_ids: list[str],
) -> int | None:
    return next(
        (
            position
            for position, (identifier, _score) in enumerate(
                index.ranked(query_id, candidate_ids), start=1
            )
            if identifier == target_id
        ),
        None,
    )


def _structural_context(left: IssueRecord, right: IssueRecord) -> str:
    return structural_context(left, right)


def _issue_summary(issue: IssueRecord) -> dict[str, Any]:
    return {
        "id": issue.id,
        "title": issue.title,
        "status": issue.status,
        "issue_type": issue.issue_type,
        "priority": issue.priority,
        "labels": list(issue.labels),
        "parent_id": issue.parent_id,
        "dependencies": list(issue.dependencies),
        "dependency_links": [asdict(link) for link in issue.dependency_links],
    }


def _model_metadata(provider: Model2VecProvider | HashingProvider) -> dict[str, str]:
    return {"model_id": provider.model_id, "model_revision": provider.model_revision}


def _readiness(args: argparse.Namespace) -> int:
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    result = provider_readiness(_provider(args.provider))
    payload = {
        "readiness_version": 1,
        **result,
        "corpus_loaded": False,
        "network_policy": "offline" if args.offline else "prefetch-allowed",
    }
    if args.as_json:
        sys.stdout.write(_json_text(payload))
    else:
        sys.stdout.write(
            "Embedding model ready\n"
            f"Model: {payload['model_id']}@{payload['model_revision']}\n"
            f"Vector dimension: {payload['vector_dimension']}\n"
            "Corpus loaded: no\n"
        )
    return 0


def _capabilities(args: argparse.Namespace) -> int:
    payload = {
        "document_type": "embeadings-capabilities",
        "protocol_version": 1,
        "role": "producer",
        "schema_versions": [1],
        "report_types": ["neighbors", "batch", "sweep", "collisions"],
        "capabilities": list(PRODUCER_CAPABILITIES),
        "required_capabilities": ["read-only-review"],
    }
    if args.as_json:
        sys.stdout.write(_json_text(payload))
    else:
        sys.stdout.write(
            "emBEADings producer capabilities\n"
            "Protocol: 1\n"
            "Schemas: 1\n"
            f"Reports: {', '.join(payload['report_types'])}\n"
            f"Capabilities: {', '.join(payload['capabilities'])}\n"
            "Required: read-only-review\n"
        )
    return 0


def _doctor(args: argparse.Namespace) -> int:
    payload = diagnose(
        source=args.source,
        linear_team=args.linear_team,
        provider=_provider(args.provider),
        offline=args.offline,
    )
    if args.as_json:
        sys.stdout.write(_json_text(payload))
    else:
        sys.stdout.write(
            f"emBEADings doctor: {payload['status']}\n"
            f"Source: {payload['source']['status']} — {payload['source']['detail']}\n"
            f"Repository: {payload['repository']['status']} — "
            f"{payload['repository']['detail']}\n"
            f"Embedding: {payload['embedding']['status']} — "
            f"{payload['embedding']['detail']}\n"
            f"Cache: {payload['cache']['status']} — {payload['cache']['detail']}\n"
        )
    return 2 if payload["status"] == "blocked" else 0


def _surface_analysis(
    args: argparse.Namespace,
    snapshot: Any,
    issues: list[IssueRecord],
) -> dict[str, Any]:
    mappings = parse_worktree_mappings(args.worktree_map)
    analysis = analyze_code_surfaces(
        issues,
        workspace_path=snapshot.workspace_path,
        invocation_path=Path.cwd(),
        worktree_mappings=mappings,
        base_reference=args.base_ref,
        hub_surface_limit=args.max_hub_surface_issues,
    )
    return analysis.to_dict()


def _collisions(args: argparse.Namespace) -> int:
    snapshot, issues = _load_source(args)
    statuses = {status.casefold() for status in (args.status or ACTIVE_STATUSES)}
    population = [
        issue
        for issue in issues
        if issue.status.casefold() in statuses
        and (args.include_epics or issue.issue_type.casefold() != "epic")
    ]
    analysis = _surface_analysis(args, snapshot, population)
    payload = build_collisions_payload(
        analysis,
        snapshot=asdict(snapshot),
        filters={"status": sorted(statuses), "include_epics": args.include_epics},
    )
    rendered = _json_text(payload) if args.as_json else render_collisions_markdown(payload)
    if args.output:
        _atomic_text(args.output, rendered)
    sys.stdout.write(rendered)
    return 0


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _neighbors(args: argparse.Namespace) -> int:
    snapshot, issues = _load_source(args)
    by_id = {issue.id: issue for issue in issues}
    if args.issue_id not in by_id:
        raise ValueError(f"issue not found: {args.issue_id}")
    if args.limit < 0:
        raise ValueError("--limit cannot be negative")
    provider = _provider(args.provider)
    cache_path, _ = _workspace_paths(snapshot.workspace_id)
    vectors, cache_stats = _load_vectors(issues, provider, VectorCache(cache_path))
    similarity_index = SimilarityIndex(vectors)
    ranked = nearest_neighbors(
        by_id[args.issue_id],
        issues,
        vectors,
        limit=args.limit,
        include_closed=args.include_closed,
        similarity_index=similarity_index,
    )
    evidence = []
    for neighbor in ranked:
        related = by_id[neighbor.issue_id]
        evidence.append(
            {
                **_issue_summary(related),
                "similarity": round(neighbor.similarity, 6),
                "structural_context": _structural_context(by_id[args.issue_id], related),
            }
        )
    payload = build_neighbors_payload(
        _issue_summary(by_id[args.issue_id]),
        evidence,
        snapshot=asdict(snapshot),
        model=_model_metadata(provider),
        cache=cache_stats,
    )
    rendered = _json_text(payload) if args.as_json else render_neighbors_markdown(payload)
    if args.output:
        _atomic_text(args.output, rendered)
    sys.stdout.write(rendered)
    return 0


def _candidate_evidence(
    population: list[IssueRecord],
    all_issues: tuple[IssueRecord, ...],
    vectors: dict[str, list[float]],
    *,
    echo_threshold: float,
    overlap_threshold: float,
    similarity_index: SimilarityIndex | MultiViewSimilarityIndex | None = None,
    exception_margin: float = 0.08,
    reciprocal_rank: int = 5,
    max_candidates_per_issue: int = 3,
    max_echoes_per_target: int = 2,
    max_echo_alternatives_per_active: int = 3,
    max_dependency_candidates_per_issue: int = 3,
    max_candidates: int = 250,
    max_dependency_candidates: int = 75,
    max_echo_candidates: int = 125,
    max_overlap_candidates: int = 125,
    lane_reservations: dict[str, int] | None = None,
    eligible_issue_ids: frozenset[str] | None = None,
    objectives: frozenset[str] | None = None,
) -> CandidateRanking:
    ranking = rank_candidates(
        population,
        all_issues,
        similarity_index or SimilarityIndex(vectors),
        CandidatePolicy(
            echo_threshold=echo_threshold,
            overlap_threshold=overlap_threshold,
            exception_margin=exception_margin,
            reciprocal_rank=reciprocal_rank,
            max_per_issue=max_candidates_per_issue,
            max_echoes_per_target=max_echoes_per_target,
            max_echo_alternatives_per_active=max_echo_alternatives_per_active,
            max_dependencies_per_issue=max_dependency_candidates_per_issue,
            max_total=max_candidates,
            max_dependencies=max_dependency_candidates,
            max_echoes=max_echo_candidates,
            max_overlaps=max_overlap_candidates,
            lane_reservations=lane_reservations,
            objectives=objectives,
        ),
        eligible_issue_ids=eligible_issue_ids,
    )
    by_id = {issue.id: issue for issue in all_issues}
    active_ids = sorted(issue.id for issue in population)
    closed_ids = sorted(
        issue.id
        for issue in all_issues
        if issue.status.casefold() in {"closed", "done", "completed", "resolved"}
    )
    explained = []
    for candidate in ranking.candidates:
        left = by_id[candidate["issue_id"]]
        right = by_id[candidate["related_issue_id"]]
        enriched = {
            **candidate,
            **explain_candidate(
                left,
                right,
                kind=candidate["kind"],
                similarity=candidate["similarity"],
                structural_context=candidate["structural_context"],
            ),
        }
        if objectives is not None or isinstance(similarity_index, MultiViewSimilarityIndex):
            enriched.update(
                {
                    "objective": _objective_for_candidate(candidate),
                    "retrieval_provenance": _retrieval_provenance(
                        candidate,
                        similarity_index or SimilarityIndex(vectors),
                        active_ids=active_ids,
                        closed_ids=closed_ids,
                    ),
                }
            )
        explained.append(enriched)
    return CandidateRanking(
        candidates=tuple(explained),
        qualified=ranking.qualified,
        dropped_by_issue_cap=ranking.dropped_by_issue_cap,
        dropped_by_run_cap=ranking.dropped_by_run_cap,
        lanes=ranking.lanes,
        baseline_protected=ranking.baseline_protected,
        dropped_by_lane_cap=ranking.dropped_by_lane_cap,
        dropped_by_dependency_issue_cap=ranking.dropped_by_dependency_issue_cap,
        dropped_by_echo_target_cap=ranking.dropped_by_echo_target_cap,
        capped_typed_dependencies=ranking.capped_typed_dependencies,
        echo_target_hubs=ranking.echo_target_hubs,
        reciprocal_diagnostics=ranking.reciprocal_diagnostics,
        cap_replacements=ranking.cap_replacements,
        dependency_funnel=ranking.dependency_funnel,
    )


def _review_lane_reservations(limit: int, lane_caps: dict[str, int]) -> dict[str, int]:
    """Reserve a structural majority while guaranteeing semantic lane access.

    The reservations are minimum access, not quotas. Any unused capacity is
    returned to the normal dependency -> echo -> overlap priority pass.
    """

    if limit == 1:
        requested = {"dependency": 0, "echo": 0, "overlap": 1}
    elif limit == 2:
        requested = {"dependency": 1, "echo": 0, "overlap": 1}
    else:
        echo = max(1, limit // 5)
        overlap = max(1, limit // 5)
        requested = {
            "dependency": limit - echo - overlap,
            "echo": echo,
            "overlap": overlap,
        }
    return {lane: min(requested[lane], lane_caps[lane]) for lane in requested}


def _sweep(args: argparse.Namespace) -> int:
    if args.size < 1:
        raise ValueError("--size must be positive")
    max_candidates = (
        args.weekly_review_budget
        if args.weekly_review_budget is not None
        else args.max_candidates
        if args.max_candidates is not None
        else 250
    )
    objectives = frozenset(args.objective) if args.objective else None
    lane_caps = {
        "dependency": args.max_dependency_candidates,
        "echo": args.max_echo_candidates,
        "overlap": args.max_overlap_candidates,
    }
    if objectives is not None:
        lane_caps = {
            "dependency": lane_caps["dependency"] if "structure" in objectives else 0,
            "echo": lane_caps["echo"] if "echo" in objectives else 0,
            "overlap": lane_caps["overlap"] if "overlap" in objectives else 0,
        }
    lane_reservations = (
        _review_lane_reservations(max_candidates, lane_caps)
        if args.weekly_review_budget is not None
        else None
    )
    policy = CandidatePolicy(
        echo_threshold=args.echo_threshold,
        overlap_threshold=args.overlap_threshold,
        exception_margin=args.exception_margin,
        reciprocal_rank=args.reciprocal_rank,
        max_per_issue=args.max_candidates_per_issue,
        max_echoes_per_target=args.max_echoes_per_target,
        max_echo_alternatives_per_active=args.max_echo_alternatives_per_active,
        max_dependencies_per_issue=args.max_dependency_candidates_per_issue,
        max_total=max_candidates,
        max_dependencies=lane_caps["dependency"],
        max_echoes=lane_caps["echo"],
        max_overlaps=lane_caps["overlap"],
        lane_reservations=lane_reservations,
        objectives=objectives,
    )
    policy.validate()
    started = time.monotonic()
    phase_started = started
    snapshot, issues = _load_source(args)
    acquisition_ms = round((time.monotonic() - phase_started) * 1000)
    if args.write_checkpoint:
        ensure_external_path(
            args.write_checkpoint,
            snapshot.workspace_path,
            purpose="checkpoint output",
        )
    if args.since_checkpoint:
        ensure_external_path(
            args.since_checkpoint,
            snapshot.workspace_path,
            purpose="checkpoint input",
        )
    statuses = {status.casefold() for status in (args.status or ACTIVE_STATUSES)}
    selected_population = [issue for issue in issues if issue.status.casefold() in statuses]
    excluded_epics = [
        issue
        for issue in selected_population
        if not args.include_epics and issue.issue_type.casefold() == "epic"
    ]
    excluded_ids = {issue.id for issue in excluded_epics}
    population = [issue for issue in selected_population if issue.id not in excluded_ids]
    code_surface_payload: dict[str, Any] | None = None
    code_surface_ms = 0
    if args.code_surfaces or args.worktree_map or (objectives and "collision" in objectives):
        phase_started = time.monotonic()
        code_surface_payload = _surface_analysis(args, snapshot, population)
        code_surface_ms = round((time.monotonic() - phase_started) * 1000)
    scope: IncrementalScope | None = None
    if args.changed_since:
        scope = scope_since_timestamp(issues, args.changed_since)
    elif args.since_checkpoint:
        scope = load_checkpoint(
            args.since_checkpoint,
            issues,
            workspace_id=snapshot.workspace_id,
        )
    active_scope_ids = (
        frozenset(issue.id for issue in population if issue.id in scope.changed_ids)
        if scope is not None
        else None
    )
    provider = _provider(args.provider)
    cache_path, state_path = _workspace_paths(snapshot.workspace_id)
    phase_started = time.monotonic()
    vectors, cache_stats = _load_vectors(issues, provider, VectorCache(cache_path))
    embedding_ms = round((time.monotonic() - phase_started) * 1000)
    phase_started = time.monotonic()
    whole_record_index = SimilarityIndex(vectors)
    similarity_scoring_ms = round((time.monotonic() - phase_started) * 1000)
    similarity_index: SimilarityIndex | MultiViewSimilarityIndex = whole_record_index
    if args.semantic_view == "fields":
        phase_started = time.monotonic()
        similarity_index, field_cache_stats = _load_field_similarity_index(
            issues,
            provider,
            VectorCache(cache_path),
            whole_record_index,
        )
        cache_stats.update(field_cache_stats)
        embedding_ms += round((time.monotonic() - phase_started) * 1000)
    phase_started = time.monotonic()
    ranking = _candidate_evidence(
        population,
        issues,
        vectors,
        echo_threshold=args.echo_threshold,
        overlap_threshold=args.overlap_threshold,
        similarity_index=similarity_index,
        exception_margin=args.exception_margin,
        reciprocal_rank=args.reciprocal_rank,
        max_candidates_per_issue=args.max_candidates_per_issue,
        max_echoes_per_target=args.max_echoes_per_target,
        max_echo_alternatives_per_active=args.max_echo_alternatives_per_active,
        max_dependency_candidates_per_issue=args.max_dependency_candidates_per_issue,
        max_candidates=max_candidates,
        max_dependency_candidates=lane_caps["dependency"],
        max_echo_candidates=lane_caps["echo"],
        max_overlap_candidates=lane_caps["overlap"],
        lane_reservations=lane_reservations,
        eligible_issue_ids=active_scope_ids,
        objectives=objectives,
    )
    candidates = list(ranking.candidates)
    candidate_analysis_ms = round((time.monotonic() - phase_started) * 1000)
    phase_started = time.monotonic()
    packaging = package_candidate_batches(
        population,
        candidates,
        vectors,
        max_batch_size=args.size,
        similarity_index=whole_record_index,
    )
    batches = packaging.batches
    batching_ms = round((time.monotonic() - phase_started) * 1000)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    run_dir = args.output or state_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    model = _model_metadata(provider)
    snapshot_payload = asdict(snapshot)
    for index, review_batch in enumerate(batches, start=1):
        batch_issues = review_batch.issues
        member_ids = {issue.id for issue in batch_issues}
        batch_evidence = [
            item
            for item in candidates
            if item["issue_id"] in member_ids or item["related_issue_id"] in member_ids
        ]
        manifest = build_batch_manifest(
            run_id,
            index,
            [_issue_summary(issue) for issue in batch_issues],
            batch_evidence,
            REVIEW_RUBRIC,
            snapshot=snapshot_payload,
            model=model,
            cache=cache_stats,
            batch_kind=review_batch.kind,
            review_units=[{"issue_ids": list(unit)} for unit in review_batch.review_units],
        )
        manifests.append(manifest)
        _atomic_text(run_dir / f"batch-{index}.json", _json_text(manifest))
        _atomic_text(run_dir / f"batch-{index}.md", render_batch_markdown(manifest))
    summary_batches = [
        {
            "batch": item["batch"],
            "kind": item["kind"],
            "issue_ids": [issue["id"] for issue in item["issues"]],
            "review_units": item["review_units"],
        }
        for item in manifests
    ]
    ranking_warnings = list(snapshot.source_warnings)
    semantic_issue_cap_drops = (
        ranking.dropped_by_issue_cap - ranking.dropped_by_dependency_issue_cap
    )
    if semantic_issue_cap_drops:
        ranking_warnings.append(
            f"Per-issue semantic candidate cap omitted {semantic_issue_cap_drops} qualified pairs."
        )
    if ranking.dropped_by_dependency_issue_cap:
        ranking_warnings.append(
            "Per-issue dependency allowance omitted "
            f"{ranking.dropped_by_dependency_issue_cap} qualified typed edges; "
            "compact structural summaries were retained."
        )
    if ranking.dropped_by_echo_target_cap:
        ranking_warnings.append(
            "Completed-target diversity cap omitted "
            f"{ranking.dropped_by_echo_target_cap} repeated echo pairs; "
            "the next qualified candidates were considered."
        )
    if ranking.dropped_by_run_cap:
        ranking_warnings.append(
            f"Run candidate cap omitted {ranking.dropped_by_run_cap} qualified pairs."
        )
    if ranking.dropped_by_lane_cap:
        ranking_warnings.append(
            f"Lane candidate budgets omitted {ranking.dropped_by_lane_cap} qualified pairs."
        )
    reciprocal_omissions = (ranking.reciprocal_diagnostics or {}).get("omitted", 0)
    if reciprocal_omissions:
        ranking_warnings.append(
            "Reciprocal evidence guard omitted "
            f"{reciprocal_omissions} pairs without discriminative local evidence."
        )
    if ranking.cap_replacements:
        ranking_warnings.append(
            f"Threshold comparison exposed {len(ranking.cap_replacements)} "
            "deterministic cap-driven replacements."
        )
    if packaging.diagnostics.cross_batch_candidate_edges:
        ranking_warnings.append(
            f"Hard batch limit split {packaging.diagnostics.cross_batch_candidate_edges} "
            "candidate edges across review artifacts."
        )
    queue_population = (
        [issue for issue in population if issue.id in active_scope_ids]
        if active_scope_ids is not None
        else population
    )
    population_ids = {issue.id for issue in queue_population}
    candidate_issue_ids = {
        identifier
        for item in candidates
        for identifier in (item["issue_id"], item["related_issue_id"])
        if identifier in population_ids
    }
    no_signal_ids = sorted(
        issue.id for issue in queue_population if issue.id not in candidate_issue_ids
    )
    unchanged_ids = (
        sorted(issue.id for issue in population if issue.id not in active_scope_ids)
        if active_scope_ids is not None
        else []
    )
    scope_payload = {
        "mode": scope.mode if scope else "full",
        "changed_active_count": (
            len(active_scope_ids) if active_scope_ids is not None else len(population_ids)
        ),
        "unchanged_active_count": len(unchanged_ids),
        "unknown_timestamp_count": len(scope.unknown_timestamp_ids) if scope else 0,
        "deleted_since_checkpoint_count": len(scope.deleted_ids) if scope else 0,
        "checkpoint_created_at": scope.checkpoint_created_at if scope else None,
    }
    review_budget = {
        "mode": "weekly" if args.weekly_review_budget is not None else "standard",
        "candidate_limit": max_candidates,
        "admitted_candidates": len(candidates),
        "omitted_candidates": ranking.dropped_by_run_cap,
        "selection_policy": "reserved-lane-access-then-priority-reflow",
        "reservation_order": ["dependency", "echo", "overlap"],
        "priority_order": [
            "typed-dependency",
            "high-confidence-completed-work-echo",
            "possible-overlap",
        ],
        "omitted_by_lane": {
            lane: metrics.dropped_by_run_cap for lane, metrics in (ranking.lanes or {}).items()
        },
        "lane_capacity": {
            lane: {
                "reserved": metrics.reserved,
                "admitted_to_reservation": metrics.admitted_to_reservation,
                "unused": metrics.unused_reserved,
            }
            for lane, metrics in (ranking.lanes or {}).items()
            if lane_reservations is not None
        },
        "code_surface_scope": "outside-semantic-candidate-limit",
    }
    payload = build_sweep_payload(
        run_id,
        candidates,
        summary_batches,
        snapshot=snapshot_payload,
        model=model,
        cache=cache_stats,
        filters={
            "status": sorted(statuses),
            "include_epics": args.include_epics,
            **({"review_objectives": sorted(objectives)} if objectives is not None else {}),
            **({"semantic_view": "fields"} if args.semantic_view == "fields" else {}),
            "incremental_scope": scope_payload,
        },
        thresholds={
            "completed_work_echo": args.echo_threshold,
            "possible_overlap": args.overlap_threshold,
        },
        candidate_policy={
            "exception_margin": args.exception_margin,
            "reciprocal_rank": args.reciprocal_rank,
            "max_per_issue": args.max_candidates_per_issue,
            "max_echoes_per_target": args.max_echoes_per_target,
            "max_echo_alternatives_per_active": args.max_echo_alternatives_per_active,
            "max_dependencies_per_issue": args.max_dependency_candidates_per_issue,
            "max_total": max_candidates,
            **({"review_objectives": sorted(objectives)} if objectives is not None else {}),
            **({"semantic_view": "fields"} if args.semantic_view == "fields" else {}),
            "review_budget": review_budget,
            "lane_caps": lane_caps,
            "qualified": ranking.qualified,
            "baseline_protected": ranking.baseline_protected,
            "reciprocal_diagnostics": ranking.reciprocal_diagnostics,
            "cap_replacements": list(ranking.cap_replacements),
            "dependency_funnel": asdict(ranking.dependency_funnel)
            if ranking.dependency_funnel
            else {},
            "lanes": {lane: asdict(metrics) for lane, metrics in (ranking.lanes or {}).items()},
            "dropped_by_lane_cap": ranking.dropped_by_lane_cap,
            "dropped_by_issue_cap": ranking.dropped_by_issue_cap,
            "dropped_by_dependency_issue_cap": ranking.dropped_by_dependency_issue_cap,
            "dropped_by_echo_target_cap": ranking.dropped_by_echo_target_cap,
            "echo_target_hubs": list(ranking.echo_target_hubs),
            "dropped_by_run_cap": ranking.dropped_by_run_cap,
        },
        capped_typed_dependencies=list(ranking.capped_typed_dependencies),
        warnings=ranking_warnings,
        no_signal={"count": len(no_signal_ids), "issue_ids": no_signal_ids},
        excluded={
            "count": len(excluded_epics) + len(unchanged_ids),
            "by_reason": {
                **({"epic": len(excluded_epics)} if excluded_epics else {}),
                **({"unchanged": len(unchanged_ids)} if unchanged_ids else {}),
            },
            "issue_ids": sorted([issue.id for issue in excluded_epics] + unchanged_ids),
        },
        target_batch_size=args.size,
        batch_diagnostics=asdict(packaging.diagnostics),
        duration_ms=round((time.monotonic() - started) * 1000),
        code_surface_analysis=code_surface_payload,
    )
    payload["timings_ms"] = {
        "acquisition": acquisition_ms,
        "embedding_and_cache": embedding_ms,
        "similarity_scoring": similarity_scoring_ms,
        "candidate_analysis": candidate_analysis_ms,
        "batching": batching_ms,
        "code_surface_analysis": code_surface_ms,
    }
    payload["output_directory"] = str(run_dir)
    _atomic_text(run_dir / "report.json", _json_text(payload))
    _atomic_text(run_dir / "report.md", render_sweep_markdown(payload))
    if args.write_checkpoint:
        _atomic_text(
            args.write_checkpoint,
            _json_text(build_checkpoint(issues, workspace_id=snapshot.workspace_id)),
        )
    sys.stdout.write(_json_text(payload) if args.as_json else render_sweep_markdown(payload))
    if not args.as_json:
        sys.stdout.write(f"\nArtifacts: {run_dir}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "neighbors":
            return _neighbors(args)
        if args.command == "readiness":
            return _readiness(args)
        if args.command == "capabilities":
            return _capabilities(args)
        if args.command == "doctor":
            return _doctor(args)
        if args.command == "collisions":
            return _collisions(args)
        return _sweep(args)
    except (TrackerError, OSError, RuntimeError, ValueError) as exc:
        print(f"embead: {exc}", file=sys.stderr)
        print("emBEADings made no tracker changes.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
