from pathlib import Path

import pytest

from src.evaluation.pipeline import load_golden_dataset
from src.evaluation.regression_seed import seed_regression_corpus
from src.rag.config import RAGSettings
from src.rag.container import RAGContainer

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "eval" / "fixtures" / "rag_regression_corpus.json"
DATASET = ROOT / "docs" / "eval" / "datasets" / "golden_questions.regression.jsonl"


@pytest.mark.asyncio
async def test_seeded_regression_corpus_matches_golden_retrieval_labels(tmp_path):
    container = RAGContainer(
        RAGSettings(
            app_env="test",
            database_url="sqlite://",
            data_dir=tmp_path,
            vector_backend="memory",
            generator_provider="template",
            embedding_provider="hash",
            embedding_dimensions=128,
        )
    )
    summary = await seed_regression_corpus(container, FIXTURE)
    cases = load_golden_dataset(DATASET)

    assert summary["documents"] == 4
    assert summary["chunks"] == 6

    for case in cases:
        evaluation_trace = {}
        results = await container.retriever.search(
            case.query,
            case.user_context,
            case.as_of_date,
            evaluation_trace=evaluation_trace,
        )
        result_ids = {item.chunk_id for item in results}
        assert set(result_ids).issubset(evaluation_trace["reranked_chunk_ids"])
        assert set(evaluation_trace["fused_chunk_ids"]).issubset(
            evaluation_trace["authorized_candidate_ids"]
        )
        assert evaluation_trace["latency_ms"]["total"] >= 0
        assert not result_ids.intersection(case.forbidden_chunk_ids)
        if case.expected_chunk_ids:
            assert result_ids.intersection(case.expected_chunk_ids)
