from embead.explain import explain_candidate
from embead.models import IssueRecord


def issue(identifier: str, **changes) -> IssueRecord:
    values = {
        "id": identifier,
        "title": "Persist authentication session",
        "description": "Store login tokens between browser restarts",
        "acceptance_criteria": "Users remain signed in after relaunch",
        "status": "open",
    }
    values.update(changes)
    return IssueRecord(**values)


def test_completed_echo_names_fields_lifecycle_and_contract() -> None:
    active = issue("demo-active")
    closed = issue("demo-closed", status="closed")

    result = explain_candidate(
        active,
        closed,
        kind="completed-work-echo",
        similarity=0.91,
        structural_context="none recorded",
    )

    assert result["pattern"] == "completed-work"
    assert "title" in result["why_surfaced"]
    assert "open to closed" in result["why_surfaced"]
    assert "demo-active" in result["what_to_verify"]
    assert "delivered outcome" in result["what_to_verify"]
    assert result["counterevidence"] == ["no structural relationship is recorded"]


def test_parent_child_is_explicit_counterevidence() -> None:
    parent = issue("demo-parent")
    child = issue("demo-child", parent_id="demo-parent")

    result = explain_candidate(
        parent,
        child,
        kind="possible-overlap",
        similarity=0.88,
        structural_context="parent/child",
    )

    assert result["pattern"] == "parent-child"
    assert any("parent/child" in item for item in result["counterevidence"])


def test_different_acceptance_criteria_are_counterevidence() -> None:
    left = issue("demo-left", acceptance_criteria="Refresh tokens after expiry")
    right = issue("demo-right", acceptance_criteria="Administrators can revoke device access")

    result = explain_candidate(
        left,
        right,
        kind="possible-overlap",
        similarity=0.84,
        structural_context="same parent auth",
    )

    assert any("acceptance criteria" in item for item in result["counterevidence"])
    assert result["field_evidence"]


def test_explanation_contains_no_issue_body_text() -> None:
    secret = "customer-codename-never-report"
    left = issue("demo-left", description=f"Store tokens for {secret}")
    right = issue("demo-right", description=f"Persist sessions for {secret}")

    result = explain_candidate(
        left,
        right,
        kind="possible-overlap",
        similarity=0.82,
        structural_context="none recorded",
    )

    assert secret not in str(result)
    assert all("shared_term_count" in item for item in result["field_evidence"])
