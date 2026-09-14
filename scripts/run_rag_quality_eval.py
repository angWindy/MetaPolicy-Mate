from __future__ import annotations

# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.schemas import RetrievalStatus
from src.evaluation.local_quality import (
    average_precision,
    context_recall,
    extractive_faithfulness,
    token_f1,
)
from src.evaluation.pipeline import (
    StageObservation,
    evaluate_rag_quality,
    load_golden_dataset,
)
from src.evaluation.regression_seed import seed_regression_corpus
from src.rag.config import EvidenceThresholds, RAGSettings
from src.rag.container import RAGContainer

DATASET = ROOT / "docs/eval/datasets/golden_questions.regression.jsonl"
FIXTURE = ROOT / "docs/eval/fixtures/rag_regression_corpus.json"
JSON_REPORT = ROOT / "docs/eval/results/rag_quality_report.json"
MD_REPORT = ROOT / "docs/eval/results/rag_quality_report.md"
RAGAS_SNAPSHOT = ROOT / "docs/eval/results/ragas_input_snapshot.jsonl"


def _chunk_id(value) -> str:
    if isinstance(value, dict):
        return str(value.get("chunk_id", ""))
    return str(getattr(value, "chunk_id", ""))


def _chunk_text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or "")
    return str(getattr(value, "text", None) or getattr(value, "content", ""))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run governed RAG quality evaluation.")
    parser.add_argument(
        "--profile",
        choices=("local", "docker"),
        default="local",
        help="Use in-memory test services or real local PostgreSQL/Qdrant.",
    )
    return parser.parse_args()


def build_settings(profile: str) -> RAGSettings:
    docker = profile == "docker"
    return RAGSettings(
        app_env="test",
        database_url=(
            "postgresql+psycopg://p234:p234@localhost:5432/p234"
            if docker
            else "sqlite://"
        ),
        vector_backend="qdrant" if docker else "memory",
        qdrant_url="http://localhost:6333",
        qdrant_collection=(
            "hust-regulations-eval-v1" if docker else "hust-regulations-v1"
        ),
        generator_provider="template",
        embedding_provider="hash",
        embedding_dimensions=128,
        reranker_provider="lexical_fallback",
        evidence_thresholds_by_domain={
            "general": EvidenceThresholds(
                sufficient_top_score=0.15,
                partial_top_score=0.10,
                minimum_independent_sources=1,
            )
        },
        data_dir=ROOT / (".tmp/eval-quality-docker" if docker else ".tmp/eval-quality"),
    )


async def run(profile: str = "local") -> dict:
    settings = build_settings(profile)
    container = RAGContainer(settings)
    seed_summary = await seed_regression_corpus(container, FIXTURE)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reference_text_by_id = {
        chunk["id"]: chunk["text"]
        for document in fixture["documents"]
        for chunk in document["chunks"]
    }
    cases = load_golden_dataset(DATASET)
    observations: list[StageObservation] = []
    case_results: list[dict] = []
    ragas_rows: list[dict] = []

    for case in cases:
        retrieved = await container.retriever.search(
            case.query, case.user_context, case.as_of_date
        )
        state = await container.pipeline.ainvoke(
            {
                "query": case.query,
                "original_query": case.query,
                "user": case.user_context,
                "as_of_date": case.as_of_date,
                "request_id": str(uuid.uuid4()),
            }
        )
        final_contexts = list(state.get("final_contexts", []) or [])
        final_ids = [_chunk_id(item) for item in final_contexts if _chunk_id(item)]
        citations = list(state.get("citations", []) or [])
        citation_ids = [_chunk_id(item) for item in citations if _chunk_id(item)]
        citation_versions = {
            _chunk_id(item): str(
                item.get("version_id", "")
                if isinstance(item, dict)
                else getattr(item, "version_id", "")
            )
            for item in citations
            if _chunk_id(item)
        }
        answer = str(state.get("answer", ""))
        actual_status = state.get("evidence_status")
        if actual_status is None:
            actual_status = (
                RetrievalStatus.NOT_FOUND
                if not citations
                else RetrievalStatus.SUFFICIENT
            )
        expected = set(case.expected_chunk_ids)
        is_abstained = not citation_ids
        behavior_correct = is_abstained == case.should_abstain
        answer_correctness = (
            float(behavior_correct)
            if case.should_abstain
            else token_f1(case.reference_answer, answer)
        )
        faithfulness = (
            float(behavior_correct)
            if case.should_abstain
            else extractive_faithfulness(
                answer, [_chunk_text(item) for item in final_contexts]
            )
        )
        observation = StageObservation(
            retrieved_chunk_ids=[item.chunk_id for item in retrieved],
            ranked_chunk_ids=final_ids,
            final_context_ids=final_ids,
            citation_chunk_ids=citation_ids,
            citation_versions=citation_versions,
            answer=answer,
            actual_status=actual_status,
            answer_correctness=answer_correctness,
            faithfulness=faithfulness,
            context_precision=average_precision(final_ids, expected),
            context_recall=context_recall(final_ids, expected),
            abstained=is_abstained,
        )
        observations.append(observation)
        ragas_rows.append(
            {
                "case_id": f"case-{len(ragas_rows) + 1:03d}",
                "user_input": case.query,
                "response": answer,
                "reference": case.reference_answer,
                "retrieved_contexts": [_chunk_text(item) for item in final_contexts],
                "reference_contexts": [
                    reference_text_by_id[chunk_id]
                    for chunk_id in case.expected_chunk_ids
                ],
                "retrieved_context_ids": final_ids,
                "reference_context_ids": case.expected_chunk_ids,
                "citation_chunk_ids": citation_ids,
                "should_abstain": case.should_abstain,
                "security_category": case.security_category,
            }
        )
        case_results.append(
            {
                "category": case.category,
                "should_abstain": case.should_abstain,
                "retrieved_chunk_ids": observation.retrieved_chunk_ids,
                "final_context_ids": final_ids,
                "citation_chunk_ids": citation_ids,
                "outcome": str(state.get("outcome", "")),
                "error_code": str(state.get("error_code", "")),
                "guardrail_reason_codes": list(state.get("guardrail_reason_codes", []) or []),
                "warnings": [str(item) for item in state.get("warnings", []) or []],
                "answer": answer,
                "answer_correctness": answer_correctness,
                "faithfulness": faithfulness,
                "behavior_correct": behavior_correct,
            }
        )

    metrics = evaluate_rag_quality(cases, observations)
    checks = {
        "faithfulness_gte_0_85": metrics["faithfulness"] is not None
        and metrics["faithfulness"] >= 0.85,
        "answer_correctness_gte_0_75": metrics["answer_correctness"] is not None
        and metrics["answer_correctness"] >= 0.75,
        "citation_validation_100pct": metrics["citation_validation"] == 1.0,
        "critical_abstention_100pct": metrics["critical_abstention_correctness"] == 1.0,
    }
    report = {
        "dataset": str(DATASET.relative_to(ROOT)),
        "dataset_version": "rag-regression-v1",
        "dataset_cases": len(cases),
        "infrastructure_profile": profile,
        "database_backend": "postgresql" if profile == "docker" else "sqlite-memory",
        "evaluator": "local_deterministic_extractive_v1",
        "ragas_llm_judge_executed": False,
        "seed_summary": seed_summary,
        "metrics": metrics,
        "gate": {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks},
        "cases": case_results,
    }
    JSON_REPORT.parent.mkdir(parents=True, exist_ok=True)
    RAGAS_SNAPSHOT.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in ragas_rows) + "\n",
        encoding="utf-8",
    )
    JSON_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# RAG Quality Evaluation",
        "",
        f"- Dataset: `{report['dataset']}`",
        f"- Cases: `{len(cases)}`",
        f"- Infrastructure profile: `{profile}`",
        f"- Database backend: `{report['database_backend']}`",
        f"- Vector backend: `{seed_summary['vector_backend']}`",
        "- Evaluator: `local_deterministic_extractive_v1`",
        "- RAGAS LLM judge executed: `false`",
        f"- Local gate: **{report['gate']['status']}**",
        "",
        "## Quality metrics",
        "",
        *[f"- {name}: `{value}`" for name, value in metrics.items()],
        "",
        "The local evaluator measures extractive grounding and lexical answer overlap. "
        "It is not reported as a RAGAS LLM-judge result.",
        "",
    ]
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = asyncio.run(run(parse_args().profile))
    print(json.dumps({"metrics": result["metrics"], "gate": result["gate"]}, indent=2))
