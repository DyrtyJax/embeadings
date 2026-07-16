import json

from embead import cli, doctor
from embead.models import WorkspaceSnapshot
from embead.provider import HashingProvider, Model2VecProvider


class ReadyBeadsAdapter:
    def workspace_snapshot(self) -> WorkspaceSnapshot:
        return WorkspaceSnapshot(
            "workspace-doctor",
            "1.0.5",
            "/private/repository/.beads",
            tracker_version="1.0.5",
        )


def test_doctor_is_corpus_free_and_reports_readiness(monkeypatch, tmp_path, capsys) -> None:
    class CorpusGuardAdapter(ReadyBeadsAdapter):
        def load(self):
            raise AssertionError("doctor must not load tracker records")

    monkeypatch.setattr(doctor, "BeadsAdapter", CorpusGuardAdapter)
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=16))
    monkeypatch.setattr(
        doctor,
        "_repository_check",
        lambda _path: {
            "status": "ready",
            "available": True,
            "context": "invocation-worktree",
            "revision": "abc123",
            "clean": True,
            "detail": "Git metadata is readable from the invoking worktree.",
        },
    )
    monkeypatch.setattr(doctor, "_vector_cache_path", lambda _identity: tmp_path / "missing")

    assert cli.main(["doctor", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["doctor_version"] == 1
    assert payload["read_only"] is True
    assert payload["corpus_loaded"] is False
    assert payload["status"] == "ready"
    assert payload["source"]["tracker_version"] == "1.0.5"
    assert payload["embedding"]["artifacts_cached"] is True
    assert payload["cache"] == {
        "detail": (
            "Workspace vector cache is uninitialized and will be created on first semantic run."
        ),
        "initialized": False,
        "status": "ready",
        "vector_files": 0,
        "workspace_identified": True,
    }


def test_linear_doctor_reports_auth_presence_without_secret(monkeypatch, capsys) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "private-linear-secret")
    monkeypatch.delenv("LINEAR_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=8))
    monkeypatch.setattr(
        doctor,
        "_repository_check",
        lambda _path: {
            "status": "attention",
            "available": False,
            "context": "unavailable",
            "revision": None,
            "clean": None,
            "detail": "No Git repository is available from the invocation directory.",
        },
    )

    assert cli.main(["--source", "linear", "--linear-team", "ENG", "doctor", "--json"]) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "attention"
    assert payload["source"] == {
        "configured": True,
        "credential": "api-key",
        "detail": "Linear team and API-key credential are configured; no network request was made.",
        "name": "linear",
        "status": "ready",
        "team_configured": True,
        "verified": False,
    }
    assert "private-linear-secret" not in output
    assert "ENG" not in output


def test_linear_doctor_blocks_on_conflicting_credentials(monkeypatch, capsys) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "one-secret")
    monkeypatch.setenv("LINEAR_ACCESS_TOKEN", "another-secret")
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=8))

    assert cli.main(["--source", "linear", "--linear-team", "ENG", "doctor", "--json"]) == 2

    output = capsys.readouterr().out
    assert json.loads(output)["source"]["credential"] == "conflict"
    assert "one-secret" not in output
    assert "another-secret" not in output


def test_offline_doctor_blocks_when_pinned_model_is_not_cached(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(doctor, "BeadsAdapter", ReadyBeadsAdapter)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty-hf-cache"))
    monkeypatch.setattr(
        doctor,
        "_repository_check",
        lambda _path: {
            "status": "ready",
            "available": True,
            "context": "invocation-worktree",
            "revision": "abc123",
            "clean": True,
            "detail": "Git metadata is readable from the invoking worktree.",
        },
    )
    monkeypatch.setattr(doctor, "_vector_cache_path", lambda _identity: tmp_path / "vectors")

    assert cli.main(["doctor", "--offline", "--json"]) == 2

    embedding = json.loads(capsys.readouterr().out)["embedding"]
    assert embedding["status"] == "blocked"
    assert embedding["artifacts_cached"] is False
    assert embedding["network_policy"] == "offline"
    assert embedding["model_id"] == Model2VecProvider.DEFAULT_MODEL_ID


def test_doctor_does_not_initialize_missing_cache(monkeypatch, tmp_path, capsys) -> None:
    vector_cache = tmp_path / "not-created"
    monkeypatch.setattr(doctor, "BeadsAdapter", ReadyBeadsAdapter)
    monkeypatch.setattr(cli, "_provider", lambda _name: HashingProvider(dimension=8))
    monkeypatch.setattr(doctor, "_vector_cache_path", lambda _identity: vector_cache)

    cli.main(["doctor", "--json"])
    capsys.readouterr()

    assert not vector_cache.exists()
