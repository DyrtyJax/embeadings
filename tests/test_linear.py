from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from embead import __version__
from embead.analysis import SimilarityIndex
from embead.linear import LinearAdapter, LinearError, _HTTPTransport, _transport_from_environment
from embead.ranking import CandidatePolicy, rank_candidates

TEAM_UUID = "123e4567-e89b-12d3-a456-426614174000"


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
        if "EmbeadLinearTeamById" in query:
            assert values == {"id": TEAM_UUID}
            return {"team": {"id": TEAM_UUID, "key": "ENG", "name": "Engineering"}}
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
                    "nodes": [{"id": TEAM_UUID, "key": "ENG", "name": "Engineering"}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        if "EmbeadLinearIssues" in query:
            assert values["teamId"] == TEAM_UUID
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
                        _relation("OPS-10", "ENG-2", "blocks"),
                        _relation("OPS-10", "OPS-11", "similar"),
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
    adapter = LinearAdapter(team="eng", transport=transport, page_size=2)

    with pytest.raises(LinearError, match="only after load"):
        _ = adapter.relation_diagnostics
    snapshot, records = adapter.load()

    assert snapshot.tracker_name == "linear"
    assert snapshot.tracker_version == "graphql-current"
    assert snapshot.beads_version is None
    assert snapshot.live_issue_count == 3
    assert snapshot.dependency_count == 2
    assert snapshot.dependency_type_counts == (("blocks", 1), ("relates-to", 1))
    assert snapshot.relation_diagnostics == adapter.relation_diagnostics
    assert snapshot.relation_diagnostics.omitted_relation_count == 3
    assert snapshot.source_warnings == (
        "Linear omitted 3 workspace relation(s) outside the selected team: 2 cross the team "
        "boundary (selected-to-external: relates-to=1; external-to-selected: blocks=1) and "
        "1 have neither endpoint in the team (similar-to=1); omitted types: blocks=1, "
        "relates-to=1, similar-to=1. External endpoint records are not fetched.",
        "Linear canonicalized 2 redundant relation edge(s) by issue pair.",
    )
    assert adapter.relation_diagnostics.raw_relation_count == 7
    assert adapter.relation_diagnostics.retained_relation_count == 2
    assert adapter.relation_diagnostics.retained_type_counts == (
        ("blocks", 1),
        ("relates-to", 1),
    )
    assert adapter.relation_diagnostics.collapsed_relation_count == 2
    assert adapter.relation_diagnostics.omitted_relation_count == 3
    assert adapter.relation_diagnostics.omitted_type_counts == (
        ("blocks", 1),
        ("relates-to", 1),
        ("similar-to", 1),
    )
    assert adapter.relation_diagnostics.boundary_relation_count == 2
    assert adapter.relation_diagnostics.outbound_boundary_type_counts == (("relates-to", 1),)
    assert adapter.relation_diagnostics.inbound_boundary_type_counts == (("blocks", 1),)
    assert adapter.relation_diagnostics.unrelated_external_relation_count == 1
    assert adapter.relation_diagnostics.unrelated_external_type_counts == (("similar-to", 1),)
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


def test_linear_adapter_resolves_exact_team_uuid_without_listing_teams() -> None:
    transport = FakeTransport()

    snapshot, _ = LinearAdapter(team=TEAM_UUID.upper(), transport=transport, page_size=2).load()

    assert snapshot.tracker_name == "linear"
    assert sum("EmbeadLinearTeamById" in query for query, _ in transport.calls) == 1
    assert sum("EmbeadLinearTeams" in query for query, _ in transport.calls) == 0


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
    assert request.get_header("User-agent") == f"embeadings/{__version__}"
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
