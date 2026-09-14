"""Strict RAGAS dataset adapter and offline/opt-in evaluation runners."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RagasInputRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    user_input: str = Field(min_length=1)
    response: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    retrieved_contexts: list[str]
    reference_contexts: list[str]
    retrieved_context_ids: list[str]
    reference_context_ids: list[str]
    citation_chunk_ids: list[str]
    should_abstain: bool
    security_category: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_context_alignment(self) -> RagasInputRecord:
        if len(self.retrieved_contexts) != len(self.retrieved_context_ids):
            raise ValueError("retrieved context texts and IDs must have equal length.")
        if len(self.reference_contexts) != len(self.reference_context_ids):
            raise ValueError("reference context texts and IDs must have equal length.")
        if not self.should_abstain and not self.reference_context_ids:
            raise ValueError("answerable cases require reference context IDs.")
        placeholders = ("insufficient_data", "replace with", "thay bằng", "todo")
        if any(marker in self.reference.casefold() for marker in placeholders):
            raise ValueError("reference contains a placeholder label.")
        return self


def load_ragas_input(path: str | Path) -> list[RagasInputRecord]:
    source = Path(path)
    rows: list[RagasInputRecord] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        source.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            record = RagasInputRecord.model_validate_json(line)
        except ValueError as exc:
            raise ValueError(f"Invalid RAGAS row {line_number}: {exc}") from exc
        if record.case_id in seen:
            raise ValueError(f"Duplicate RAGAS case_id at row {line_number}.")
        seen.add(record.case_id)
        rows.append(record)
    if not rows:
        raise ValueError("RAGAS input dataset is empty.")
    return rows


def build_evaluation_dataset(
    records: list[RagasInputRecord],
    *,
    answerable_only: bool,
):
    from ragas import EvaluationDataset, SingleTurnSample

    selected = [record for record in records if not record.should_abstain]
    if not answerable_only:
        selected = records
    if not selected:
        raise ValueError("No RAGAS samples match the requested evaluation scope.")
    return EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=record.user_input,
                response=record.response,
                reference=record.reference,
                retrieved_contexts=record.retrieved_contexts,
                reference_contexts=record.reference_contexts,
                retrieved_context_ids=record.retrieved_context_ids,
                reference_context_ids=record.reference_context_ids,
            )
            for record in selected
        ]
    )


def _aggregate(result, metric_names: list[str]) -> dict[str, float]:
    frame = result.to_pandas()
    metrics: dict[str, float] = {}
    for name in metric_names:
        values = frame[name].dropna()
        if values.empty:
            raise ValueError(f"RAGAS metric {name} has no measured values.")
        metrics[name] = float(values.mean())
    return metrics


async def evaluate_id_metrics(records: list[RagasInputRecord]) -> dict[str, Any]:
    """Run real RAGAS metrics that require no LLM and no external transfer."""

    import ragas
    from ragas import aevaluate
    from ragas.metrics import IDBasedContextPrecision, IDBasedContextRecall

    dataset = build_evaluation_dataset(records, answerable_only=True)
    names = ["id_based_context_precision", "id_based_context_recall"]
    result = await aevaluate(
        dataset,
        metrics=[IDBasedContextPrecision(), IDBasedContextRecall()],
        show_progress=False,
        raise_exceptions=True,
    )
    return {
        "status": "PASS",
        "ragas_version": ragas.__version__,
        "mode": "offline_id_based",
        "sample_count": len(dataset),
        "external_payload_sent": False,
        "metrics": _aggregate(result, names),
        "rows": result.to_pandas().to_dict(orient="records"),
    }


def require_external_approval(provider: Literal["openai"]) -> None:
    approved = os.getenv("RAGAS_EXTERNAL_EVAL_APPROVED", "").casefold() == "true"
    destination = os.getenv("RAGAS_EXTERNAL_EVAL_DESTINATION", "").casefold()
    if not approved or destination != provider:
        raise PermissionError(
            "External RAGAS evaluation requires RAGAS_EXTERNAL_EVAL_APPROVED=true "
            f"and RAGAS_EXTERNAL_EVAL_DESTINATION={provider}."
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for the approved OpenAI evaluator.")


async def evaluate_llm_metrics(
    records: list[RagasInputRecord],
    *,
    provider: Literal["openai"],
    model: str,
    embedding_model: str,
) -> dict[str, Any]:
    """Run LLM-judge metrics only after payload- and destination-specific approval."""

    require_external_approval(provider)
    import ragas
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import aevaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        AnswerCorrectness,
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )

    llm = LangchainLLMWrapper(ChatOpenAI(model=model, temperature=0))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=embedding_model))
    metrics = [
        Faithfulness(llm=llm),
        AnswerCorrectness(llm=llm, embeddings=embeddings),
        LLMContextPrecisionWithReference(llm=llm),
        LLMContextRecall(llm=llm),
    ]
    names = [
        "faithfulness",
        "answer_correctness",
        "llm_context_precision_with_reference",
        "context_recall",
    ]
    dataset = build_evaluation_dataset(records, answerable_only=True)
    result = await aevaluate(
        dataset,
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
        show_progress=True,
        raise_exceptions=True,
    )
    return {
        "status": "PASS",
        "ragas_version": ragas.__version__,
        "mode": "external_llm_judge",
        "provider": provider,
        "model": model,
        "embedding_model": embedding_model,
        "sample_count": len(dataset),
        "external_payload_sent": True,
        "metrics": _aggregate(result, names),
        "rows": result.to_pandas().to_dict(orient="records"),
    }


__all__ = [
    "RagasInputRecord",
    "build_evaluation_dataset",
    "evaluate_id_metrics",
    "evaluate_llm_metrics",
    "load_ragas_input",
    "require_external_approval",
]
