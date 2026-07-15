"""Strictly read-only Linear GraphQL acquisition.

The adapter deliberately queries issues and the workspace relation collection separately. This
avoids one detail request per issue and gives relation canonicalization a single, deterministic
boundary before records enter the semantic ranking core.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any, Final, TypeAlias

from .models import DependencyLink, IssueRecord, WorkspaceSnapshot
from .trackers import TrackerError

LINEAR_GRAPHQL_ENDPOINT: Final[str] = "https://api.linear.app/graphql"
LINEAR_TRACKER_VERSION: Final[str] = "graphql-current"


class LinearError(TrackerError):
    """Raised when Linear cannot provide a safe, valid snapshot."""


GraphQLTransport: TypeAlias = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]

_CONTEXT_QUERY = """
query EmbeadLinearContext {
  organization { id }
}
"""

_TEAMS_QUERY = """
query EmbeadLinearTeams($first: Int!, $after: String) {
  teams(first: $first, after: $after, includeArchived: false) {
    nodes { id key name }
    pageInfo { hasNextPage endCursor }
  }
}
"""

_ISSUES_QUERY = """
query EmbeadLinearIssues($teamId: ID!, $first: Int!, $after: String) {
  issues(
    first: $first
    after: $after
    includeArchived: false
    orderBy: updatedAt
    filter: { team: { id: { eq: $teamId } } }
  ) {
    nodes {
      id
      identifier
      title
      description
      priority
      updatedAt
      state { name type }
      parent { identifier }
      labels(first: 50) {
        nodes { name }
        pageInfo { hasNextPage }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

_RELATIONS_QUERY = """
query EmbeadLinearRelations($first: Int!, $after: String) {
  issueRelations(first: $first, after: $after, includeArchived: false) {
    nodes {
      id
      type
      issue { identifier }
      relatedIssue { identifier }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

_RELATION_TYPES = {
    "blocks": "blocks",
    "duplicate": "duplicate-of",
    "related": "relates-to",
    "similar": "similar-to",
}
_RELATION_PRIORITY = {"blocks": 0, "duplicate-of": 1, "relates-to": 2, "similar-to": 3}
_SYMMETRIC_RELATIONS = frozenset({"relates-to", "similar-to"})
_CLOSED_STATE_TYPES = frozenset({"completed", "canceled", "cancelled", "duplicate"})


class _HTTPTransport:
    """Small stdlib GraphQL client that refuses mutation operations."""

    def __init__(
        self,
        authorization: str,
        *,
        endpoint: str = LINEAR_GRAPHQL_ENDPOINT,
        timeout: float = 30.0,
    ) -> None:
        if not authorization.strip():
            raise LinearError("Linear authorization must not be empty")
        self._authorization = authorization
        self._endpoint = endpoint
        self._timeout = timeout

    def __call__(self, query: str, variables: Mapping[str, Any]) -> Mapping[str, Any]:
        operation = query.lstrip()
        if not operation.startswith("query "):
            raise LinearError("Linear adapter refused a non-query GraphQL operation")
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps({"query": query, "variables": dict(variables)}).encode("utf-8"),
            headers={
                "Authorization": self._authorization,
                "Content-Type": "application/json",
                "User-Agent": "embeadings/0.3.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LinearError(f"Linear GraphQL request failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise LinearError("Linear GraphQL request could not connect") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LinearError("Linear GraphQL returned malformed JSON") from exc
        if not isinstance(payload, Mapping):
            raise LinearError("Linear GraphQL response must be an object")
        errors = payload.get("errors")
        if errors:
            messages = [
                str(item.get("message", "unknown error"))
                for item in errors
                if isinstance(item, Mapping)
            ]
            detail = "; ".join(messages)[:500] or "unknown error"
            raise LinearError(f"Linear GraphQL query failed: {detail}")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise LinearError("Linear GraphQL response contains no data object")
        return data


def _transport_from_environment() -> _HTTPTransport:
    api_key = os.environ.get("LINEAR_API_KEY", "").strip()
    access_token = os.environ.get("LINEAR_ACCESS_TOKEN", "").strip()
    if api_key and access_token:
        raise LinearError("set only one of LINEAR_API_KEY or LINEAR_ACCESS_TOKEN")
    if access_token:
        authorization = f"Bearer {access_token}"
    elif api_key:
        authorization = api_key
    else:
        raise LinearError("set LINEAR_API_KEY or LINEAR_ACCESS_TOKEN for Linear access")
    return _HTTPTransport(authorization, endpoint=LINEAR_GRAPHQL_ENDPOINT)


class LinearAdapter:
    """Team-scoped, query-only Linear adapter."""

    def __init__(
        self,
        *,
        team: str,
        transport: GraphQLTransport | None = None,
        page_size: int = 100,
    ) -> None:
        if not team.strip():
            raise LinearError("a Linear team ID, key, or exact name is required")
        if not 1 <= page_size <= 250:
            raise LinearError("Linear page size must be between 1 and 250")
        self._team = team.strip()
        self._transport = transport or _transport_from_environment()
        self._page_size = page_size

    def _query(self, query: str, variables: Mapping[str, Any]) -> Mapping[str, Any]:
        if not query.lstrip().startswith("query "):
            raise LinearError("Linear adapter refused a non-query GraphQL operation")
        result = self._transport(query, variables)
        if not isinstance(result, Mapping):
            raise LinearError("Linear transport returned a non-object result")
        return result

    def _paginate(
        self,
        query: str,
        connection_name: str,
        variables: Mapping[str, Any] | None = None,
    ) -> list[Mapping[str, Any]]:
        cursor: str | None = None
        nodes: list[Mapping[str, Any]] = []
        while True:
            payload = self._query(
                query,
                {**dict(variables or {}), "first": self._page_size, "after": cursor},
            )
            connection = payload.get(connection_name)
            if not isinstance(connection, Mapping):
                raise LinearError(f"Linear response contains no {connection_name} connection")
            page_nodes = connection.get("nodes")
            if not isinstance(page_nodes, Sequence) or isinstance(page_nodes, (str, bytes)):
                raise LinearError(f"Linear {connection_name} connection contains invalid nodes")
            for node in page_nodes:
                if not isinstance(node, Mapping):
                    raise LinearError(f"Linear {connection_name} node must be an object")
                nodes.append(node)
            page_info = connection.get("pageInfo")
            if not isinstance(page_info, Mapping):
                raise LinearError(f"Linear {connection_name} connection has no pageInfo")
            if not bool(page_info.get("hasNextPage")):
                return nodes
            next_cursor = page_info.get("endCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                raise LinearError(f"Linear {connection_name} pagination has no end cursor")
            if next_cursor == cursor:
                raise LinearError(f"Linear {connection_name} pagination cursor did not advance")
            cursor = next_cursor

    def _resolve_context(self) -> tuple[str, Mapping[str, Any]]:
        payload = self._query(_CONTEXT_QUERY, {})
        organization = payload.get("organization")
        if not isinstance(organization, Mapping):
            raise LinearError("Linear response contains no organization")
        organization_id = _required_string(organization, "id", subject="organization")
        teams = self._paginate(_TEAMS_QUERY, "teams")
        needle = self._team.casefold()
        matches = [
            team
            for team in teams
            if any(
                isinstance(team.get(field), str) and str(team[field]).casefold() == needle
                for field in ("id", "key", "name")
            )
        ]
        if not matches:
            raise LinearError("Linear team was not found or is not accessible")
        if len(matches) > 1:
            raise LinearError("Linear team name is ambiguous; use its ID or key")
        return organization_id, matches[0]

    def load(self) -> tuple[WorkspaceSnapshot, tuple[IssueRecord, ...]]:
        organization_id, team = self._resolve_context()
        team_id = _required_string(team, "id", subject="team")
        raw_issues = self._paginate(_ISSUES_QUERY, "issues", {"teamId": team_id})
        base_records, truncated_labels = _parse_issues(raw_issues)
        raw_relations = self._paginate(_RELATIONS_QUERY, "issueRelations")
        links_by_source, outside_count, collapsed_count = _canonical_relations(
            raw_relations,
            frozenset(record.id for record in base_records),
        )
        records = tuple(
            replace(
                record,
                dependencies=tuple(link.target_id for link in links_by_source[record.id]),
                dependency_links=links_by_source[record.id],
            )
            for record in base_records
        )
        relationship_types = Counter(
            link.relationship_type for record in records for link in record.dependency_links
        )
        warnings: list[str] = []
        if truncated_labels:
            warnings.append(
                "Linear labels exceeded the per-issue safety bound on one or more records."
            )
        if outside_count:
            warnings.append(
                f"Linear omitted {outside_count} relation(s) with endpoints outside the "
                "selected team."
            )
        if collapsed_count:
            warnings.append(
                f"Linear canonicalized {collapsed_count} redundant relation edge(s) by issue pair."
            )
        identity = hashlib.sha256(f"linear:{organization_id}:{team_id}".encode()).hexdigest()
        snapshot = WorkspaceSnapshot(
            workspace_id=identity,
            beads_version=None,
            workspace_path=None,
            dependency_count=sum(relationship_types.values()),
            dependency_type_counts=tuple(sorted(relationship_types.items())),
            acquisition_source="linear-graphql-api",
            live_issue_count=len(records),
            source_warnings=tuple(warnings),
            tracker_name="linear",
            tracker_version=LINEAR_TRACKER_VERSION,
        )
        return snapshot, records


def _required_string(value: Mapping[str, Any], key: str, *, subject: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate.strip():
        raise LinearError(f"Linear {subject} contains no valid {key}")
    return candidate.strip()


def _parse_issues(raw_issues: Sequence[Mapping[str, Any]]) -> tuple[tuple[IssueRecord, ...], int]:
    records: list[IssueRecord] = []
    truncated_labels = 0
    for raw in raw_issues:
        identifier = _required_string(raw, "identifier", subject="issue")
        title = _required_string(raw, "title", subject=f"issue {identifier}")
        state = raw.get("state")
        if not isinstance(state, Mapping):
            raise LinearError(f"Linear issue {identifier} contains no workflow state")
        state_type = _required_string(state, "type", subject=f"issue {identifier} state")
        labels_value = raw.get("labels")
        if not isinstance(labels_value, Mapping):
            raise LinearError(f"Linear issue {identifier} contains no labels connection")
        label_nodes = labels_value.get("nodes")
        if not isinstance(label_nodes, Sequence) or isinstance(label_nodes, (str, bytes)):
            raise LinearError(f"Linear issue {identifier} contains invalid labels")
        labels = []
        for label in label_nodes:
            if not isinstance(label, Mapping):
                raise LinearError(f"Linear issue {identifier} contains an invalid label")
            labels.append(_required_string(label, "name", subject="label"))
        label_page = labels_value.get("pageInfo")
        if isinstance(label_page, Mapping) and bool(label_page.get("hasNextPage")):
            truncated_labels += 1
        parent = raw.get("parent")
        parent_id = None
        if parent is not None:
            if not isinstance(parent, Mapping):
                raise LinearError(f"Linear issue {identifier} contains an invalid parent")
            parent_id = _required_string(parent, "identifier", subject="parent issue")
        description = raw.get("description")
        if description is not None and not isinstance(description, str):
            raise LinearError(f"Linear issue {identifier} contains an invalid description")
        updated_at = _required_string(raw, "updatedAt", subject=f"issue {identifier}")
        priority = raw.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, (int, float)):
            raise LinearError(f"Linear issue {identifier} contains an invalid priority")
        numeric_priority = int(priority)
        if numeric_priority != priority or not 0 <= numeric_priority <= 4:
            raise LinearError(f"Linear issue {identifier} contains an unsupported priority")
        records.append(
            IssueRecord(
                id=identifier,
                title=title,
                description=description or "",
                status=_status_from_state(state_type),
                issue_type="issue",
                priority=numeric_priority,
                labels=tuple(sorted(set(labels), key=str.casefold)),
                parent_id=parent_id,
                updated_at=updated_at,
            )
        )
    ids = [record.id for record in records]
    if len(ids) != len(set(ids)):
        raise LinearError("Linear returned duplicate issue identifiers")
    return tuple(sorted(records, key=lambda record: record.id)), truncated_labels


def _status_from_state(value: str) -> str:
    normalized = value.casefold()
    if normalized in _CLOSED_STATE_TYPES:
        return "closed"
    if normalized == "started":
        return "in_progress"
    if normalized in {"backlog", "unstarted"}:
        return "open"
    raise LinearError("Linear returned an unsupported workflow state type")


def _canonical_relations(
    raw_relations: Sequence[Mapping[str, Any]], issue_ids: frozenset[str]
) -> tuple[dict[str, tuple[DependencyLink, ...]], int, int]:
    selected: dict[tuple[str, str], tuple[int, str, str, str]] = {}
    outside_count = 0
    collapsed_count = 0
    for raw in raw_relations:
        source_value = raw.get("issue")
        target_value = raw.get("relatedIssue")
        if not isinstance(source_value, Mapping) or not isinstance(target_value, Mapping):
            raise LinearError("Linear issue relation contains invalid endpoints")
        source = _required_string(source_value, "identifier", subject="relation source")
        target = _required_string(target_value, "identifier", subject="relation target")
        if source == target:
            raise LinearError("Linear issue relation contains a self-dependency")
        raw_type = _required_string(raw, "type", subject="relation").casefold()
        relationship_type = _RELATION_TYPES.get(raw_type)
        if relationship_type is None:
            raise LinearError("Linear issue relation contains an unsupported type")
        if source not in issue_ids or target not in issue_ids:
            outside_count += 1
            continue
        if relationship_type in _SYMMETRIC_RELATIONS and target < source:
            source, target = target, source
        pair = tuple(sorted((source, target)))
        candidate = (_RELATION_PRIORITY[relationship_type], source, target, relationship_type)
        previous = selected.get(pair)
        if previous is not None:
            collapsed_count += 1
        if previous is None or candidate < previous:
            selected[pair] = candidate
    grouped: dict[str, list[DependencyLink]] = defaultdict(list)
    for _priority, source, target, relationship_type in selected.values():
        grouped[source].append(DependencyLink(source, target, relationship_type))
    result: dict[str, tuple[DependencyLink, ...]] = {}
    for identifier in issue_ids:
        result[identifier] = tuple(
            sorted(
                grouped[identifier],
                key=lambda link: (link.target_id, link.relationship_type, link.source_id),
            )
        )
    return result, outside_count, collapsed_count
