# RAG Runbook

Quick operations guide for running the stack with a configured LLM/embedding
provider, Qdrant and PostgreSQL. Quy trình kiểm thử đầy đủ nằm tại
[`TESTING_RAG_PIPELINE.md`](TESTING_RAG_PIPELINE.md).

## 1. Prerequisites

- Docker & Docker Compose v2
- Python 3.11 (conda env `p234` recommended)
- API key hợp lệ cho provider được chọn
- `python-multipart` (already required for ingest uploads)

```bash
conda activate p234
python -m pip install -r requirements.txt
```

## 2. Setup API key (Quick start)

`src/rag/config.py` đọc theo thứ tự: biến môi trường thật → `.env` → `.env.rag`.

**Quy trình khuyến nghị:**

```bash
# 1. Copy template. KHÔNG commit file mới này — `.env.rag` đã gitignore.
cp .env.rag.example .env.rag

# 2. Chọn GENERATOR_PROVIDER / EMBEDDING_PROVIDER và điền key tương ứng,
#    ví dụ GEMINI_API_KEY=... hoặc OPENAI_API_KEY=sk-...
#    (Lưu ý: KHÔNG viết inline comment trên cùng dòng với key, vd
#     `OPENAI_API_KEY=sk-...  # comment` sẽ bị Pydantic Settings hiểu
#     nhầm thành giá trị key.)

# 3. (Tuỳ chọn) Key export ở shell sẽ override file .env.rag.
```

**Smoke test trước/sau khi dán key:**

```bash
# Xem key/provide có active không (ẩn 4 ký tự cuối).
python scripts/check_rag_env.py

# Hoặc output JSON để parse.
python scripts/check_rag_env.py --json
```

Lệnh này ping thật từng thành phần:
- **embedding**: gọi `embeddings.embed_query("smoke-test")`.
- **vector_store**: query Qdrant `/collections`.
- **generator**: gọi `AnswerGenerator.generate(query="ping", evidence=[])`.
- **reranker**: load `CrossEncoderReranker` (hoặc nhãn fallback).

Nếu key sai / hết hạn, từng bước sẽ fail với message chi tiết.

## 3. Start the local stack

```bash
docker compose up -d postgres qdrant adminer
# Postgres:  localhost:5432  (p234/p234)
# Qdrant:    http://localhost:6333
# Adminer:   http://localhost:8080
```

Wait for healthchecks:

```bash
docker compose ps
```

## 4. Verify the environment

The environment was already validated in step 2 (`scripts/check_rag_env.py`).
Re-run after any change to `.env.rag` or the running stack:

```bash
python scripts/check_rag_env.py
```

This prints a table of:

- `app_env`, `embedding_provider`, `embedding_dimensions`
- `generator_provider`, `model_name`
- `vector_backend`, `qdrant_url`, `reranker_provider`
- key presence (masked) and a pass/fail for each provider ping

For JSON output:

```bash
python scripts/check_rag_env.py --json
```

## 5. Smoke test the chat pipeline

```bash
python scripts/smoke_chat_real.py \
  --query "Thời hạn nộp đơn nghỉ phép theo quy chế là bao lâu?"
```

This:

1. Loads `RAGSettings()` (real keys from env).
2. Builds the `RAGContainer`.
3. Seeds and directly indexes `docs/eval/fixtures/rag_regression_corpus.json`.
4. Runs the query through the complete governed pipeline.
5. Prints `outcome`, `evidence_status`, `answer`, `citations`, warnings.

Omit `--query` to run all default queries. Use `--json` for a JSON dump.

## 6. Admin endpoints (Dev bypass auth)

When `DEV_AUTH_BYPASS=true` and `APP_ENV!=production`, include header:

```http
X-User-Id: dev-user
X-Tenant-Id: hust
X-Department: TCCB
X-Roles: data_owner,staff
```

Endpoints (require `data_owner` or `security_admin`):

| Method | Path                                    | Purpose                                |
| ------ | --------------------------------------- | -------------------------------------- |
| POST   | `/api/v1/admin/documents/ingest`        | Upload file + metadata; runs ingest.   |
| POST   | `/api/v1/admin/documents/{vid}/approve` | Approve a parsed version.              |
| POST   | `/api/v1/admin/documents/{vid}/publish` | Publish an approved version.           |
| POST   | `/api/v1/admin/index/reindex`           | Refresh statuses + warm Qdrant index.  |
| GET    | `/api/v1/admin/stats`                   | Document/version/chunk counts.         |

## 7. Switching reranker

Set `RERANKER_PROVIDER` in `.env.rag`:

- `cross_encoder` (default): tries to load the model; if loading fails, logs
  `reranker_unavailable` and **transparently falls back** to the lexical reranker.
- `lexical_fallback`: skips the cross-encoder entirely.

Check current reranker with `scripts/check_rag_env.py`.

## 8. Production hardening

Before flipping `APP_ENV=production`:

- **Set `DEV_AUTH_BYPASS=false`** (validator enforces this).
- Configure a real OIDC provider in front of the FastAPI app (the dev-bypass
  middleware refuses bypass headers in production).
- Set `RERANKER_PROVIDER=cross_encoder` and ensure the model can be downloaded.
- Run `docker compose up -d` on a host with persistent volumes for Qdrant and
  Postgres.
- Configure `LANGCHAIN_TRACING_V2=true` and an `LANGCHAIN_API_KEY` to enable
  trace dashboards.

## 9. Common failures

| Symptom                                    | Likely cause                                  |
| ------------------------------------------ | --------------------------------------------- |
| `Reranker unavailable` in logs              | CrossEncoder model not downloaded (offline)   |
| `embedding_dimensions must be one of ...`  | OpenAI model needs a supported dims           |
| `Missing OPENAI_API_KEY` in production     | Validator blocks prod without a key           |
| `Missing config: reranker_service`         | Container not yet initialized or test stub    |
| Sparse search returns empty                | Index never recreated; rerun `reindex`        |
| Admin endpoint 403                         | Header missing `X-Roles` with `data_owner`    |
| Production request with `X-User-Id` → 401  | Bypass header forbidden in production         |

## 10. Tests

```bash
pytest tests/ -q
```

Để chạy trên PDF thật tại `data/raw/HUST`, xem mục 9 trong
[`TESTING_RAG_PIPELINE.md`](TESTING_RAG_PIPELINE.md).

The full suite covers retriever, workflow, policy, citations, admin routes,
auth middleware, and Qdrant payload mapping.
