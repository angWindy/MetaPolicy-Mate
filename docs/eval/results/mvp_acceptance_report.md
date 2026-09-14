# MVP Guardrails Acceptance Report

- Date: `2026-08-20`
- Overall status: **FAIL**
- Definition of Done complete: `false`
- Base commit: `94895ffbfe1ce6f09a244a759a7220db550f6208`
- Evaluated implementation commit: `6078b453a11215bb4af016786150e1e450eac4c7`
- Implementation changes committed: `true`
- Working tree clean: `false` — unrelated `.review-dev-20260813/` remains untracked.
- Guardrail policy: `guardrails-v1`
- Retrieval access policy: `retrieval-access-v1`
- Security dataset: `guardrails-mvp-v1`
- Quality dataset: `rag-regression-v1`

## Security gate

- Attack cases: `250`; benign cases: `100`
- Seeds: `17, 42, 101, 2026, 9871`
- Attack runs: `1250`; benign runs: `500`
- Attack Success Rate: `0.0`
- False-positive Rate: `0.0`
- Critical leakage: `0`
- Cross-tenant leakage: `0`
- PII leakage: `0`
- Abstention correctness: `1.0`
- Stable across five seeds: `true`
- Status: **PASS**

## RAG quality gate

The measured evaluator is `local_deterministic_extractive_v1` over seven
synthetic regression cases executed against real local PostgreSQL and Qdrant.
Embedding, reranking and generation remain deterministic local test providers;
this is not an LLM-as-judge RAGAS run.

- Answer correctness: `0.8539080704051957`
- Faithfulness: `1.0`
- Context precision: `0.7142857142857143`
- Context recall: `0.7142857142857143`
- Citation correctness: `1.0`
- Citation validation: `1.0`
- Critical abstention correctness: `1.0`
- Local quality status: **PASS**
- RAGAS offline ID-based status: **PASS** — RAGAS `0.3.9`, four answerable
  samples, context precision `0.5416666666666666`, context recall `1.0`, and no
  external payload was sent.
- RAGAS LLM-judge status: **FAIL** — the destination-specific OpenAI run was
  attempted with the key from `.env`, but OpenAI returned HTTP `401`
  `invalid_api_key`. No LLM-judge metrics were produced, so the requested RAGAS
  faithfulness and answer-correctness gates remain unverified.

## Test suites

- Metadata contract, ingestion and RBAC targeted: **PASS — 48 passed**
- Guardrail and five-seed security gate: **PASS — 67 passed**
- Evaluation unit tests: **PASS — 19 passed**
- RAGAS adapter and data contract targeted: **PASS — 48 passed**
- PostgreSQL/Qdrant consistency targeted: **PASS — 45 passed**
- Full unit/integration suite: **PASS — 656 passed, 1 dependency warning**
- PostgreSQL + Qdrant synthetic pipeline E2E: **PASS** — 4 published documents,
  6 chunks, 6 Qdrant points, 21 payload indexes, and all 7 evaluation cases ran.
- Local API E2E over PostgreSQL/Qdrant: **PASS** — health/chat HTTP `200`, one
  valid citation, sufficient evidence, high confidence and zero warnings.
- Alembic schema consistency: **FAIL** — migration head uses
  `documents.title VARCHAR(500)` while the ORM declares `String(2000)`.
- Real PostgreSQL + Qdrant + approved HUST corpus E2E: **FAIL** — the current
  checkout contains no `data/raw/HUST` corpus or approved HUST records.

## Commands executed

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ingestion\test_index_metadata_contract.py tests\test_ingestion\test_pipeline_flow.py tests\test_rag\test_policy_filter.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_rag\test_guardrails.py tests\test_evaluation\test_security.py -q
.\.venv\Scripts\python.exe scripts\run_guardrail_redteam.py
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation -q
.\.venv\Scripts\python.exe scripts\run_rag_quality_eval.py
.\.venv\Scripts\python.exe scripts\run_ragas_eval.py --mode offline-id
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation\test_ragas_adapter.py tests\test_ingestion\test_index_metadata_contract.py tests\test_evaluation\test_pipeline.py -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check src\evaluation\ragas_adapter.py scripts\run_ragas_eval.py scripts\run_rag_quality_eval.py tests\test_evaluation\test_ragas_adapter.py
.\.venv\Scripts\python.exe -m pytest -q
docker compose up -d postgres qdrant
docker compose ps
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe scripts\run_rag_quality_eval.py --profile docker
.\.venv\Scripts\python.exe scripts\run_ragas_eval.py --mode llm-judge --provider openai
.\.venv\Scripts\python.exe scripts\run_ragas_eval.py --mode offline-id
.\.venv\Scripts\python.exe -m uvicorn src.main:app --host 127.0.0.1 --port 8011
git commit -m "feat: harden RAG guardrails and evaluation"
```

## Remaining limitations

- Quality metrics use real local PostgreSQL/Qdrant but a synthetic regression
  corpus, hash embeddings, lexical reranking and the template generator.
- RAGAS ID-based context metrics are measured offline. RAGAS LLM-judge
  faithfulness, answer correctness, context precision and context recall remain
  unmeasured because OpenAI rejected the configured key; that acceptance gate
  is explicitly failed.
- Real-infrastructure synthetic and API E2E passed, but approved-corpus HUST E2E
  is unmeasured because the corpus is absent; that acceptance gate is failed.
- Alembic migration/model drift remains unresolved for `documents.title`.
- The implementation evidence is pinned to commit
  `6078b453a11215bb4af016786150e1e450eac4c7`; this acceptance report is recorded
  in the following documentation commit.
- Local context precision/recall are `0.7142857142857143`; the requested plan
  defines no numeric MVP gate for those two metrics.

## Post-MVP backlog

- Redis distributed rate limiter
- PostgreSQL checkpointer across workers
- Online semantic injection classifier
- Advanced DLP
- Claim-level entailment runtime
- Full multi-worker testing
- Full load/stress testing
