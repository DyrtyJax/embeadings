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
    assert "semantic similarity alone" in result["what_to_verify"]
    assert result["verification_anchor"] == {
        "category": "completed outcome",
        "outcome_or_invariant": "completed outcome",
        "operation": "persist",
        "action": "persist",
        "entity_class": "session",
        "entity": "session",
        "source_field": "title",
        "confidence": "high",
        "extraction_confidence": "high",
        "confidence_scope": "anchor-extraction",
        "specificity": "category-check",
        "generic_fallback": False,
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

    anchor = result["verification_anchor"]
    assert anchor["category"] == "repaired invariant"
    assert anchor["operation"] == "validate"
    assert anchor["entity_class"] == "dependency"
    assert anchor["source_field"] == "title"
    assert anchor["confidence"] == "high"
    assert anchor["generic_fallback"] is False
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


def test_ownership_requires_evidence_in_both_records() -> None:
    result = explain_candidate(
        issue("owner-a", title="Assign workflow owner"),
        issue("owner-b", title="Update workflow configuration"),
        kind="possible-overlap",
        similarity=0.86,
        structural_context="none recorded",
    )

    assert result["verification_anchor"]["category"] != "transferred ownership"


def test_safe_active_contract_survives_different_related_wording() -> None:
    result = explain_candidate(
        issue("active", title="Limit dependency queue"),
        issue("related", title="Avoid too many linked work items"),
        kind="possible-overlap",
        similarity=0.86,
        structural_context="dependency",
    )

    assert result["verification_anchor"]["action"] == "limit"
    assert result["verification_anchor"]["entity"] == "dependency"
    assert result["verification_anchor"]["confidence"] == "medium"
    assert result["verification_anchor"]["generic_fallback"] is False


def test_evaluation_shaped_fixture_materially_reduces_generic_fallbacks() -> None:
    # Mirrors the pilot's 200-candidate scale and its mix of tracker/review concerns without using
    # private text. Every output remains drawn from the finite safe vocabulary.
    templates = (
        ("Parse dependency records", "Reject invalid dependency relationships"),
        ("Rank review candidates", "Prioritize dependency candidates in the queue"),
        ("Render sweep report", "Display warnings in the report"),
        ("Cache embedding vectors", "Persist embedding cache between runs"),
        ("Validate report schema", "Reject invalid schema output"),
        ("Package singleton batches", "Group issue candidates into an envelope"),
        ("Filter epic issues", "Exclude epic records from the queue"),
        ("Export review artifacts", "Write batch artifacts for review"),
    )
    anchors = []
    for index in range(200):
        title, acceptance = templates[index % len(templates)]
        result = explain_candidate(
            issue(f"fixture-a-{index}", title=title, acceptance_criteria=acceptance),
            issue(f"fixture-b-{index}", title=title, acceptance_criteria=acceptance),
            kind="completed-work-echo" if index % 4 == 0 else "possible-overlap",
            similarity=0.85,
            structural_context="none recorded",
        )
        anchors.append(result["verification_anchor"])

    assert sum(anchor["generic_fallback"] for anchor in anchors) <= 10
    assert not any(anchor["operation"] == "satisfy" for anchor in anchors)
    assert not any(anchor["entity_class"] == "system behavior" for anchor in anchors)


def test_specificity_is_separate_from_extraction_fallback() -> None:
    concrete = explain_candidate(
        issue(
            "specific-a",
            title="Validate dependency",
            acceptance_criteria="Must validate dependency invariant in a test",
        ),
        issue(
            "specific-b",
            title="Validate dependency",
            acceptance_criteria="Must validate dependency invariant in a test",
        ),
        kind="possible-overlap",
        similarity=0.9,
        structural_context="none recorded",
    )["verification_anchor"]
    category = explain_candidate(
        issue("category-a", title="Configure cache backend", acceptance_criteria=""),
        issue("category-b", title="Configure cache backend", acceptance_criteria=""),
        kind="possible-overlap",
        similarity=0.9,
        structural_context="none recorded",
    )["verification_anchor"]
    broad = explain_candidate(
        issue("broad-a", title="Review workflow", acceptance_criteria=""),
        issue("broad-b", title="Review workflow", acceptance_criteria=""),
        kind="possible-overlap",
        similarity=0.9,
        structural_context="none recorded",
    )["verification_anchor"]

    assert concrete["specificity"] == "concrete-check"
    assert category["specificity"] == "category-check"
    assert broad["specificity"] == "generic"
    assert broad["generic_fallback"] is False
    assert broad["confidence_scope"] == "anchor-extraction"


def test_generic_anchor_abstains_from_concrete_claims() -> None:
    result = explain_candidate(
        issue(
            "generic-a",
            title="Discuss miscellaneous work",
            description="",
            acceptance_criteria="",
        ),
        issue(
            "generic-b",
            title="Discuss miscellaneous work",
            description="",
            acceptance_criteria="",
        ),
        kind="completed-work-echo",
        similarity=0.9,
        structural_context="none recorded",
    )

    assert result["verification_anchor"]["specificity"] == "generic"
    assert "generic local comparison" in result["what_to_verify"]
    assert "shared contract" not in result["what_to_verify"]
