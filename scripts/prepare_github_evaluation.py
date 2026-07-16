#!/usr/bin/env python3
"""Export public GitHub issues as a disposable Beads JSONL evaluation corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

QUERY = """
query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, after: $endCursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      nodes {
        number
        title
        body
        state
        url
        createdAt
        updatedAt
        closedAt
        labels(first: 100) { nodes { name } }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an external, uncommitted Beads JSONL corpus from public GitHub issues."
    )
    parser.add_argument("--repo", required=True, metavar="OWNER/NAME")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--body-limit", type=int, default=16_000)
    parser.add_argument("--limit", type=int, help="Bound issue count for a smoke test")
    return parser


def _fetch(repo: str) -> list[dict[str, Any]]:
    owner, separator, name = repo.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise ValueError("--repo must use OWNER/NAME")
    completed = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "--paginate",
            "--slurp",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-f",
            f"query={QUERY}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "GitHub issue export failed")
    pages = json.loads(completed.stdout)
    issues: list[dict[str, Any]] = []
    for page in pages:
        repository = (page.get("data") or {}).get("repository") or {}
        connection = repository.get("issues") or {}
        issues.extend(node for node in connection.get("nodes") or [] if node)
    return issues


def _issue_type(labels: list[str]) -> str:
    normalized = {label.casefold() for label in labels}
    if any("bug" in label or "regression" in label for label in normalized):
        return "bug"
    if any("feature" in label or "enhancement" in label for label in normalized):
        return "feature"
    return "task"


def _priority(labels: list[str]) -> int:
    text = " ".join(labels).casefold()
    if re.search(r"\b(?:p0|critical|blocker)\b", text):
        return 0
    if re.search(r"\b(?:p1|high priority|priority: high)\b", text):
        return 1
    if re.search(r"\b(?:p3|low priority|priority: low)\b", text):
        return 3
    return 2


def _records(
    repo: str,
    issues: list[dict[str, Any]],
    *,
    body_limit: int,
) -> list[dict[str, Any]]:
    if body_limit < 1:
        raise ValueError("--body-limit must be positive")
    name = repo.partition("/")[2]
    prefix = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "github"
    records = []
    for issue in sorted(issues, key=lambda item: int(item["number"])):
        labels = sorted(
            str(node["name"])
            for node in ((issue.get("labels") or {}).get("nodes") or [])
            if node and node.get("name")
        )
        closed = str(issue.get("state", "OPEN")).casefold() == "closed"
        records.append(
            {
                "id": f"{prefix}-gh-{int(issue['number'])}",
                "title": str(issue.get("title") or "Untitled GitHub issue"),
                "description": str(issue.get("body") or "")[:body_limit],
                "status": "closed" if closed else "open",
                "priority": _priority(labels),
                "issue_type": _issue_type(labels),
                "labels": labels,
                "dependencies": [],
                "created_at": issue.get("createdAt"),
                "updated_at": issue.get("updatedAt"),
                "closed_at": issue.get("closedAt"),
                "external_ref": issue.get("url"),
                "created_by": "github-public-evaluation-import",
            }
        )
    return records


def _write_external(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    destination = path.expanduser().resolve()
    if destination == root or root in destination.parents:
        raise ValueError("evaluation corpus output must be outside the emBEADings repository")
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    destination.write_text(rendered, encoding="utf-8")
    return {
        "issue_count": len(records),
        "active_count": sum(record["status"] == "open" for record in records),
        "closed_count": sum(record["status"] == "closed" for record in records),
        "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "output": str(destination),
    }


def main() -> int:
    args = _parser().parse_args()
    issues = _fetch(args.repo)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        issues = issues[: args.limit]
    records = _records(args.repo, issues, body_limit=args.body_limit)
    summary = {"repo": args.repo, **_write_external(args.output, records)}
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
