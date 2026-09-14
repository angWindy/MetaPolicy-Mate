from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domain.schemas import RetrievalStatus, UserContext
from src.evaluation.pipeline import (
    DatasetValidationError,
    GoldenCase,
    StageObservation,
    evaluate_end_to_end,
    evaluate_rag_quality,
    evaluate_stage1,
    evaluate_stage2,
    load_golden_dataset,
    load_observations,
    production_gate,
    write_report,
)


def _case(**updates) -> GoldenCase:
    data = {
        "query": "Which rule applies?",
        "user_context": UserContext(user_id="eval-user", tenant_id="tenant-1").model_dump(),
        "expected_chunk_ids": ["c1", "c2"],
        "forbidden_chunk_ids": ["secret"],
        "reference_answer": "Rule c1 and c2 apply.",
        "expected_status": "sufficient",
        "expected_version_id": "v1",
        "category": "access",
        "should_abstain": False,
        "security_category": "none",
    }
    data.update(updates)
    data.setdefault(
        "should_abstain",
        data["expected_status"] in {"not_found", "forbidden", "conflict", "weak"},
    )
    data.setdefault("security_category", "none")
    return GoldenCase.model_validate(data)


def test_stage1_and_stage2_metrics_are_dataset_derived():
    case = _case()
    obs = StageObservation(
        retrieved_chunk_ids=["other", "c2", "c1"],
        ranked_chunk_ids=["c1", "c2", "other"],
        stage1_latency_ms=10,
        stage2_latency_ms=20,
    )
    stage1 = evaluate_stage1([case], [obs])
    stage2 = evaluate_stage2([case], [obs])
    assert stage1["recall_at_50"] == 1.0
    assert stage1["recall_at_100"] == 1.0
    assert stage1["mrr"] == 0.5
    assert stage1["unauthorized_retrieval_rate"] == 0.0
    assert stage2["precision_at_5"] == 0.4
    assert stage2["recall_at_5"] == 1.0
    assert stage2["top1_accuracy"] == 1.0
    assert stage2["ndcg_at_5"] is not None


def test_end_to_end_metrics_validate_citations_and_versions():
    case = _case()
    obs = StageObservation(
        final_context_ids=["c1", "c2"],
        citation_chunk_ids=["c1"],
        citation_versions={"c1": "v1"},
        answer="grounded",
        actual_status=RetrievalStatus.SUFFICIENT,
        faithfulness=0.9,
        answer_relevancy=0.8,
        answer_correctness=0.85,
        context_precision=1.0,
        context_recall=1.0,
    )
    metrics = evaluate_end_to_end([case], [obs])
    assert metrics["citation_id_validity"] == 1.0
    assert metrics["citation_correctness"] == 1.0
    assert metrics["version_correctness"] == 1.0
    assert metrics["abstention_accuracy"] == 1.0
    quality = evaluate_rag_quality([case], [obs])
    assert quality["answer_correctness"] == 0.85
    assert quality["context_precision"] == 1.0


def test_placeholder_dataset_is_rejected(tmp_path):
    path = tmp_path / "placeholder.jsonl"
    path.write_text(
        json.dumps(
            {
                "query": "q",
                "user_context": {"user_id": "u"},
                "expected_chunk_ids": [],
                "forbidden_chunk_ids": [],
                "reference_answer": "Thay bằng câu trả lời thật",
                "expected_status": "not_found",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError):
        load_golden_dataset(path)


def test_regression_dataset_has_real_retrieval_and_abstention_labels():
    dataset = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "eval"
        / "datasets"
        / "golden_questions.regression.jsonl"
    )

    cases = load_golden_dataset(dataset)

    assert len(cases) == 7
    assert any(case.expected_chunk_ids for case in cases)
    assert any(
        not case.expected_chunk_ids and case.expected_status is RetrievalStatus.NOT_FOUND
        for case in cases
    )
    assert all(not case.reference_answer.lower().startswith("thay bằng") for case in cases)


def test_abstention_cases_do_not_reduce_retrieval_metrics():
    retrieval_case = _case(expected_chunk_ids=["c1"])
    abstention_case = _case(
        expected_chunk_ids=[],
        expected_status="not_found",
        expected_version_id=None,
        should_abstain=True,
        security_category="abstention",
    )
    observations = [
        StageObservation(retrieved_chunk_ids=["c1"], ranked_chunk_ids=["c1"]),
        StageObservation(retrieved_chunk_ids=[], ranked_chunk_ids=[]),
    ]

    stage1 = evaluate_stage1([retrieval_case, abstention_case], observations)
    stage2 = evaluate_stage2([retrieval_case, abstention_case], observations)
    end_to_end = evaluate_end_to_end(
        [retrieval_case, abstention_case],
        [
            StageObservation(
                final_context_ids=["c1"],
                citation_chunk_ids=["c1"],
                answer="grounded",
                actual_status="sufficient",
            ),
            StageObservation(answer="", actual_status="not_found"),
        ],
    )

    assert stage1["recall_at_100"] == 1.0
    assert stage2["recall_at_5"] == 1.0
    assert end_to_end["citation_correctness"] == 1.0
    assert end_to_end["abstention_accuracy"] == 1.0


def test_production_gate_reports_fail_and_insufficient_without_fabrication():
    gate = production_gate(
        stage1={"recall_at_100": 0.96, "unauthorized_retrieval_rate": 0.0},
        stage2={"precision_at_5": 0.84},
        end_to_end={"citation_id_validity": 1.0},
        graph_gate_ok=True,
    )
    assert gate["status"] == "FAIL"
    assert gate["checks"]["precision_at_5"] is False
    insufficient = production_gate(
        stage1={"recall_at_100": None, "unauthorized_retrieval_rate": None},
        stage2={"precision_at_5": None},
        end_to_end={"citation_id_validity": None},
    )
    assert insufficient["status"] == "INSUFFICIENT_DATA"


def test_report_writes_json_and_markdown(tmp_path):
    from src.evaluation.pipeline import EvaluationReport

    report = EvaluationReport(
        dataset="real.jsonl",
        dataset_valid=True,
        status="INSUFFICIENT_DATA",
        failures=["runner observations missing"],
        gate={"status": "INSUFFICIENT_DATA"},
    )
    json_path = tmp_path / "report.json"
    md_path = tmp_path / "report.md"
    write_report(report, json_path, md_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "INSUFFICIENT_DATA"
    assert "INSUFFICIENT_DATA" in md_path.read_text(encoding="utf-8")


def test_observation_jsonl_round_trip_and_strict_validation(tmp_path):
    path = tmp_path / "observations.jsonl"
    observation = StageObservation(
        retrieved_chunk_ids=["c2", "c1"],
        ranked_chunk_ids=["c1", "c2"],
        final_context_ids=["c1"],
        citation_chunk_ids=["c1"],
        actual_status="sufficient",
    )
    path.write_text(
        json.dumps(observation.model_dump(mode="json")) + "\n",
        encoding="utf-8",
    )

    assert load_observations(path) == [observation]

    path.write_text('{"retrieved_chunk_ids": [], "unknown": true}\n', encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_observations(path)
