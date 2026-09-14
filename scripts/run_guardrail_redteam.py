from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluation.security import (
    evaluate_security_datasets,
    load_jsonl,
    render_security_report_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic MVP guardrail red-team evaluation.")
    parser.add_argument(
        "--attacks",
        default="docs/eval/datasets/guardrail_attacks.jsonl",
    )
    parser.add_argument(
        "--benign",
        default="docs/eval/datasets/guardrail_benign.jsonl",
    )
    parser.add_argument("--output", default="docs/eval/results/guardrail_security_report.json")
    args = parser.parse_args()

    report = evaluate_security_datasets(
        load_jsonl(args.attacks),
        load_jsonl(args.benign),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output.with_suffix(".md").write_text(
        render_security_report_markdown(report),
        encoding="utf-8",
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
