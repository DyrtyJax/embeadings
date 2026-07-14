import json
from datetime import UTC, datetime, timedelta

import pytest

from embead.incremental import (
    build_checkpoint,
    ensure_external_path,
    load_checkpoint,
    scope_since_timestamp,
)
from embead.models import IssueRecord

NOW = datetime(2026, 7, 14, 12, tzinfo=UTC)


def _issue(identifier: str, updated_at: str, title: str = "Private title") -> IssueRecord:
    return IssueRecord(identifier, title, status="open", updated_at=updated_at)


def test_timestamp_scope_is_strict_and_missing_timestamps_are_changed() -> None:
    issues = (
        _issue("before", "2026-07-01T00:00:00Z"),
        _issue("after", "2026-07-02T00:00:00Z"),
        _issue("unknown", ""),
    )
    scope = scope_since_timestamp(issues, "2026-07-01T12:00:00-00:00", now=NOW)
    assert scope.changed_ids == {"after", "unknown"}
    assert scope.unchanged_ids == {"before"}
    assert scope.unknown_timestamp_ids == {"unknown"}


@pytest.mark.parametrize("value", ["not-a-date", "2026-07-01T00:00:00", "2027-01-01T00:00:00Z"])
def test_invalid_or_future_timestamp_fails_closed(value: str) -> None:
    with pytest.raises(ValueError):
        scope_since_timestamp((), value, now=NOW)


def test_checkpoint_detects_new_changed_unchanged_and_deleted_without_text(tmp_path) -> None:
    original = (
        _issue("same", "2026-07-01T00:00:00Z", "same title"),
        _issue("changed", "2026-07-01T00:00:00Z", "old title"),
        _issue("deleted", "2026-07-01T00:00:00Z"),
    )
    checkpoint = build_checkpoint(original, workspace_id="workspace", created_at=NOW)
    encoded = json.dumps(checkpoint)
    assert "same title" not in encoded
    assert "old title" not in encoded
    path = tmp_path / "checkpoint.json"
    path.write_text(encoded)

    current = (
        original[0],
        _issue("changed", "2026-07-01T00:00:00Z", "new title"),
        _issue("new", "2026-07-02T00:00:00Z"),
    )
    scope = load_checkpoint(path, current, workspace_id="workspace", now=NOW + timedelta(seconds=1))
    assert scope.unchanged_ids == {"same"}
    assert scope.changed_ids == {"changed", "new"}
    assert scope.deleted_ids == {"deleted"}


def test_checkpoint_rejects_future_cross_workspace_and_malformed_state(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    payload = build_checkpoint((), workspace_id="other", created_at=NOW + timedelta(days=1))
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="different workspace"):
        load_checkpoint(path, (), workspace_id="workspace", now=NOW)

    payload["workspace_id"] = "workspace"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="future"):
        load_checkpoint(path, (), workspace_id="workspace", now=NOW)

    path.write_text("private malformed text")
    with pytest.raises(ValueError, match="unreadable or invalid") as error:
        load_checkpoint(path, (), workspace_id="workspace", now=NOW)
    assert "private malformed text" not in str(error.value)


def test_checkpoint_output_must_be_outside_repository(tmp_path) -> None:
    repository = tmp_path / "repo"
    beads = repository / ".beads"
    beads.mkdir(parents=True)
    with pytest.raises(ValueError, match="outside"):
        ensure_external_path(repository / "checkpoint.json", str(beads))
    ensure_external_path(tmp_path / "external.json", str(beads))
    with pytest.raises(ValueError, match="outside"):
        ensure_external_path(repository / "checkpoint.json", str(repository))
