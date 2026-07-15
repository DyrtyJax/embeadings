from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from embead.analysis import SimilarityIndex
from embead.linear import LinearAdapter, LinearError, _HTTPTransport, _transport_from_environment
from embead.ranking import CandidatePolicy, rank_candidates


def _issue(
    identifier: str,
    *,
    state: str,
    parent: str | None = None,
    labels: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "id": f"uuid-{identifier}",
        "identifier": identifier,
        "title": f"Synthetic {identifier}",
        "description": f"Implement src/{identifier.casefold()}.py",
        "priority": 2,
        "updatedAt": "2026-07-15T00:00:00Z",
        "state": {"name": state.title(), "type": state},
        "parent": {"identifier": parent} if parent else None,
        "labels": {
            "nodes": [{"name": label} for label in labels],
            "pageInfo": {"hasNextPage": False},
        },
    }


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, query: str, variables: Mapping[str, Any]) -> Mapping[str, Any]:
        assert query.lstrip().startswith("query ")
        assert "mutation" not in query.casefold()
        values = dict(variables)
        self.calls.append((query, values))
        cursor = values.get("after")
        if "EmbeadLinearContext" in query:
            return {"organization": {"id": "org-1"}}
        if "EmbeadLinearTeams" in query:
            if cursor is None:
                return {
                    "teams": {
                        "nodes": [{"id": "other", "key": "OPS", "name": "Operations"}],
                        "pageInfo": {"hasNextPage": True, "endCursor": "team-next"},
                    }
                }
            return {
                "teams": {
                    "nodes": [{"id": "team-1", "key": "ENG", "name": "Engineering"}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        if "EmbeadLinearIssues" in query:
            assert values["teamId"] == "team-1"
            if cursor is None:
                return {
                    "issues": {
                        "nodes": [
                            _issue("ENG-1", state="completed", labels=("Backend",)),
                            _issue("ENG-2", state="started", parent="ENG-1"),
                        ],
                        "pageInfo": {"hasNextPage": True, "endCursor": "issue-next"},
                    }
                }
            return {
                "issues": {
                    "nodes": [_issue("ENG-3", state="backlog")],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        if "EmbeadLinearRelations" in query:
            if cursor is None:
                return {
                    "issueRelations": {
                        "nodes": [
                            _relation("ENG-2", "ENG-3", "blocks"),
                            _relation("ENG-3", "ENG-2", "related"),
                            _relation("ENG-1", "ENG-3", "related"),
                        ],
                        "pageInfo": {"hasNextPage": True, "endCursor": "relation-next"},
                    }
                }
            return {
                "issueRelations": {
                    "nodes": [
                        _relation("ENG-3", "ENG-1", "related"),
                        _relation("ENG-1", "OPS-9", "related"),
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        raise AssertionError("unexpected query")


def _relation(source: str, target: str, kind: str) -> dict[str, Any]:
    return {
        "id": f"relation-{source}-{target}-{kind}",
        "type": kind,
        "issue": {"identifier": source},
        "relatedIssue": {"identifier": target},
    }


def test_linear_adapter_pages_maps_and_canonicalizes_relations() -> None:
    transport = FakeTransport()

    snapshot, records = LinearAdapter(team="eng", transport=transport, page_size=2).load()

    assert snapshot.tracker_name == "linear"
    assert snapshot.tracker_version == "graphql-current"
    assert snapshot.beads_version is None
    assert snapshot.live_issue_count == 3
    assert snapshot.dependency_count == 2
    assert snapshot.dependency_type_counts == (("blocks", 1), ("relates-to", 1))
    assert snapshot.source_warnings == (
        "Linear omitted 1 relation(s) with endpoints outside the selected team.",
        "Linear canonicalized 2 redundant relation edge(s) by issue pair.",
    )
    by_id = {record.id: record for record in records}
    assert by_id["ENG-1"].status == "closed"
    assert by_id["ENG-1"].labels == ("Backend",)
    assert by_id["ENG-2"].status == "in_progress"
    assert by_id["ENG-2"].parent_id == "ENG-1"
    assert by_id["ENG-3"].status == "open"
    assert [
        (link.source_id, link.target_id, link.relationship_type)
        for link in by_id["ENG-2"].dependency_links
    ] == [("ENG-2", "ENG-3", "blocks")]
    assert [
        (link.source_id, link.target_id, link.relationship_type)
        for link in by_id["ENG-1"].dependency_links
    ] == [("ENG-1", "ENG-3", "relates-to")]
    assert sum("EmbeadLinearTeams" in query for query, _ in transport.calls) == 2
    assert sum("EmbeadLinearIssues" in query for query, _ in transport.calls) == 2
    assert sum("EmbeadLinearRelations" in query for query, _ in transport.calls) == 2

    vectors = {record.id: [1.0, 0.0] for record in records}
    ranking = rank_candidates(
        [record for record in records if record.status != "closed"],
        records,
        SimilarityIndex(vectors),
        CandidatePolicy(),
    )
    assert ranking.dependency_funnel is not None
    ranking.dependency_funnel.validate()


def test_linear_adapter_resolves_exact_team_name() -> None:
    snapshot, _ = LinearAdapter(team="Engineering", transport=FakeTransport(), page_size=2).load()
    assert snapshot.tracker_name == "linear"


def test_linear_adapter_rejects_non_advancing_pagination() -> None:
    def transport(query: str, variables: Mapping[str, Any]) -> Mapping[str, Any]:
        if "Context" in query:
            return {"organization": {"id": "org"}}
        return {
            "teams": {
                "nodes": [],
                "pageInfo": {"hasNextPage": True, "endCursor": variables.get("after") or "x"},
            }
        }

    with pytest.raises(LinearError, match="cursor did not advance"):
        LinearAdapter(team="ENG", transport=transport).load()


def test_linear_adapter_rejects_self_relation() -> None:
    transport = FakeTransport()
    original = transport.__call__

    def with_self_relation(query: str, variables: Mapping[str, Any]) -> Mapping[str, Any]:
        if "EmbeadLinearRelations" in query:
            return {
                "issueRelations": {
                    "nodes": [_relation("ENG-1", "ENG-1", "related")],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        return original(query, variables)

    with pytest.raises(LinearError, match="self-dependency"):
        LinearAdapter(team="ENG", transport=with_self_relation, page_size=2).load()


def test_http_transport_refuses_mutation_before_network() -> None:
    transport = _HTTPTransport("secret")
    with pytest.raises(LinearError, match="non-query"):
        transport("mutation Unsafe { issueCreate { success } }", {})


def test_http_transport_keeps_authorization_out_of_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b'{"data":{"viewer":{"id":"viewer-1"}}}'

    def urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("embead.linear.urllib.request.urlopen", urlopen)
    result = _HTTPTransport("private-key")("query Safe { viewer { id } }", {"first": 1})

    request = captured["request"]
    assert result == {"viewer": {"id": "viewer-1"}}
    assert request.get_header("Authorization") == "private-key"
    body = json.loads(request.data)
    assert body["variables"] == {"first": 1}
    assert "private-key" not in request.data.decode()
    assert captured["timeout"] == 30.0


def test_http_transport_rejects_graphql_errors(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b'{"data":null,"errors":[{"message":"not authorized"}]}'

    monkeypatch.setattr(
        "embead.linear.urllib.request.urlopen", lambda _request, timeout: Response()
    )
    with pytest.raises(LinearError, match="not authorized"):
        _HTTPTransport("private-key")("query Safe { viewer { id } }", {})


def test_environment_auth_requires_exactly_one_token(monkeypatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("LINEAR_ACCESS_TOKEN", raising=False)
    with pytest.raises(LinearError, match="set LINEAR_API_KEY"):
        _transport_from_environment()

    monkeypatch.setenv("LINEAR_API_KEY", "key")
    monkeypatch.setenv("LINEAR_ACCESS_TOKEN", "token")
    with pytest.raises(LinearError, match="only one"):
        _transport_from_environment()
