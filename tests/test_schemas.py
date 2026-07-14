from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from embead.reports import build_batch_manifest, build_neighbors_payload, build_sweep_payload

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas" / "v1"
EXAMPLES = ROOT / "examples"
SNAPSHOT = {
    "workspace_id": "synthetic-workspace",
    "beads_version": "1.0.5",
    "workspace_path": None,
}
MODEL = {"model_id": "synthetic-local-model", "model_revision": "example-revision"}
CACHE = {"hits": 2, "misses": 0}
ISSUE = {
    "id": "demo-1",
    "title": "Document token refresh",
    "status": "open",
    "priority": 2,
    "labels": ["documentation"],
    "parent_id": "demo-epic",
    "dependencies": [],
}
EVIDENCE = {
    "kind": "completed-work-echo",
    "issue_id": "demo-1",
    "related_issue_id": "demo-2",
    "similarity": 0.91,
    "structural_context": "same parent demo-epic",
    "verification_anchor": {
        "category": "completed outcome",
        "operation": "render",
        "entity_class": "report",
        "source_field": "acceptance criteria",
        "confidence": "high",
        "extraction_confidence": "high",
        "confidence_scope": "anchor-extraction",
        "specificity": "concrete-check",
        "generic_fallback": False,
    },
    "candidate_evidence": {
        "evidence_basis": "structurally-corroborated",
        "structural_corroboration": "shared-parent",
        "admission_path": "semantic-threshold",
        "uncertainty": "structural-corroboration-recorded",
    },
    "what_to_verify": "Confirm whether completed work changed the active scope.",
    "counterevidence": ["no direct dependency is recorded"],
}


def _load(directory: Path, name: str) -> dict[str, Any]:
    return json.loads((directory / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["neighbors", "batch", "sweep", "capabilities", "checkpoint"])
def test_schema_is_valid_draft_2020_12_and_accepts_example(name: str) -> None:
    schema = _load(SCHEMAS, f"{name}.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_load(EXAMPLES, f"{name}.json"))


def test_report_builders_produce_schema_valid_payloads() -> None:
    neighbor = {**ISSUE, "id": "demo-2", "similarity": 0.91}
    payloads = {
        "neighbors": build_neighbors_payload(
            ISSUE, [neighbor], snapshot=SNAPSHOT, model=MODEL, cache=CACHE
        ),
        "batch": build_batch_manifest(
            "synthetic-run-1",
            1,
            [ISSUE],
            [EVIDENCE],
            ["Verify against current source."],
            snapshot=SNAPSHOT,
            model=MODEL,
            cache=CACHE,
        ),
        "sweep": build_sweep_payload(
            "synthetic-run-1",
            [EVIDENCE],
            [{"batch": 1, "issue_ids": ["demo-1"]}],
            snapshot=SNAPSHOT,
            model=MODEL,
            cache=CACHE,
            filters={"status": ["open"]},
            thresholds={"completed_work_echo": 0.72},
            capped_typed_dependencies=[
                {
                    "source_id": "demo-3",
                    "target_id": "demo-4",
                    "type": "blocks",
                    "drop_reason": "dependency-per-issue-cap",
                }
            ],
            no_signal={"count": 1, "issue_ids": ["demo-3"]},
            excluded={"count": 1, "by_reason": {"epic": 1}, "issue_ids": ["demo-epic"]},
            target_batch_size=5,
            duration_ms=12,
        ),
    }

    for report_type, payload in payloads.items():
        Draft202012Validator(_load(SCHEMAS, f"{report_type}.schema.json")).validate(payload)

    assert payloads["sweep"]["no_signal"]["count"] == 1
    assert payloads["sweep"]["excluded"]["by_reason"] == {"epic": 1}
    assert payloads["sweep"]["anchor_metrics"] == {
        "total": 1,
        "confidence": {"high": 1, "medium": 0, "low": 0},
        "specificity": {"concrete-check": 1, "category-check": 0, "generic": 0},
        "generic_fallback_count": 0,
        "generic_fallback_rate": 0.0,
    }
    assert payloads["batch"]["anchor_metrics"] == payloads["sweep"]["anchor_metrics"]


def test_version_one_allows_additive_fields() -> None:
    payload = _load(EXAMPLES, "sweep.json")
    payload["future_diagnostic"] = {"reason": "synthetic"}
    payload["candidates"][0]["future_evidence"] = ["synthetic"]

    Draft202012Validator(_load(SCHEMAS, "sweep.schema.json")).validate(payload)


def test_unsupported_version_and_weakened_policy_are_rejected() -> None:
    schema = _load(SCHEMAS, "neighbors.schema.json")
    example = _load(EXAMPLES, "neighbors.json")
    unsupported = copy.deepcopy(example)
    unsupported["schema_version"] = 2
    unsafe = copy.deepcopy(example)
    unsafe["policy"]["tracker_mutation_allowed"] = True

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(unsupported)
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(unsafe)
