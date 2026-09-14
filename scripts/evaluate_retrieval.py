import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.schemas import EvidenceAction, RetrievalStatus  # noqa: E402
from src.evaluation.pipeline import (  # noqa: E402
    StageObservation,
    load_golden_dataset,
    recall_at_k,
)
from src.evaluation.regression_seed import seed_regression_corpus  # noqa: E402
from src.rag.config import RAGSettings  # noqa: E402
from src.rag.container import RAGContainer  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval and the governed RAG pipeline against a golden dataset."
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--observations-jsonl", type=Path)
    parser.add_argument("--seed-fixture", type=Path)
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--run-pipeline", action="store_true")
    parser.add_argument("--database-url")
    parser.add_argument("--qdrant-url")
    parser.add_argument("--qdrant-collection")
    parser.add_argument("--vector-backend", choices=("memory", "qdrant"))
    parser.add_argument("--data-dir", type=Path)
    return parser.parse_args()


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _citation_id(citation: object) -> str:
    if isinstance(citation, dict):
        return str(citation["chunk_id"])
    return str(getattr(citation, "chunk_id"))


def _citation_value(citation: object, key: str) -> object | None:
    if isinstance(citation, dict):
        return citation.get(key)
    return getattr(citation, key, None)


async def main() -> None:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cases = load_golden_dataset(args.dataset)
    overrides = {
        key: value
        for key, value in {
            "database_url": args.database_url,
            "qdrant_url": args.qdrant_url,
            "qdrant_collection": args.qdrant_collection,
            "vector_backend": args.vector_backend,
            "data_dir": args.data_dir,
            "app_env": "test",
            "generator_provider": "template",
            "embedding_provider": "hash",
        }.items()
        if value is not None
    }
    container = RAGContainer(RAGSettings(**overrides))
    if args.seed_fixture:
        await seed_regression_corpus(container, args.seed_fixture)
    warmed = await container.warm_index()
    retriever = container.retriever
    retrieval_recalls: list[float] = []
    retrieval_hits: list[float] = []
    unauthorized: list[float] = []
    status_matches: list[float] = []
    abstention_candidate_empty: list[float] = []
    latencies: list[float] = []
    pipeline_outcomes: list[float] = []
    pipeline_status_matches: list[float] = []
    pipeline_citation_correctness: list[float] = []
    pipeline_unauthorized: list[float] = []
    pipeline_latencies: list[float] = []
    observations: list[StageObservation] = []
    details = []
    for case in cases:
        evaluation_trace: dict = {}
        started = time.perf_counter()
        results = await retriever.search(
            case.query,
            case.user_context,
            case.as_of_date,
            evaluation_trace=evaluation_trace,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        retrieved_ids = [item.chunk_id for item in results]
        expected = set(case.expected_chunk_ids)
        forbidden = set(case.forbidden_chunk_ids)
        if expected:
            retrieval_recalls.append(recall_at_k(retrieved_ids, expected, len(retrieved_ids)))
            retrieval_hits.append(float(bool(expected.intersection(retrieved_ids))))
        unauthorized.append(float(bool(forbidden.intersection(retrieved_ids))))
        actual_status = RetrievalStatus.SUFFICIENT if results else RetrievalStatus.NOT_FOUND
        expects_results = case.expected_status in {RetrievalStatus.SUFFICIENT, RetrievalStatus.PARTIAL}
        if expects_results:
            status_matches.append(float(bool(results)))
        else:
            abstention_candidate_empty.append(float(not results))
        latencies.append(elapsed_ms)
        detail = {
            "query": case.query,
            "expected_status": case.expected_status.value,
            "actual_status": actual_status.value,
            "retrieved_chunk_ids": retrieved_ids,
            "retrieved_scores": {item.chunk_id: item.score for item in results},
            "expected_chunk_ids": case.expected_chunk_ids,
            "unauthorized_chunk_ids": sorted(forbidden.intersection(retrieved_ids)),
            "latency_ms": elapsed_ms,
            "evaluation_trace": evaluation_trace,
        }
        fused_ids = list(evaluation_trace.get("fused_chunk_ids") or retrieved_ids)
        reranked_ids = list(
            evaluation_trace.get("reranked_chunk_ids") or retrieved_ids
        )
        trace_latency = evaluation_trace.get("latency_ms") or {}
        stage1_latency_ms = sum(
            float(trace_latency.get(key) or 0.0)
            for key in ("policy_filter", "embedding", "search", "fusion")
        )
        stage2_latency_ms = float(trace_latency.get("rerank") or 0.0)
        observation_data = {
            "retrieved_chunk_ids": fused_ids,
            "retrieved_scores": dict(
                evaluation_trace.get("retrieved_scores") or {}
            ),
            "ranked_chunk_ids": reranked_ids,
            "relevance_grades": {
                chunk_id: 1.0 for chunk_id in case.expected_chunk_ids
            },
            "final_context_ids": retrieved_ids,
            "latency_ms": elapsed_ms,
            "stage1_latency_ms": stage1_latency_ms,
            "stage2_latency_ms": stage2_latency_ms,
        }
        if args.run_pipeline:
            pipeline_started = time.perf_counter()
            pipeline_result = await container.pipeline.ainvoke(
                {
                    "query": case.query,
                    "user": case.user_context,
                    "as_of_date": case.as_of_date,
                    "request_id": str(uuid.uuid4()),
                }
            )
            pipeline_elapsed_ms = (time.perf_counter() - pipeline_started) * 1000
            pipeline_status = RetrievalStatus(
                pipeline_result.get("evidence_status", RetrievalStatus.NOT_FOUND)
            )
            pipeline_action = EvidenceAction(
                pipeline_result.get("evidence_decision", EvidenceAction.ABSTAIN)
            )
            citation_ids = [
                _citation_id(citation)
                for citation in pipeline_result.get("citations", [])
            ]
            citation_versions = {
                _citation_id(citation): str(version_id)
                for citation in pipeline_result.get("citations", [])
                if (
                    version_id := _citation_value(citation, "version_id")
                ) is not None
            }
            expects_results = case.expected_status in {
                RetrievalStatus.SUFFICIENT,
                RetrievalStatus.PARTIAL,
            }
            generated_with_citation = (
                pipeline_action is EvidenceAction.GENERATE and bool(citation_ids)
            )
            pipeline_outcomes.append(float(generated_with_citation == expects_results))
            pipeline_status_matches.append(float(pipeline_status is case.expected_status))
            pipeline_citation_correctness.append(
                float(bool(expected.intersection(citation_ids)))
                if expected
                else float(not citation_ids)
            )
            pipeline_unauthorized.append(
                float(bool(forbidden.intersection(citation_ids)))
            )
            pipeline_latencies.append(pipeline_elapsed_ms)
            detail["pipeline"] = {
                "evidence_status": pipeline_status.value,
                "evidence_action": pipeline_action.value,
                "citation_chunk_ids": citation_ids,
                "unauthorized_citation_ids": sorted(forbidden.intersection(citation_ids)),
                "confidence": pipeline_result.get("confidence", "low"),
                "evidence_reason": pipeline_result.get("evidence_reason", ""),
                "latency_ms": pipeline_elapsed_ms,
            }
            observation_data.update(
                {
                    "final_context_ids": [
                        str(getattr(context, "chunk_id", ""))
                        if not isinstance(context, dict)
                        else str(context.get("chunk_id", ""))
                        for context in pipeline_result.get("final_contexts", [])
                    ]
                    or retrieved_ids,
                    "citation_chunk_ids": citation_ids,
                    "citation_versions": citation_versions,
                    "answer": str(pipeline_result.get("answer") or ""),
                    "actual_status": pipeline_status,
                    "latency_ms": pipeline_elapsed_ms,
                    "abstained": pipeline_action is not EvidenceAction.GENERATE,
                }
            )
        observations.append(StageObservation.model_validate(observation_data))
        details.append(detail)
    report = {
        "cases": len(cases),
        "retrieval_cases": len(retrieval_recalls),
        "warmed_index_chunks": warmed,
        "recall_at_final_k": _mean(retrieval_recalls),
        "hit_rate_at_final_k": _mean(retrieval_hits),
        "unauthorized_retrieval_rate": _mean(unauthorized),
        "retrieval_presence_accuracy": _mean(status_matches),
        "abstention_candidate_empty_rate": _mean(abstention_candidate_empty),
        "mean_latency_ms": _mean(latencies),
        "details": details,
    }
    if args.run_pipeline:
        report["pipeline"] = {
            "outcome_accuracy": _mean(pipeline_outcomes),
            "exact_status_accuracy": _mean(pipeline_status_matches),
            "citation_correctness": _mean(pipeline_citation_correctness),
            "unauthorized_citation_rate": _mean(pipeline_unauthorized),
            "mean_latency_ms": _mean(pipeline_latencies),
        }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(rendered, encoding="utf-8")
    if args.observations_jsonl:
        args.observations_jsonl.parent.mkdir(parents=True, exist_ok=True)
        args.observations_jsonl.write_text(
            "".join(
                json.dumps(
                    observation.model_dump(mode="json"),
                    ensure_ascii=False,
                )
                + "\n"
                for observation in observations
            ),
            encoding="utf-8",
        )
    print(rendered)
    retrieval_regressed = (
        report["recall_at_final_k"] < 1.0
        or report["unauthorized_retrieval_rate"] != 0.0
        or report["retrieval_presence_accuracy"] < 1.0
    )
    pipeline_report = report.get("pipeline")
    pipeline_regressed = bool(
        pipeline_report
        and (
            pipeline_report["outcome_accuracy"] < 1.0
            or pipeline_report["citation_correctness"] < 1.0
            or pipeline_report["unauthorized_citation_rate"] != 0.0
        )
    )
    if args.fail_on_regression and (retrieval_regressed or pipeline_regressed):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
