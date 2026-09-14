from __future__ import annotations

# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.ragas_adapter import (
    evaluate_id_metrics,
    evaluate_llm_metrics,
    load_ragas_input,
)

INPUT = ROOT / "docs/eval/results/ragas_input_snapshot.jsonl"
JSON_REPORT = ROOT / "docs/eval/results/ragas_report.json"
MD_REPORT = ROOT / "docs/eval/results/ragas_report.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run governed RAGAS evaluation.")
    parser.add_argument(
        "--mode", choices=("offline-id", "llm-judge"), default="offline-id"
    )
    parser.add_argument("--provider", choices=("openai",), default="openai")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--embedding-model", default="text-embedding-3-small")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict:
    records = load_ragas_input(INPUT)
    if args.mode == "offline-id":
        report = await evaluate_id_metrics(records)
    else:
        report = await evaluate_llm_metrics(
            records,
            provider=args.provider,
            model=args.model,
            embedding_model=args.embedding_model,
        )
    report.update(
        {
            "dataset": str(INPUT.relative_to(ROOT)),
            "dataset_version": "rag-regression-v1",
            "input_cases": len(records),
        }
    )
    JSON_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# RAGAS Evaluation",
        "",
        f"- Status: **{report['status']}**",
        f"- RAGAS version: `{report['ragas_version']}`",
        f"- Mode: `{report['mode']}`",
        f"- Evaluated samples: `{report['sample_count']}`",
        f"- External payload sent: `{str(report['external_payload_sent']).lower()}`",
        "",
        "## Metrics",
        "",
        *[f"- {name}: `{value}`" for name, value in report["metrics"].items()],
        "",
    ]
    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    output = asyncio.run(run(parse_args()))
    print(json.dumps({key: output[key] for key in ("status", "mode", "metrics")}, indent=2))
