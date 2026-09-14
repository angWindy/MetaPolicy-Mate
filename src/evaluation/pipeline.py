"""Stage-separated evaluation and production gating.

The module intentionally accepts observations from a caller-owned runner.  It
never treats the example dataset as a benchmark and never invents LLM-judge
scores when a judge has not been configured.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.domain.schemas import RetrievalStatus, UserContext


class DatasetValidationError(ValueError):
    """Raised when a golden dataset is missing real labels."""


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    user_context: UserContext
    expected_chunk_ids: list[str] = Field(default_factory=list)
    forbidden_chunk_ids: list[str] = Field(default_factory=list)
    reference_answer: str = Field(min_length=1)
    expected_status: RetrievalStatus
    expected_version_id: str | None = None
    as_of_date: date | None = None
    category: str = "uncategorized"
    should_abstain: bool
    security_category: str = Field(min_length=1)

    @model_validator(mode="after")
    def abstention_label_must_match_status(self) -> GoldenCase:
        abstention_statuses = {
            RetrievalStatus.NOT_FOUND,
            RetrievalStatus.FORBIDDEN,
            RetrievalStatus.CONFLICT,
            RetrievalStatus.WEAK,
        }
        if self.should_abstain != (self.expected_status in abstention_statuses):
            raise ValueError("should_abstain conflicts with expected_status.")
        return self


class StageObservation(BaseModel):
    """One runner observation; all metrics are derived from these fields."""

    model_config = ConfigDict(extra="forbid")

    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    retrieved_scores: dict[str, float] = Field(default_factory=dict)
    ranked_chunk_ids: list[str] = Field(default_factory=list)
    relevance_grades: dict[str, float] = Field(default_factory=dict)
    final_context_ids: list[str] = Field(default_factory=list)
    citation_chunk_ids: list[str] = Field(default_factory=list)
    citation_versions: dict[str, str] = Field(default_factory=dict)
    answer: str = ""
    actual_status: RetrievalStatus | None = None
    latency_ms: float = 0.0
    stage1_latency_ms: float | None = None
    stage2_latency_ms: float | None = None
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    answer_correctness: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    abstained: bool | None = None


@dataclass
class EvaluationReport:
    dataset: str
    dataset_valid: bool
    status: str
    metrics: dict[str, float | None] = field(default_factory=dict)
    by_category: dict[str, dict[str, float | None]] = field(default_factory=dict)
    variants: dict[str, dict[str, float | None]] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    gate: dict[str, Any] = field(default_factory=dict)
    run_metadata: dict[str, Any] = field(default_factory=dict)
    stage_metrics: dict[str, dict[str, float | None]] = field(default_factory=dict)
    case_results: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "dataset_valid": self.dataset_valid,
            "status": self.status,
            "metrics": self.metrics,
            "by_category": self.by_category,
            "variants": self.variants,
            "failures": self.failures,
            "gate": self.gate,
            "run_metadata": self.run_metadata,
            "stage_metrics": self.stage_metrics,
            "case_results": self.case_results,
            "limitations": self.limitations,
        }


def load_golden_dataset(path: str | Path) -> list[GoldenCase]:
    """Load only real, non-placeholder golden labels."""

    source = Path(path)
    cases: list[GoldenCase] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = GoldenCase.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise DatasetValidationError(f"Invalid golden row {line_number}: {exc}") from exc
        requires_retrieval = case.expected_status in {
            RetrievalStatus.SUFFICIENT,
            RetrievalStatus.PARTIAL,
        }
        if requires_retrieval and not case.expected_chunk_ids:
            raise DatasetValidationError(
                f"Row {line_number} expects retrieval but has no expected_chunk_ids."
            )
        if case.reference_answer.lower().startswith(("thay bằng", "replace with", "todo")):
            raise DatasetValidationError(f"Row {line_number} contains a placeholder reference_answer.")
        cases.append(case)
    if not cases:
        raise DatasetValidationError("Golden dataset is empty.")
    return cases


def load_observations(path: str | Path) -> list[StageObservation]:
    """Load runner observations from JSONL without accepting extra fields."""

    source = Path(path)
    observations: list[StageObservation] = []
    for line_number, line in enumerate(
        source.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            observation = StageObservation.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise DatasetValidationError(
                f"Invalid observation row {line_number}: {exc}"
            ) from exc
        observations.append(observation)
    if not observations:
        raise DatasetValidationError("Observation dataset is empty.")
    return observations


def recall_at_k(actual: Sequence[str], expected: set[str], k: int) -> float:
    return len(set(actual[:k]).intersection(expected)) / len(expected) if expected else 0.0


def precision_at_k(actual: Sequence[str], expected: set[str], k: int) -> float:
    return len(set(actual[:k]).intersection(expected)) / max(k, 1)


def reciprocal_rank(actual: Sequence[str], expected: set[str]) -> float:
    for index, chunk_id in enumerate(actual, start=1):
        if chunk_id in expected:
            return 1.0 / index
    return 0.0


def ndcg_at_k(actual: Sequence[str], expected: set[str], grades: Mapping[str, float], k: int) -> float:
    ranked = [float(grades.get(chunk_id, 1.0 if chunk_id in expected else 0.0)) for chunk_id in actual[:k]]
    ideal = sorted([float(grades.get(chunk_id, 1.0)) for chunk_id in expected], reverse=True)[:k]

    def dcg(values: Sequence[float]) -> float:
        return sum((2**value - 1) / math.log2(index + 2) for index, value in enumerate(values))

    ideal_score = dcg(ideal)
    return dcg(ranked) / ideal_score if ideal_score else 0.0


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def evaluate_stage1(cases: Sequence[GoldenCase], observations: Sequence[StageObservation]) -> dict[str, float | None]:
    if len(cases) != len(observations):
        raise ValueError("Cases and observations must have the same length.")
    recalls50 = []
    recalls100 = []
    mrr = []
    unauthorized = []
    latencies = []
    for case, obs in zip(cases, observations, strict=True):
        expected = set(case.expected_chunk_ids)
        forbidden = set(case.forbidden_chunk_ids)
        if expected:
            recalls50.append(recall_at_k(obs.retrieved_chunk_ids, expected, 50))
            recalls100.append(recall_at_k(obs.retrieved_chunk_ids, expected, 100))
            mrr.append(reciprocal_rank(obs.retrieved_chunk_ids, expected))
        unauthorized.append(float(bool(forbidden.intersection(obs.retrieved_chunk_ids))))
        latencies.append(obs.stage1_latency_ms if obs.stage1_latency_ms is not None else obs.latency_ms)
    return {
        "recall_at_50": _mean(recalls50),
        "recall_at_100": _mean(recalls100),
        "mrr": _mean(mrr),
        "unauthorized_retrieval_rate": _mean(unauthorized),
        "latency_ms": _mean(latencies),
    }


def evaluate_stage2(cases: Sequence[GoldenCase], observations: Sequence[StageObservation]) -> dict[str, float | None]:
    if len(cases) != len(observations):
        raise ValueError("Cases and observations must have the same length.")
    precision = []
    recall = []
    mrr = []
    ndcg = []
    top1 = []
    latencies = []
    for case, obs in zip(cases, observations, strict=True):
        expected = set(case.expected_chunk_ids)
        if not expected:
            continue
        precision.append(precision_at_k(obs.ranked_chunk_ids, expected, 5))
        recall.append(recall_at_k(obs.ranked_chunk_ids, expected, 5))
        mrr.append(reciprocal_rank(obs.ranked_chunk_ids[:5], expected))
        ndcg.append(ndcg_at_k(obs.ranked_chunk_ids, expected, obs.relevance_grades, 5))
        top1.append(float(bool(obs.ranked_chunk_ids and obs.ranked_chunk_ids[0] in expected)))
        latencies.append(obs.stage2_latency_ms if obs.stage2_latency_ms is not None else obs.latency_ms)
    return {
        "precision_at_5": _mean(precision),
        "recall_at_5": _mean(recall),
        "mrr_at_5": _mean(mrr),
        "ndcg_at_5": _mean(ndcg),
        "top1_accuracy": _mean(top1),
        "latency_ms": _mean(latencies),
    }


def evaluate_end_to_end(
    cases: Sequence[GoldenCase], observations: Sequence[StageObservation]
) -> dict[str, float | None]:
    if len(cases) != len(observations):
        raise ValueError("Cases and observations must have the same length.")
    citation_validity = []
    citation_correctness = []
    abstention = []
    version_correctness = []
    faithfulness = []
    relevancy = []
    for case, obs in zip(cases, observations, strict=True):
        citations = set(obs.citation_chunk_ids)
        context = set(obs.final_context_ids)
        citation_validity.append(float(citations.issubset(context)))
        expected = set(case.expected_chunk_ids)
        citation_correctness.append(
            float(bool(citations.intersection(expected))) if expected else float(not citations)
        )
        should_abstain = case.expected_status in {
            RetrievalStatus.NOT_FOUND,
            RetrievalStatus.FORBIDDEN,
            RetrievalStatus.CONFLICT,
            RetrievalStatus.WEAK,
        }
        is_abstained = (
            obs.abstained
            if obs.abstained is not None
            else (
                obs.actual_status
                in {
                    RetrievalStatus.NOT_FOUND,
                    RetrievalStatus.FORBIDDEN,
                    RetrievalStatus.CONFLICT,
                    RetrievalStatus.WEAK,
                }
                or not obs.answer.strip()
            )
        )
        abstention.append(float(should_abstain == is_abstained))
        if case.expected_version_id is None:
            version_correctness.append(None)
        else:
            version_correctness.append(
                float(all(obs.citation_versions.get(chunk_id) == case.expected_version_id for chunk_id in citations))
            )
        if obs.faithfulness is not None:
            faithfulness.append(obs.faithfulness)
        if obs.answer_relevancy is not None:
            relevancy.append(obs.answer_relevancy)
    measured_versions = [value for value in version_correctness if value is not None]
    return {
        "faithfulness": _mean(faithfulness),
        "citation_correctness": _mean(citation_correctness),
        "citation_id_validity": _mean(citation_validity),
        "answer_relevancy": _mean(relevancy),
        "abstention_accuracy": _mean(abstention),
        "version_correctness": _mean(measured_versions),
    }


def evaluate_rag_quality(
    cases: Sequence[GoldenCase], observations: Sequence[StageObservation]
) -> dict[str, float | None]:
    """Quality-only report; security observations are evaluated separately."""

    if len(cases) != len(observations):
        raise ValueError("Cases and observations must have the same length.")
    end_to_end = evaluate_end_to_end(cases, observations)
    stage2 = evaluate_stage2(cases, observations)
    measured_context_precision = _mean(
        value.context_precision
        for value in observations
        if value.context_precision is not None
    )
    measured_context_recall = _mean(
        value.context_recall
        for value in observations
        if value.context_recall is not None
    )
    return {
        "answer_correctness": _mean(
            value.answer_correctness
            for value in observations
            if value.answer_correctness is not None
        ),
        "faithfulness": end_to_end["faithfulness"],
        "context_precision": (
            measured_context_precision
            if measured_context_precision is not None
            else stage2["precision_at_5"]
        ),
        "context_recall": (
            measured_context_recall
            if measured_context_recall is not None
            else stage2["recall_at_5"]
        ),
        "citation_correctness": end_to_end["citation_correctness"],
        "citation_validation": end_to_end["citation_id_validity"],
        "critical_abstention_correctness": end_to_end["abstention_accuracy"],
    }


def compare_variants(
    cases: Sequence[GoldenCase], variants: Mapping[str, Sequence[StageObservation]]
) -> dict[str, dict[str, float | None]]:
    """Compare dense, sparse, hybrid RRF and hybrid+rereanker observations."""

    return {name: evaluate_stage2(cases, observations) for name, observations in variants.items()}


def production_gate(
    *,
    stage1: Mapping[str, float | None],
    stage2: Mapping[str, float | None],
    end_to_end: Mapping[str, float | None],
    variants: Mapping[str, Mapping[str, float | None]] | None = None,
    graph_gate_ok: bool = True,
) -> dict[str, Any]:
    checks = {
        "recall_at_100": stage1.get("recall_at_100", 0.0) is not None and stage1.get("recall_at_100", 0.0) >= 0.95,
        "precision_at_5": stage2.get("precision_at_5", 0.0) is not None and stage2.get("precision_at_5", 0.0) >= 0.85,
        "citation_id_validity": end_to_end.get("citation_id_validity") == 1.0,
        "unauthorized_retrieval": stage1.get("unauthorized_retrieval_rate") == 0.0,
        "graph_no_bypass": graph_gate_ok,
    }
    if variants and "hybrid_rrf" in variants and "hybrid_reranker" in variants:
        baseline = variants["hybrid_rrf"].get("ndcg_at_5")
        reranked = variants["hybrid_reranker"].get("ndcg_at_5")
        checks["reranker_ndcg_improvement"] = baseline is not None and reranked is not None and reranked > baseline
    missing = [
        name
        for name, value in {
            "recall_at_100": stage1.get("recall_at_100"),
            "precision_at_5": stage2.get("precision_at_5"),
            "citation_id_validity": end_to_end.get("citation_id_validity"),
            "unauthorized_retrieval_rate": stage1.get("unauthorized_retrieval_rate"),
        }.items()
        if value is None
    ]
    status = "INSUFFICIENT_DATA" if missing else ("PASS" if all(checks.values()) else "FAIL")
    return {"status": status, "checks": checks, "missing_metrics": missing}


def write_report(report: EvaluationReport, json_path: str | Path, markdown_path: str | Path) -> None:
    Path(json_path).write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Báo cáo đánh giá truy xuất RAG",
        "",
        f"- Bộ dữ liệu: `{report.dataset}`",
        f"- Bộ dữ liệu hợp lệ: `{report.dataset_valid}`",
        f"- Trạng thái: **{report.status}**",
        "",
        "## Thông tin lần chạy",
        "",
    ]
    if report.run_metadata:
        lines.extend(
            f"- {key}: `{value}`" for key, value in report.run_metadata.items()
        )
    else:
        lines.append("- Không được cung cấp")
    lines.extend([
        "",
        "## Các chỉ số",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---:|",
    ])
    lines.extend(f"| {key} | {value} |" for key, value in report.metrics.items())
    for stage_name, stage_metrics in report.stage_metrics.items():
        lines.extend(
            [
                "",
                f"### {stage_name}",
                "",
                "| Chỉ số | Giá trị |",
                "|---|---:|",
                *(
                    f"| {key} | {value} |"
                    for key, value in stage_metrics.items()
                ),
            ]
        )
    if report.by_category:
        lines.extend(["", "## Kết quả theo nhóm", ""])
        for category, category_metrics in report.by_category.items():
            rendered_metrics = ", ".join(
                f"{key}={value}" for key, value in category_metrics.items()
            )
            lines.append(f"- `{category}`: {rendered_metrics}")
    if report.variants:
        lines.extend(["", "## So sánh biến thể", ""])
        for variant, variant_metrics in report.variants.items():
            rendered_metrics = ", ".join(
                f"{key}={value}" for key, value in variant_metrics.items()
            )
            lines.append(f"- `{variant}`: {rendered_metrics}")
    if report.limitations:
        lines.extend(
            ["", "## Giới hạn", "", *[f"- {item}" for item in report.limitations]]
        )
    if report.failures:
        lines.extend(["", "## Các trường hợp chưa đạt", "", *[f"- {item}" for item in report.failures]])
    lines.extend(["", "## Cổng chất lượng phát hành", "", f"```json\n{json.dumps(report.gate, indent=2)}\n```", ""])
    Path(markdown_path).write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "DatasetValidationError",
    "EvaluationReport",
    "GoldenCase",
    "StageObservation",
    "compare_variants",
    "evaluate_end_to_end",
    "evaluate_rag_quality",
    "evaluate_stage1",
    "evaluate_stage2",
    "load_golden_dataset",
    "load_observations",
    "ndcg_at_k",
    "production_gate",
    "recall_at_k",
    "write_report",
]
