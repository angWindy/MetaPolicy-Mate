from __future__ import annotations

import json

import pytest

from src.evaluation.ragas_adapter import (
    RagasInputRecord,
    build_evaluation_dataset,
    evaluate_id_metrics,
    load_ragas_input,
    require_external_approval,
)


def record(**updates) -> RagasInputRecord:
    value = {
        "case_id": "case-1",
        "user_input": "Ai phê duyệt?",
        "response": "Trưởng đơn vị phê duyệt.",
        "reference": "Trưởng đơn vị phê duyệt.",
        "retrieved_contexts": ["Trưởng đơn vị phê duyệt."],
        "reference_contexts": ["Trưởng đơn vị phê duyệt."],
        "retrieved_context_ids": ["c1"],
        "reference_context_ids": ["c1"],
        "citation_chunk_ids": ["c1"],
        "should_abstain": False,
        "security_category": "none",
    }
    value.update(updates)
    return RagasInputRecord.model_validate(value)


def test_ragas_input_rejects_misaligned_context_data():
    with pytest.raises(ValueError, match="equal length"):
        record(retrieved_context_ids=[])


def test_ragas_input_rejects_placeholders():
    with pytest.raises(ValueError, match="placeholder"):
        record(reference="INSUFFICIENT_DATA")


def test_load_ragas_input_rejects_duplicate_case_ids(tmp_path):
    path = tmp_path / "input.jsonl"
    row = record().model_dump(mode="json")
    path.write_text(
        json.dumps(row, ensure_ascii=False) + "\n" + json.dumps(row, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate"):
        load_ragas_input(path)


def test_answerable_scope_excludes_abstention_rows():
    abstention = record(
        case_id="case-2",
        response="Không đủ căn cứ.",
        retrieved_contexts=[],
        reference_contexts=[],
        retrieved_context_ids=[],
        reference_context_ids=[],
        citation_chunk_ids=[],
        should_abstain=True,
        security_category="abstention",
    )
    dataset = build_evaluation_dataset([record(), abstention], answerable_only=True)
    assert len(dataset) == 1


@pytest.mark.asyncio
async def test_real_ragas_id_metrics_run_offline():
    result = await evaluate_id_metrics([record()])
    assert result["ragas_version"] == "0.3.9"
    assert result["external_payload_sent"] is False
    assert result["metrics"] == {
        "id_based_context_precision": 1.0,
        "id_based_context_recall": 1.0,
    }


def test_external_ragas_requires_destination_specific_approval(monkeypatch):
    monkeypatch.delenv("RAGAS_EXTERNAL_EVAL_APPROVED", raising=False)
    monkeypatch.delenv("RAGAS_EXTERNAL_EVAL_DESTINATION", raising=False)
    with pytest.raises(PermissionError, match="RAGAS_EXTERNAL_EVAL_APPROVED"):
        require_external_approval("openai")
