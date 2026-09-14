# Kiểm thử end-to-end RAG pipeline

Tài liệu này giúp một thành viên mới kiểm thử pipeline hiện tại trên Conda
`p234`, PostgreSQL và Qdrant chạy bằng Docker. Smoke test dùng fixture synthetic
có prefix `EVAL-`, nhưng embedding, vector search, reranker và generator đều là
provider thật theo `.env.rag`.

## 1. Điều kiện ban đầu

- Conda đã được cài đặt.
- Docker Engine và Docker Compose v2 đang hoạt động.
- Chạy lệnh từ thư mục gốc repository.
- Có API key hợp lệ cho provider được chọn trong `.env.rag`.

Tạo hoặc kích hoạt đúng environment:

```bash
# conda create -n p234 python=3.11 -y  # chỉ chạy nếu env chưa tồn tại
# conda activate p234
python --version                    # kỳ vọng Python 3.11.x
python -m pip install -r requirements.txt
python -m pip check
```

Hiện không cần `requirements-docling.txt` — OCR stack đã được lược bỏ
sau refactor 2026-08-25. Xem [`docs/PDF_PROCESSING.md`](PDF_PROCESSING.md)
cho stack hiện tại.



## 2. Cấu hình

```bash
cp .env.rag.example .env.rag  # bỏ qua nếu đã có file local hợp lệ
```

Trong `.env.rag`, chọn `GENERATOR_PROVIDER` và `EMBEDDING_PROVIDER`, sau đó điền
API key tương ứng. Không commit `.env.rag` và không dán key vào log kiểm thử.
Thiết lập local mặc định cần giữ:

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg://p234:p234@localhost:5432/p234
VECTOR_BACKEND=qdrant
QDRANT_URL=http://localhost:6333
DEV_AUTH_BYPASS=true
```



## 3. Khởi động hạ tầng Docker

```bash
docker compose up -d postgres qdrant adminer
docker compose ps
```

Tiêu chí đạt: `postgres` và `qdrant` đều là `healthy`. Adminer chỉ phục vụ kiểm
tra thủ công tại `http://localhost:8080`.

Kiểm tra provider và kết nối:

```bash
python scripts/check_rag_env.py
```

Tiêu chí đạt: cả bốn check `embedding`, `vector_store`, `generator`, `reranker`
đều là `OK`. Checker gọi thật embedding/generator; nó không in API key đầy đủ.

## 4. Chạy smoke test end-to-end

```bash
python scripts/smoke_chat_real.py \
  --query "Thời hạn nộp đơn nghỉ phép theo quy chế là bao lâu?"
```

Đây là smoke test nhanh nhưng vẫn đi qua toàn bộ pipeline và gọi generator.
Để chạy cả bộ ba câu hỏi mặc định:

```bash
python scripts/smoke_chat_real.py
```

`cross_encoder` cần nhiều RAM và chậm trên CPU. Nếu muốn chạy cả bộ trên máy
dev cấu hình thấp, có thể override riêng cho lệnh test (không sửa `.env.rag`):

```bash
RERANKER_PROVIDER=lexical_fallback python scripts/smoke_chat_real.py
```

Pipeline sẽ:

1. upsert 4 tài liệu synthetic và 6 chunks từ
  `docs/eval/fixtures/rag_regression_corpus.json`;
2. tạo/cập nhật trực tiếp vector của fixture trong Qdrant (không re-embed toàn bộ kho);
3. chạy hybrid retrieval, access policy, reranker và evidence gate;
4. gọi generator khi evidence đủ;
5. kiểm tra citation trước khi trả kết quả.

Tiêu chí đạt:

- process kết thúc với exit code `0`;
- không có trường `error` trong kết quả;
- mỗi query có `outcome`, `evidence_status`, `answer` và `warnings`;
- query có `outcome=generated` phải có citation hợp lệ;
- abstention là hợp lệ khi evidence gate đánh giá bằng chứng chưa đủ.

Để lấy stdout dạng JSON có thể parse (log vận hành được chuyển sang stderr):

```bash
python scripts/smoke_chat_real.py \
  --query "Thời hạn nộp đơn nghỉ phép theo quy chế là bao lâu?" \
  --json > /tmp/p234-smoke.json
python -m json.tool /tmp/p234-smoke.json
```

Có thể chỉ định fixture khác, nhưng fixture phải có
`dataset_kind=synthetic_regression`:

```bash
python scripts/smoke_chat_real.py --corpus path/to/corpus.json
```



## 5. Kiểm thử API thật

Terminal 1:

```bash
conda activate p234
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```bash
curl -fsS http://127.0.0.1:8000/health

curl -fsS http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: smoke-user' \
  -H 'X-Tenant-Id: hust' \
  -H 'X-Department: TCCB' \
  -H 'X-Roles: staff' \
  -d '{"message":"Thời hạn nộp đơn nghỉ phép theo quy chế là bao lâu?"}'
```

Tiêu chí đạt: `/health` trả HTTP 200 và chat trả JSON có `response`, `citations`,
`confidence`, `warnings`.

## 6. Regression suite

```bash
python -m pytest tests/ -q
python -m ruff check scripts/check_rag_env.py scripts/smoke_chat_real.py
```

Chạy riêng phần RAG/API nhanh hơn:

```bash
python -m pytest tests/test_rag tests/test_services tests/test_api tests/test_evaluation -q
```



## 7. Dữ liệu và dừng dịch vụ

Smoke test chỉ quản lý các bản ghi synthetic có số hiệu bắt đầu bằng `EVAL-`.
Volume PostgreSQL/Qdrant được giữ lại khi dừng container:

```bash
docker compose stop
```

Không dùng `docker compose down -v` trên môi trường có dữ liệu cần giữ, vì lệnh
đó xóa toàn bộ volume local.

## 8. Lỗi thường gặp


| Hiện tượng                          | Cách xử lý                                                                                                       |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Qdrant `unhealthy`                  | Chạy `docker compose up -d qdrant` để áp dụng healthcheck mới, rồi xem `docker compose ps`.                      |
| Provider check báo thiếu key        | Điền key đúng provider trong `.env.rag`; không thêm comment sau value trên cùng dòng.                            |
| Generator trả `Lỗi generator (...)` | Kiểm tra model name, quota/key và base URL của provider. Smoke test coi đây là lỗi.                              |
| Reranker tải chậm lần đầu           | Chờ model Hugging Face được cache; có thể dùng `RERANKER_PROVIDER=lexical_fallback` để smoke nhanh trên máy yếu. |
| Port 5432/6333 đã được dùng         | Dừng service đang chiếm port hoặc đổi mapping và cập nhật `.env.rag`.                                            |
| PostgreSQL schema lỗi               | Chạy `alembic upgrade head`, sau đó chạy lại smoke test.                                                         |




## 9. E2E với PDF thật trong `data/raw/HUST`

Quy trình dưới đây không dùng fixture, hash embedding, template generator hoặc
mock. PDF được parse từ ổ đĩa, dữ liệu lưu PostgreSQL, vector lưu Qdrant, rerank
bằng cross-encoder và câu trả lời được sinh bởi Gemini.

Gemini free tier có thể hết quota embedding khi index hàng trăm chunks. Profile
dưới đây dùng multilingual Sentence Transformer thật chạy local cho embedding,
còn Gemini vẫn là LLM sinh câu trả lời:

```bash
conda activate p234
docker compose up -d postgres qdrant adminer

export EMBEDDING_PROVIDER=sentence_transformers
export EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
export EMBEDDING_DIMENSIONS=384
export EMBEDDING_DEVICE=cpu
export EMBEDDING_BATCH_SIZE=16
export QDRANT_COLLECTION=hust-regulations-real-v1
```

Ingest, approve, index và publish Quy chế đào tạo thật:

```bash
RERANKER_PROVIDER=lexical_fallback \
python scripts/ingest_hust_corpus.py \
  --file 5445.pdf \
  --approve-publish
```

`lexical_fallback` ở lệnh ingest chỉ giúp không nạp đồng thời hai model lớn;
reranker không tham gia tạo vector. Khi chạy API, dùng cross-encoder thật:

```bash
RERANKER_PROVIDER=cross_encoder \
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Truy vấn đối chiếu:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: e2e-real-user' \
  -H 'X-Tenant-Id: hust' \
  -H 'X-Department: DT' \
  -H 'X-Roles: staff' \
  -d '{"message":"Theo Quy chế đào tạo 5445/QĐ-ĐHBK, khi nào sinh viên bị nâng hai mức cảnh báo học tập? Cho biết điều khoản và địa chỉ văn bản nguồn."}'
```

Kết quả đã xác minh trên corpus hiện tại:

- `evidence_status=sufficient`, `evidence_action=generate`;
- câu trả lời: trên 16 tín chỉ không đạt, hoặc tự ý bỏ học/không đăng ký học tập;
- citation: `Điều 19 — Khoản 1 — Điểm b`, trang 18;
- source: đường dẫn tuyệt đối tới `data/raw/HUST/5445.pdf`;
- `confidence=high`, không warning.

Không chạy đồng thời OCR EasyOCR và cross-encoder trên máy ít RAM. Các PDF scan
thuần (`5980.pdf`, `6100.pdf`, `7323.pdf`) nên được OCR tuần tự trước khi đưa vào
batch chung; script `pypdf` sẽ fail rõ ràng nếu tài liệu không có lớp text.