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
    assert result["verification_anchor"] == {
        "category": "completed outcome",
        "operation": "persist",
        "entity_class": "session",
        "source_field": "title",
    }
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


def test_contract_anchor_distinguishes_repaired_invariant() -> None:
    left = issue(
        "demo-left",
        title="Validate dependency invariant",
        acceptance_criteria="Never retain a self dependency after parsing",
    )
    right = issue(
        "demo-right",
        title="Validate dependency invariant",
        acceptance_criteria="Prevent a self dependency regression",
        status="closed",
    )

    result = explain_candidate(
        left,
        right,
        kind="completed-work-echo",
        similarity=0.93,
        structural_context="dependency",
    )

    assert result["verification_anchor"] == {
        "category": "repaired invariant",
        "operation": "validate",
        "entity_class": "dependency",
        "source_field": "title",
    }
    assert "repaired invariant" in result["what_to_verify"]


def test_contract_anchor_distinguishes_ownership_and_implementation() -> None:
    ownership = explain_candidate(
        issue("owner-a", title="Transfer workflow ownership"),
        issue("owner-b", title="Transfer workflow ownership"),
        kind="possible-overlap",
        similarity=0.9,
        structural_context="dependency",
    )
    implementation = explain_candidate(
        issue("impl-a", title="Configure cache backend", design="Choose provider architecture"),
        issue("impl-b", title="Configure cache backend", design="Choose provider architecture"),
        kind="possible-overlap",
        similarity=0.9,
        structural_context="none recorded",
    )

    assert ownership["verification_anchor"]["category"] == "transferred ownership"
    assert implementation["verification_anchor"]["category"] == "implementation choice"


def test_contract_anchor_never_copies_adversarial_free_form_tokens() -> None:
    secrets = (
        "sk-live-SUPERSECRET",
        "customer-merger-codename",
        "internal.example.private",
    )
    body = " ".join(secrets)
    result = explain_candidate(
        issue("safe-a", title="Validate dependency", description=body),
        issue("safe-b", title="Validate dependency", description=body),
        kind="possible-overlap",
        similarity=0.95,
        structural_context="dependency",
    )

    rendered = str(result)
    assert result["verification_anchor"]["operation"] == "validate"
    assert result["verification_anchor"]["entity_class"] == "dependency"
    assert all(secret not in rendered for secret in secrets)
