"""Side-effect-free environment diagnostics for the emBEADings CLI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from platformdirs import user_cache_path

from .beads import BeadsAdapter
from .provider import HashingProvider, Model2VecProvider
from .trackers import TrackerError


def diagnose(
    *,
    source: str,
    linear_team: str | None,
    provider: Model2VecProvider | HashingProvider,
    offline: bool,
) -> dict[str, Any]:
    """Inspect source, Git, model, and vector-cache readiness without changing state."""

    source_check, workspace_id = _source_check(source, linear_team)
    repository_check = _repository_check(Path.cwd())
    embedding_check = _embedding_check(provider, offline=offline)
    cache_check = _cache_check(workspace_id)
    checks = (source_check, repository_check, embedding_check, cache_check)
    statuses = {check["status"] for check in checks}
    overall = (
        "blocked" if "blocked" in statuses else "attention" if "attention" in statuses else "ready"
    )
    return {
        "doctor_version": 1,
        "status": overall,
        "read_only": True,
        "corpus_loaded": False,
        "source": source_check,
        "repository": repository_check,
        "embedding": embedding_check,
        "cache": cache_check,
    }


def _source_check(source: str, linear_team: str | None) -> tuple[dict[str, Any], str | None]:
    if source == "linear":
        return _linear_source_check(linear_team), None
    try:
        snapshot = BeadsAdapter().workspace_snapshot()
    except (TrackerError, OSError, RuntimeError, ValueError) as exc:
        return {
            "name": "beads",
            "status": "blocked",
            "configured": False,
            "verified": False,
            "detail": str(exc),
        }, None
    return {
        "name": "beads",
        "status": "ready",
        "configured": True,
        "verified": True,
        "tracker_version": snapshot.tracker_version or snapshot.beads_version,
        "workspace_identified": True,
        "detail": "Beads context and version are readable through the read-only adapter.",
    }, snapshot.workspace_id


def _linear_source_check(linear_team: str | None) -> dict[str, Any]:
    api_key = bool(os.environ.get("LINEAR_API_KEY", "").strip())
    access_token = bool(os.environ.get("LINEAR_ACCESS_TOKEN", "").strip())
    team_configured = bool(linear_team and linear_team.strip())
    if api_key and access_token:
        credential = "conflict"
        detail = "Set only one of LINEAR_API_KEY or LINEAR_ACCESS_TOKEN."
    elif api_key:
        credential = "api-key"
        detail = "Linear team and API-key credential are configured; no network request was made."
    elif access_token:
        credential = "access-token"
        detail = (
            "Linear team and access-token credential are configured; no network request was made."
        )
    else:
        credential = "missing"
        detail = "Set LINEAR_API_KEY or LINEAR_ACCESS_TOKEN."
    configured = team_configured and credential in {"api-key", "access-token"}
    if not team_configured:
        detail = "Set --linear-team or LINEAR_TEAM." if credential != "conflict" else detail
    return {
        "name": "linear",
        "status": "ready" if configured else "blocked",
        "configured": configured,
        "verified": False,
        "team_configured": team_configured,
        "credential": credential,
        "detail": detail,
    }


def _repository_check(path: Path) -> dict[str, Any]:
    root = _git_value(path, "rev-parse", "--show-toplevel")
    if root is None:
        return {
            "status": "attention",
            "available": False,
            "context": "unavailable",
            "revision": None,
            "clean": None,
            "detail": "No Git repository is available from the invocation directory.",
        }
    revision = _git_value(path, "rev-parse", "HEAD")
    status = _git_value(path, "status", "--porcelain=v1", "--untracked-files=normal")
    return {
        "status": "ready" if revision is not None and status is not None else "attention",
        "available": True,
        "context": "invocation-worktree",
        "revision": revision,
        "clean": status == "" if status is not None else None,
        "detail": "Git metadata is readable from the invoking worktree.",
    }


def _git_value(path: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *arguments],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _embedding_check(
    provider: Model2VecProvider | HashingProvider, *, offline: bool
) -> dict[str, Any]:
    if isinstance(provider, HashingProvider):
        return {
            "status": "ready",
            "model_id": provider.model_id,
            "model_revision": provider.model_revision,
            "artifacts_cached": True,
            "network_policy": "offline" if offline else "prefetch-allowed",
            "detail": "The hashing provider requires no model artifacts.",
        }
    model_dir = (
        _huggingface_cache_root()
        / f"models--{provider.model_id.replace('/', '--')}"
        / "snapshots"
        / provider.model_revision
    )
    cached = model_dir.is_dir() and any(model_dir.iterdir())
    status = "ready" if cached else "blocked" if offline else "attention"
    detail = (
        "Pinned model artifacts are present in the local Hugging Face cache."
        if cached
        else "Pinned model artifacts are absent; a semantic command may download them."
    )
    return {
        "status": status,
        "model_id": provider.model_id,
        "model_revision": provider.model_revision,
        "artifacts_cached": cached,
        "network_policy": "offline" if offline else "prefetch-allowed",
        "detail": detail,
    }


def _huggingface_cache_root() -> Path:
    explicit = os.environ.get("HF_HUB_CACHE", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    home = os.environ.get("HF_HOME", "").strip()
    if home:
        return Path(home).expanduser() / "hub"
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    cache_home = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return cache_home / "huggingface" / "hub"


def _cache_check(workspace_id: str | None) -> dict[str, Any]:
    if workspace_id is None:
        return {
            "status": "ready",
            "workspace_identified": False,
            "initialized": None,
            "vector_files": None,
            "detail": "Workspace-specific vector cache is resolved after source acquisition.",
        }
    cache_path = _vector_cache_path(workspace_id)
    initialized = cache_path.is_dir()
    vector_files = sum(1 for path in cache_path.glob("*/*.json") if path.is_file())
    return {
        "status": "ready",
        "workspace_identified": True,
        "initialized": initialized,
        "vector_files": vector_files,
        "detail": (
            "Workspace vector cache is initialized."
            if initialized
            else (
                "Workspace vector cache is uninitialized and will be created on first semantic run."
            )
        ),
    }


def _vector_cache_path(workspace_id: str) -> Path:
    return user_cache_path("embeadings") / "vectors" / workspace_id[:16]
