"""Reproducible, dataset-backed evaluation for retrieval and RAG."""

from src.evaluation.pipeline import (
    EvaluationReport,
    GoldenCase,
    StageObservation,
    evaluate_end_to_end,
    evaluate_rag_quality,
    evaluate_stage1,
    evaluate_stage2,
    load_golden_dataset,
    production_gate,
    write_report,
)

__all__ = [
    "EvaluationReport",
    "GoldenCase",
    "StageObservation",
    "evaluate_end_to_end",
    "evaluate_rag_quality",
    "evaluate_stage1",
    "evaluate_stage2",
    "load_golden_dataset",
    "production_gate",
    "write_report",
]
