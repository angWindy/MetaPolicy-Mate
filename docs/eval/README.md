# RAG Evaluation

## Báo cáo mới nhất

- [Báo cáo đánh giá Retrieval và câu trả lời RAG trên môi trường Live — 110 câu, ngày 04/09/2026](results/rag_retrieval_live_report_20260904.md)
- [Dữ liệu kết quả chi tiết theo từng trường hợp](results/rag_quality_live_110_current_20260904.jsonl)
- [Báo cáo regression kỹ thuật theo từng stage](results/retrieval_evaluation_20260904.md)

Báo cáo live hiện có kết luận **KHÔNG ĐẠT**: Precision tài liệu 96,08%,
Recall 98,00%, F1 97,03%, nhưng tỷ lệ đạt toàn bộ tiêu chí là 77,27%, thấp
hơn release gate 80%.

The project keeps two evaluation contracts separate because they answer
different questions:

1. `datasets/golden_questions.regression.jsonl` uses exact chunk, version,
   authorization, temporal-validity, and abstention labels. It is the
   deterministic technical regression set.
2. `../../tests/sweep/golden_v7_domain_100.jsonl` and
   `../../tests/sweep/golden_v8_negative_10.jsonl` use stable document and
   evidence anchors. They are the live business-quality set.

Do not merge the scores from these datasets. Report their results in separate
sections and preserve the runtime snapshot for every live run.

## Deterministic technical evaluation

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py `
  docs\eval\datasets\golden_questions.regression.jsonl `
  --seed-fixture docs\eval\fixtures\rag_regression_corpus.json `
  --database-url sqlite:// `
  --vector-backend memory `
  --data-dir .tmp\retrieval-eval-data `
  --run-pipeline `
  --fail-on-regression `
  --observations-jsonl docs\eval\results\retrieval_observations.jsonl `
  --report-json docs\eval\results\retrieval_raw.json

.\.venv\Scripts\python.exe scripts\evaluate_pipeline.py `
  docs\eval\datasets\golden_questions.regression.jsonl `
  --observations-jsonl docs\eval\results\retrieval_observations.jsonl `
  --report-json docs\eval\results\retrieval_evaluation.json `
  --report-md docs\eval\results\retrieval_evaluation.md `
  --index-version synthetic-regression `
  --fail-on-regression
```

The first command records measured stage observations. The second command
validates the observations, computes stage-separated metrics, records dataset
and observation SHA-256 hashes, and applies the production gate.

## Live business evaluation

Start the API and provide the sweep password through
`P234_SWEEP_PASSWORD`. Never place credentials in command history, result
artifacts, or committed files.

```powershell
.\.venv\Scripts\python.exe tests\sweep\run_sweep.py `
  --live `
  --golden tests\sweep\golden_v7_domain_100.jsonl `
  --extra-golden tests\sweep\golden_v8_negative_10.jsonl `
  --out docs\eval\results\rag_quality_live.jsonl `
  --report-md docs\eval\results\rag_retrieval_live_report.md
```

The live report includes micro document Precision, Recall, and F1, confusion
counts, evidence and answer quality, positive/negative slices, latency p50/p95,
failed cases, and interpretation notes.

## Interpretation rules

- A technical regression result does not prove live production readiness.
- A live sweep does not replace ACL, version, and temporal regression tests.
- `INSUFFICIENT_DATA` is required when labels or observations are missing.
- Do not tune thresholds or labels to force a PASS.
- See C-023, C-024, and C-025 in `CROSS_LAYER_CONFLICT_REGISTER.md` before
  changing golden labels or the Precision@5 gate.
