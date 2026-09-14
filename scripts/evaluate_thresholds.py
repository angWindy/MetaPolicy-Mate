#!/usr/bin/env python3
"""
Evaluate and calibrate evidence thresholds using a ground-truth QA set.

Usage:
    python scripts/evaluate_thresholds.py [--dataset data/eval_qa.jsonl]

The script loads QA pairs, runs the retrieval workflow for each question,
and sweeps the evidence threshold parameters to find the combination that
maximises the win rate (fraction of questions that produce a generated
answer with at least one valid citation).

Results are written to stdout as a JSON blob that can be copied into
RAGSettings.evidence_thresholds_by_domain["regulations"].
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add project root to path so imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag.config import EvidenceThresholds, RAGSettings
from src.rag.workflow import RetrievalWorkflow
from src.domain.schemas import RetrievalStatus, UserContext


@dataclass
class EvalQA:
    question: str
    expected_doc_numbers: list[str] = field(default_factory=list)
    # Optional: document_number values that the answer should cite.


@dataclass
class EvalResult:
    question: str
    outcome: str  # "generated" | "abstained" | "error"
    confidence: str
    citation_count: int
    cited_doc_numbers: list[str]
    latency_ms: float
    status: str
    top_score: float | None
    error: str | None


# ----------------------------------------------------------------------
# Ground-truth dataset — replace with curated eval set or load from file.
# ----------------------------------------------------------------------
DEFAULT_QAS: list[EvalQA] = [
    EvalQA(
        question="Các KPI đánh giá giảng viên bao gồm những tiêu chí nào?",
        expected_doc_numbers=[],
    ),
    EvalQA(
        question="Quy định về chấm công giảng viên được mô tả như thế nào?",
        expected_doc_numbers=[],
    ),
    EvalQA(
        question="Mức tiền lương cho giảng viên được tính theo công thức nào?",
        expected_doc_numbers=[],
    ),
]


def load_qa_file(path: Path) -> list[EvalQA]:
    qas: list[EvalQA] = []
    with path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
                qas.append(EvalQA(
                    question=obj["question"],
                    expected_doc_numbers=obj.get("expected_doc_numbers", []),
                ))
            except Exception as exc:
                print(f"WARNING: skipped line {lineno}: {exc}", file=sys.stderr)
    return qas


async def run_one(
    workflow: RetrievalWorkflow,
    qa: EvalQA,
    user: UserContext,
) -> EvalResult:
    """Run a single question through the workflow and extract metrics."""
    state = {
        "original_query": qa.question,
        "query": qa.question,
        "user": user,
        "as_of_date": None,
        "request_id": f"eval-{id(qa)}",
        "index_version": "",
    }
    try:
        started = time.perf_counter()
        result = await workflow.ainvoke(state, thread_id=f"eval-{id(qa)}")
        elapsed_ms = (time.perf_counter() - started) * 1000
    except Exception as exc:
        return EvalResult(
            question=qa.question,
            outcome="error",
            confidence="low",
            citation_count=0,
            cited_doc_numbers=[],
            latency_ms=0.0,
            status="exception",
            top_score=None,
            error=str(exc),
        )

    outcome = result.get("outcome", "unknown")
    confidence = result.get("confidence", "low")
    citations = list(result.get("citations") or [])
    cited_doc_numbers = [
        str(c.get("document_number") or c.get("document_id") or "")
        for c in citations
        if c
    ]
    rerank = result.get("rerank_result")
    top_score = None
    status = str(result.get("evidence_status") or "unknown")
    if rerank and rerank.candidates:
        top_score = float(rerank.candidates[0].rerank_score or 0.0)

    return EvalResult(
        question=qa.question,
        outcome=outcome,
        confidence=confidence,
        citation_count=len(citations),
        cited_doc_numbers=cited_doc_numbers,
        latency_ms=elapsed_ms,
        status=status,
        top_score=top_score,
        error=None,
    )


def score_combo(
    results: list[EvalResult],
    combo: dict[str, Any],
) -> dict[str, Any]:
    """Return a score dict for one threshold combination."""
    generated = [r for r in results if r.outcome == "generated"]
    high_conf = [r for r in generated if r.confidence in {"high", "medium"}]
    with_citation = [r for r in generated if r.citation_count >= 1]
    abstain = [r for r in results if r.outcome == "abstained"]
    errors = [r for r in results if r.outcome == "error"]
    return {
        "win_rate": len(generated) / max(len(results), 1),
        "generated": len(generated),
        "high_confidence": len(high_conf),
        "with_citation": len(with_citation),
        "abstained": len(abstain),
        "errors": len(errors),
        "avg_latency_ms": (
            sum(r.latency_ms for r in results) / max(len(results), 1)
        ),
        "top_scores": [r.top_score for r in results if r.top_score is not None],
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG evidence thresholds")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to JSONL file with eval questions (one object per line with 'question' key)",
    )
    parser.add_argument(
        "--settings",
        type=str,
        default="development",
        help="APP_ENV to use (development | production | test)",
    )
    args = parser.parse_args()

    qas = []
    if args.dataset:
        qas = load_qa_file(args.dataset)
        print(f"Loaded {len(qas)} QA pairs from {args.dataset}", file=sys.stderr)
    else:
        qas = DEFAULT_QAS
        print(f"Using {len(qas)} built-in QA pairs", file=sys.stderr)

    # Build a minimal workflow (retriever/reranker/generator may be None in test mode).
    # We pass a no-op retriever so the script can run without a live Qdrant.
    settings = RAGSettings(_env_file=".env.rag")
    settings.app_env = args.settings

    from src.rag.generator import TemplateAnswerGenerator

    workflow = RetrievalWorkflow(
        settings=settings,
        retriever=None,
        reranker_service=None,
        generator=TemplateAnswerGenerator(),
    )

    # Dummy user context for access control
    user = UserContext(
        user_id="eval-user",
        tenant_id="hust",
        department="TCCB",
        role="admin",
        school_code="HUST",
    )

    # Sweep grid
    sufficient_scores = [0.05, 0.10, 0.15, 0.20, 0.25]
    score_gaps = [0.0, 0.05, 0.10]
    independent_sources = [1, 2]

    best_score = -1.0
    best_params: dict[str, Any] = {}
    all_results: dict[tuple, list[EvalResult]] = {}

    print("Running threshold sweep ...", file=sys.stderr)
    for suff in sufficient_scores:
        for gap in score_gaps:
            for indep in independent_sources:
                # Temporarily patch settings thresholds
                original_domain = settings.evidence_thresholds_by_domain.get("regulations")
                settings.evidence_thresholds_by_domain["regulations"] = EvidenceThresholds(
                    sufficient_top_score=suff,
                    partial_top_score=max(0.01, suff - 0.05),
                    minimum_score_gap=gap,
                    minimum_independent_sources=indep,
                    max_retries=1,
                    require_citation_metadata=False,
                )
                # Re-initialise workflow with patched settings
                workflow = RetrievalWorkflow(
                    settings=settings,
                    retriever=None,
                    reranker_service=None,
                    generator=TemplateAnswerGenerator(),
                )
                results = await asyncio.gather(
                    *(run_one(workflow, qa, user) for qa in qas),
                )
                metrics = score_combo(results, {"suff": suff, "gap": gap, "indep": indep})
                key = (suff, gap, indep)
                all_results[key] = list(results)
                win_rate = metrics["win_rate"]
                if win_rate > best_score:
                    best_score = win_rate
                    best_params = {
                        "sufficient_top_score": suff,
                        "partial_top_score": max(0.01, suff - 0.05),
                        "minimum_score_gap": gap,
                        "minimum_independent_sources": indep,
                        "max_retries": 1,
                        "require_citation_metadata": False,
                    }
                # Restore
                if original_domain is not None:
                    settings.evidence_thresholds_by_domain["regulations"] = original_domain
                else:
                    settings.evidence_thresholds_by_domain.pop("regulations", None)

                print(
                    f"  suff={suff:.2f} gap={gap:.2f} indep={indep} "
                    f"→ generated={metrics['generated']}/{len(qas)} "
                    f"citations={metrics['with_citation']} "
                    f"latency={metrics['avg_latency_ms']:.0f}ms "
                    f"top_scores={metrics['top_scores']}",
                    file=sys.stderr,
                )

    print("\n=== BEST PARAMETERS ===", file=sys.stderr)
    print(json.dumps(best_params, indent=2), file=sys.stderr)
    print(f"\nBest win rate: {best_score:.2%}", file=sys.stderr)

    # Print the recommended config snippet
    print("\n=== RECOMMENDED RAGSettings snippet ===")
    print(
        json.dumps(
            {"evidence_thresholds_by_domain": {"regulations": best_params}},
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
