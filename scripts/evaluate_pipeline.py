"""Build a reproducible production-gate report from measured observations.

The CLI validates both golden labels and runner observations. It writes an
explicit ``INSUFFICIENT_DATA`` report instead of fabricating unavailable data.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluation.pipeline import (  # noqa: E402
    DatasetValidationError,
    EvaluationReport,
    StageObservation,
    compare_variants,
    evaluate_end_to_end,
    evaluate_stage1,
    evaluate_stage2,
    load_golden_dataset,
    load_observations,
    production_gate,
    write_report,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(math.ceil(percentile * len(ordered)) - 1, 0)
    return ordered[rank]


def _variant_observations(
    observations: list[StageObservation],
) -> dict[str, list[StageObservation]]:
    return {
        "hybrid_rrf": [
            observation.model_copy(
                update={"ranked_chunk_ids": observation.retrieved_chunk_ids}
            )
            for observation in observations
        ],
        "hybrid_reranker": observations,
    }


def _metrics_by_category(cases, observations) -> dict[str, dict[str, float | None]]:
    categories: dict[str, tuple[list, list]] = {}
    for case, observation in zip(cases, observations, strict=True):
        category_cases, category_observations = categories.setdefault(
            case.category,
            ([], []),
        )
        category_cases.append(case)
        category_observations.append(observation)
    output = {}
    for category, (category_cases, category_observations) in categories.items():
        stage1 = evaluate_stage1(category_cases, category_observations)
        stage2 = evaluate_stage2(category_cases, category_observations)
        end_to_end = evaluate_end_to_end(category_cases, category_observations)
        output[category] = {
            "cases": float(len(category_cases)),
            "recall_at_100": stage1["recall_at_100"],
            "precision_at_5": stage2["precision_at_5"],
            "citation_correctness": end_to_end["citation_correctness"],
            "abstention_accuracy": end_to_end["abstention_accuracy"],
        }
    return output


def _case_failures(cases, observations) -> list[str]:
    failures = []
    for index, (case, observation) in enumerate(
        zip(cases, observations, strict=True),
        start=1,
    ):
        expected = set(case.expected_chunk_ids)
        forbidden = set(case.forbidden_chunk_ids)
        reasons = []
        if expected and not expected.intersection(observation.ranked_chunk_ids[:5]):
            reasons.append("thiếu bằng chứng kỳ vọng trong top 5")
        leaked = forbidden.intersection(observation.retrieved_chunk_ids)
        if leaked:
            reasons.append(f"unauthorized retrieval: {sorted(leaked)}")
        if observation.citation_chunk_ids:
            invalid = set(observation.citation_chunk_ids) - set(
                observation.final_context_ids
            )
            if invalid:
                reasons.append(f"citation outside final context: {sorted(invalid)}")
        if (
            expected
            and observation.actual_status is not None
            and not expected.intersection(observation.citation_chunk_ids)
        ):
            reasons.append("thiếu bằng chứng kỳ vọng trong trích dẫn")
        if observation.abstained is not None and observation.abstained != case.should_abstain:
            reasons.append(
                "trạng thái từ chối không khớp: "
                f"kỳ vọng={case.should_abstain}, thực tế={observation.abstained}"
            )
        if reasons:
            failures.append(
                f"dòng {index} [{case.category}]: {'; '.join(reasons)}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Checkpoint 17 evaluation report")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--observations-jsonl", type=Path)
    parser.add_argument(
        "--report-json",
        type=Path,
        default=Path("docs/eval/results/retrieval_evaluation.json"),
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=Path("docs/eval/results/retrieval_evaluation.md"),
    )
    parser.add_argument("--index-version", default="unknown")
    parser.add_argument("--graph-gate-failed", action="store_true")
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--runtime-note", action="append", default=[])
    args = parser.parse_args()
    try:
        cases = load_golden_dataset(args.dataset)
    except DatasetValidationError as exc:
        report = EvaluationReport(
            dataset=str(args.dataset),
            dataset_valid=False,
            status="INSUFFICIENT_DATA",
            failures=[str(exc)],
            gate={"status": "INSUFFICIENT_DATA", "missing_metrics": ["golden_labels", "runner_observations"]},
        )
    else:
        if args.observations_jsonl is None:
            report = EvaluationReport(
                dataset=str(args.dataset),
                dataset_valid=True,
                status="INSUFFICIENT_DATA",
                failures=[f"Đã nạp {len(cases)} ca chuẩn nhưng chưa có quan sát Giai đoạn 1/Giai đoạn 2/E2E."],
                gate={"status": "INSUFFICIENT_DATA", "missing_metrics": ["runner_observations"]},
            )
        else:
            try:
                observations = load_observations(args.observations_jsonl)
                if len(cases) != len(observations):
                    raise DatasetValidationError(
                        "Golden cases and observations must have the same length "
                        f"({len(cases)} != {len(observations)})."
                    )
            except DatasetValidationError as exc:
                report = EvaluationReport(
                    dataset=str(args.dataset),
                    dataset_valid=True,
                    status="INSUFFICIENT_DATA",
                    failures=[str(exc)],
                    gate={
                        "status": "INSUFFICIENT_DATA",
                        "missing_metrics": ["valid_runner_observations"],
                    },
                )
            else:
                stage1 = evaluate_stage1(cases, observations)
                stage2 = evaluate_stage2(cases, observations)
                end_to_end = evaluate_end_to_end(cases, observations)
                stage1_latencies = [
                    observation.stage1_latency_ms
                    if observation.stage1_latency_ms is not None
                    else observation.latency_ms
                    for observation in observations
                ]
                stage2_latencies = [
                    observation.stage2_latency_ms
                    if observation.stage2_latency_ms is not None
                    else observation.latency_ms
                    for case, observation in zip(cases, observations, strict=True)
                    if case.expected_chunk_ids
                ]
                end_to_end_latencies = [
                    observation.latency_ms for observation in observations
                ]
                stage1.update(
                    {
                        "latency_p50_ms": _percentile(stage1_latencies, 0.50),
                        "latency_p95_ms": _percentile(stage1_latencies, 0.95),
                    }
                )
                stage2.update(
                    {
                        "latency_p50_ms": _percentile(stage2_latencies, 0.50),
                        "latency_p95_ms": _percentile(stage2_latencies, 0.95),
                    }
                )
                end_to_end.update(
                    {
                        "latency_p50_ms": _percentile(end_to_end_latencies, 0.50),
                        "latency_p95_ms": _percentile(end_to_end_latencies, 0.95),
                    }
                )
                variants = compare_variants(
                    cases,
                    _variant_observations(observations),
                )
                gate = production_gate(
                    stage1=stage1,
                    stage2=stage2,
                    end_to_end=end_to_end,
                    variants=variants,
                    graph_gate_ok=not args.graph_gate_failed,
                )
                failures = _case_failures(cases, observations)
                maximum_relevance_labels = max(
                    (len(case.expected_chunk_ids) for case in cases),
                    default=0,
                )
                if maximum_relevance_labels < 5:
                    failures.append(
                        "C-025: Không thể diễn giải cổng Precision@5 vì bộ dữ liệu "
                        "chưa gán nhãn đầy đủ năm đoạn liên quan cho mỗi câu hỏi có đáp án."
                    )
                report = EvaluationReport(
                    dataset=str(args.dataset),
                    dataset_valid=True,
                    status=gate["status"],
                    metrics={
                        "cases": float(len(cases)),
                        "observations": float(len(observations)),
                    },
                    stage_metrics={
                        "Giai đoạn 1 - Truy xuất ứng viên": stage1,
                        "Giai đoạn 2 - Xếp hạng lại": stage2,
                        "Giai đoạn 3 - RAG có kiểm soát": end_to_end,
                    },
                    by_category=_metrics_by_category(cases, observations),
                    variants=variants,
                    failures=failures,
                    gate=gate,
                    run_metadata={
                        "generated_at_utc": datetime.now(UTC).isoformat(),
                        "dataset_sha256": _sha256(args.dataset),
                        "observations_sha256": _sha256(args.observations_jsonl),
                        "index_version": args.index_version,
                        "maximum_relevance_labels_per_case": maximum_relevance_labels,
                    },
                    case_results=[
                        {
                            "row": index,
                            "category": case.category,
                            "expected_chunk_ids": case.expected_chunk_ids,
                            "retrieved_top_5": observation.retrieved_chunk_ids[:5],
                            "reranked_top_5": observation.ranked_chunk_ids[:5],
                            "citation_chunk_ids": observation.citation_chunk_ids,
                            "expected_abstention": case.should_abstain,
                            "actual_abstention": observation.abstained,
                        }
                        for index, (case, observation) in enumerate(
                            zip(cases, observations, strict=True),
                            start=1,
                        )
                    ],
                    limitations=list(args.runtime_note),
                )
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    write_report(report, args.report_json, args.report_md)
    print(report.status)
    return int(args.fail_on_regression and report.status == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
