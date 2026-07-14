"""Command-line interface for emBEADings."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_cache_path, user_state_path

from .analysis import SimilarityIndex, balanced_batches, nearest_neighbors
from .beads import BeadsAdapter, BeadsError
from .cache import VectorCache
from .explain import explain_candidate
from .models import IssueRecord, canonical_text
from .provider import HashingProvider, Model2VecProvider
from .ranking import CandidatePolicy, CandidateRanking, rank_candidates
from .reports import (
    build_batch_manifest,
    build_neighbors_payload,
    build_sweep_payload,
    render_batch_markdown,
    render_neighbors_markdown,
    render_sweep_markdown,
)

ACTIVE_STATUSES = {"open", "in_progress", "blocked", "deferred"}
REVIEW_RUBRIC = (
    "Verify each candidate against current source, documentation, and shipped behavior.",
    "Record counterevidence when similar wording reflects different scope.",
    "Do not implement changes or mutate the tracker during this review.",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="embead",
        description="Find related Beads work without changing your tracker.",
        epilog="Read-only • Issue text is embedded locally by default.",
    )
    parser.add_argument("--version", action="version", version="embead 0.1.0")
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
    sweep.add_argument("--size", type=int, default=9)
    sweep.add_argument(
        "--status",
        action="append",
        help="Include a stored status (repeatable; defaults to all active work)",
    )
    sweep.add_argument("--echo-threshold", type=float, default=0.72)
    sweep.add_argument("--overlap-threshold", type=float, default=0.82)
    _candidate_policy_arguments(sweep)
    sweep.add_argument("--output", type=Path)
    sweep.add_argument("--json", action="store_true", dest="as_json")

    batch = subparsers.add_parser("batch", help="Alias for a synchronous sweep")
    batch.add_argument("--size", type=int, default=9)
    batch.add_argument("--status", action="append")
    batch.add_argument("--echo-threshold", type=float, default=0.72)
    batch.add_argument("--overlap-threshold", type=float, default=0.82)
    _candidate_policy_arguments(batch)
    batch.add_argument("--output", type=Path)
    batch.add_argument("--json", action="store_true", dest="as_json")
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
    parser.add_argument("--max-candidates", type=int, default=250)


def _provider(name: str) -> Model2VecProvider | HashingProvider:
    if name == "hashing":
        return HashingProvider()
    return Model2VecProvider()


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


def _structural_context(left: IssueRecord, right: IssueRecord) -> str:
    if left.parent_id and left.parent_id == right.parent_id:
        return f"same parent {left.parent_id}"
    if right.id in left.dependencies:
        return f"{left.id} depends on {right.id}"
    if left.id in right.dependencies:
        return f"{right.id} depends on {left.id}"
    if left.parent_id == right.id or right.parent_id == left.id:
        return "parent/child"
    return "none recorded"


def _issue_summary(issue: IssueRecord) -> dict[str, Any]:
    return {
        "id": issue.id,
        "title": issue.title,
        "status": issue.status,
        "priority": issue.priority,
        "labels": list(issue.labels),
        "parent_id": issue.parent_id,
        "dependencies": list(issue.dependencies),
    }


def _model_metadata(provider: Model2VecProvider | HashingProvider) -> dict[str, str]:
    return {"model_id": provider.model_id, "model_revision": provider.model_revision}


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
    snapshot, issues = BeadsAdapter().load()
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
    similarity_index: SimilarityIndex | None = None,
    exception_margin: float = 0.08,
    reciprocal_rank: int = 5,
    max_candidates_per_issue: int = 3,
    max_candidates: int = 250,
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
            max_total=max_candidates,
        ),
    )
    by_id = {issue.id: issue for issue in all_issues}
    explained = []
    for candidate in ranking.candidates:
        left = by_id[candidate["issue_id"]]
        right = by_id[candidate["related_issue_id"]]
        explained.append(
            {
                **candidate,
                **explain_candidate(
                    left,
                    right,
                    kind=candidate["kind"],
                    similarity=candidate["similarity"],
                    structural_context=candidate["structural_context"],
                ),
            }
        )
    return CandidateRanking(
        candidates=tuple(explained),
        qualified=ranking.qualified,
        dropped_by_issue_cap=ranking.dropped_by_issue_cap,
        dropped_by_run_cap=ranking.dropped_by_run_cap,
    )


def _sweep(args: argparse.Namespace) -> int:
    if args.size < 1:
        raise ValueError("--size must be positive")
    policy = CandidatePolicy(
        echo_threshold=args.echo_threshold,
        overlap_threshold=args.overlap_threshold,
        exception_margin=args.exception_margin,
        reciprocal_rank=args.reciprocal_rank,
        max_per_issue=args.max_candidates_per_issue,
        max_total=args.max_candidates,
    )
    policy.validate()
    started = time.monotonic()
    phase_started = started
    snapshot, issues = BeadsAdapter().load()
    acquisition_ms = round((time.monotonic() - phase_started) * 1000)
    statuses = {status.casefold() for status in (args.status or ACTIVE_STATUSES)}
    population = [issue for issue in issues if issue.status.casefold() in statuses]
    provider = _provider(args.provider)
    cache_path, state_path = _workspace_paths(snapshot.workspace_id)
    phase_started = time.monotonic()
    vectors, cache_stats = _load_vectors(issues, provider, VectorCache(cache_path))
    embedding_ms = round((time.monotonic() - phase_started) * 1000)
    phase_started = time.monotonic()
    similarity_index = SimilarityIndex(vectors)
    similarity_scoring_ms = round((time.monotonic() - phase_started) * 1000)
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
        max_candidates=args.max_candidates,
    )
    candidates = list(ranking.candidates)
    candidate_analysis_ms = round((time.monotonic() - phase_started) * 1000)
    phase_started = time.monotonic()
    batches = balanced_batches(
        population,
        vectors,
        target_size=args.size,
        similarity_index=similarity_index,
    )
    batching_ms = round((time.monotonic() - phase_started) * 1000)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    run_dir = args.output or state_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    model = _model_metadata(provider)
    snapshot_payload = asdict(snapshot)
    for index, batch_issues in enumerate(batches, start=1):
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
        )
        manifests.append(manifest)
        _atomic_text(run_dir / f"batch-{index}.json", _json_text(manifest))
        _atomic_text(run_dir / f"batch-{index}.md", render_batch_markdown(manifest))
    summary_batches = [
        {"batch": item["batch"], "issue_ids": [issue["id"] for issue in item["issues"]]}
        for item in manifests
    ]
    ranking_warnings = []
    if ranking.dropped_by_issue_cap:
        ranking_warnings.append(
            f"Per-issue candidate cap omitted {ranking.dropped_by_issue_cap} qualified pairs."
        )
    if ranking.dropped_by_run_cap:
        ranking_warnings.append(
            f"Run candidate cap omitted {ranking.dropped_by_run_cap} qualified pairs."
        )
    payload = build_sweep_payload(
        run_id,
        candidates,
        summary_batches,
        snapshot=snapshot_payload,
        model=model,
        cache=cache_stats,
        filters={"status": sorted(statuses)},
        thresholds={
            "completed_work_echo": args.echo_threshold,
            "possible_overlap": args.overlap_threshold,
        },
        candidate_policy={
            "exception_margin": args.exception_margin,
            "reciprocal_rank": args.reciprocal_rank,
            "max_per_issue": args.max_candidates_per_issue,
            "max_total": args.max_candidates,
            "qualified": ranking.qualified,
            "dropped_by_issue_cap": ranking.dropped_by_issue_cap,
            "dropped_by_run_cap": ranking.dropped_by_run_cap,
        },
        warnings=ranking_warnings,
        target_batch_size=args.size,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    payload["timings_ms"] = {
        "acquisition": acquisition_ms,
        "embedding_and_cache": embedding_ms,
        "similarity_scoring": similarity_scoring_ms,
        "candidate_analysis": candidate_analysis_ms,
        "batching": batching_ms,
    }
    payload["output_directory"] = str(run_dir)
    _atomic_text(run_dir / "report.json", _json_text(payload))
    _atomic_text(run_dir / "report.md", render_sweep_markdown(payload))
    sys.stdout.write(_json_text(payload) if args.as_json else render_sweep_markdown(payload))
    if not args.as_json:
        sys.stdout.write(f"\nArtifacts: {run_dir}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "neighbors":
            return _neighbors(args)
        return _sweep(args)
    except (BeadsError, OSError, RuntimeError, ValueError) as exc:
        print(f"embead: {exc}", file=sys.stderr)
        print("emBEADings made no tracker changes.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
