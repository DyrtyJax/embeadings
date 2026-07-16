from dataclasses import FrozenInstanceError

import pytest

from embead.models import IssueRecord, canonical_text, content_hash, semantic_field_texts


def test_issue_record_is_immutable() -> None:
    issue = IssueRecord(id="bd-1", title="A title")
    with pytest.raises(FrozenInstanceError):
        issue.title = "changed"  # type: ignore[misc]


def test_canonical_text_includes_only_semantic_fields_and_normalizes() -> None:
    issue = IssueRecord(
        id="secret-1",
        title="  Improve search  \r\n",
        description="Use vectors.  \r\nOffline. ",
        status="open",
        labels=("private",),
        acceptance_criteria="No network",
        design="Local model",
        notes="Measure quality",
    )
    text = canonical_text(issue)
    assert text.count("Improve search") == 2
    assert "Use vectors.\nOffline." in text
    assert "No network" in text
    assert "Local model" in text
    assert "Measure quality" in text
    assert "secret-1" not in text
    assert "private" not in text
    assert "open" not in text


def test_canonical_text_truncates_each_field_deterministically() -> None:
    issue = IssueRecord(id="bd-1", title="abcdef", description="uvwxyz")
    assert canonical_text(issue, field_limit=3) == (
        "Title:\nabc\n\nTitle emphasis:\nabc\n\nDescription:\nuvw"
    )
    with pytest.raises(ValueError):
        canonical_text(issue, field_limit=0)


def test_semantic_field_texts_are_addressable_and_exclude_notes() -> None:
    issue = IssueRecord(
        id="A",
        title="  Build command arguments  ",
        description="Construct argv.  \r\n",
        acceptance_criteria="",
        design="Use an argument builder.",
        notes="Historical command palette discussion.",
    )

    assert semantic_field_texts(issue) == {
        "title": "Build command arguments",
        "description": "Construct argv.",
        "design": "Use an argument builder.",
    }


def test_content_hash_is_stable_and_invalidated_by_embedding_inputs() -> None:
    issue = IssueRecord(id="bd-1", title="Semantic cache")
    same = content_hash(issue, model_id="local", model_revision="abc")
    assert same == content_hash(issue, model_id="local", model_revision="abc")
    assert len(same) == 64
    assert same != content_hash(issue, model_id="other", model_revision="abc")
    assert same != content_hash(issue, model_id="local", model_revision="def")
    assert same != content_hash(
        issue,
        model_id="local",
        model_revision="abc",
        canonicalization_version=2,
    )


def test_content_hash_rejects_unpinned_model() -> None:
    issue = IssueRecord(id="bd-1", title="Semantic cache")
    with pytest.raises(ValueError):
        content_hash(issue, model_id="local", model_revision="")
