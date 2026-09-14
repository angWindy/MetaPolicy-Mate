# End-to-end Pipeline Test với PDF HUST — Trải nghiệm thực tế

> **Lưu ý (2026-08-25):** Phần "8. OCR config" (sections 284-290) và
> "8.2 Fix đã áp dụng" mục 4-5 đã lỗi thời. `RAGSettings` không còn các
> field OCR/PP-Structure và `requirements-docling.txt` đã xoá. Xem
> `[docs/PDF_PROCESSING.md](PDF_PROCESSING.md)` cho stack hiện tại.

> Tài liệu này ghi lại quá trình test pipeline end-to-end với các file PDF
> thật trong `data/raw/HUST/` (đặc biệt `10232.pdf` — Quyết định phê duyệt
> mức học phí năm học 2025-2026), các lỗi phát hiện được, cách sửa, và đo
> đạc chất lượng/tốc độ cuối cùng.
>
> **Cập nhật 2026-08-13**: bổ sung section 5–7 mô tả lỗ hổng phát hiện khi
> review về luồng `Upload → Parse/Chunk → Approve → Index → Publish` và cách
> khắc phục (xem `docs/DATA_PROCESSING_FLOW.md` cho spec đầy đủ).

---



## 1. Bối cảnh

Sau khi hoàn tất hỗ trợ đa provider cho embedding (`hash`, `openai`,
`sentence_transformers`, `ollama`, `gemini`) và LLM (`openai`, `anthropic`,
`gemini`, `mistral`, `ollama`, `template`), hệ thống được cấu hình để chạy
với Gemini trên cả embedding và generation. Mục tiêu của đợt test này:

- Nạp một văn bản HUST thật từ `data/raw/HUST/` qua pipeline ingestion.
- Dùng Gemini (`gemini-embedding-001`) để embed, lưu vào Qdrant.
- Dùng cross-encoder reranker (`BAAI/bge-reranker-v2-m3`) và LLM Gemini.
- Truy vấn, đánh giá chất lượng retrieval, ngữ nghĩa câu trả lời và thời
gian phản hồi.

---



## 2. Chuẩn bị



### 2.1. Cấu hình

Sau khi đồng bộ hóa, `.env.rag` được đặt:

```dotenv
GENERATOR_PROVIDER=openai
GENERATOR_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=
EMBEDDING_DIMENSIONS=
RERANKER_PROVIDER=cross_encoder
RERANKER_MODEL_NAME=BAAI/bge-reranker-v2-m3
```

`GEMINI_API_KEY` đã được cung cấp.

### 2.2. Khởi động hạ tầng

```bash
docker compose up -d postgres qdrant
docker compose ps   # cả hai đều healthy
```



### 2.3. Tạo metadata

Mỗi văn bản HUST cần một metadata JSON đính kèm khi ingest. Ví dụ
`data/metadata/10232.json`:

```json
{
  "title": "Quyết định phê duyệt mức học phí năm học 2025-2026",
  "document_number": "QĐ-ĐHBK-10232",
  "issued_by": "Đại học Bách khoa Hà Nội",
  "owner_department": "Phòng Tài chính",
  "issued_date": "2025-01-15",
  "effective_from": "2025-09-01",
  "effective_to": "2026-08-31",
  "access_scope": "PUBLIC",
  "allowed_departments": ["Tất cả các khoa"],
  "version_number": 1
}
```

---



## 3. Ingest PDF

```bash
PYTHONPATH=. python scripts/ingest_document.py \
    data/raw/HUST/10232.pdf \
    --metadata data/metadata/10232.json
```

Kết quả:

```json
{
  "document_id": "7728e742-b24a-4a7a-bf4f-ada2b65ff88c",
  "version_id": "8fff1832-7cef-411e-a402-c6b0b501d9bb",
  "processing_status": "review_required",
  "section_count": 44,
  "chunk_count": 46,
  "warnings": ["Tài liệu có trang scan; đã dùng OCR. ..."]
}
```

Sau đó duyệt và xuất bản:

```python
container.repository.approve_version(version_id, "admin")
container.repository.publish_version(version_id)
```

Hoặc tương đương qua REST `/admin/versions/{id}/approve` rồi
`/admin/versions/{id}/publish`.

---



## 4. Lỗi phát hiện và cách sửa



### 4.1. Bug: payload trong Qdrant thiếu `valid_from`/`valid_to`

**Triệu chứng.** Sau khi nạp 46 chunks của QĐ-ĐHBK-10232, các truy vấn có
chứa "học phí" đều bị abstain dù semantic retrieval trả về
score `0.97+` (rất tốt).

**Nguyên nhân.** Trong `src/rag/container.py::RAGContainer.warm_index`, khi
gắn payload cho điểm trong Qdrant, code đọc `payload.get("valid_from")`,
nhưng payload sinh ra từ PostgreSQL lại dùng khoá `effective_from`
(từ `DocumentVersion`). Do đó `valid_from` luôn là `None` cho mọi điểm
của văn bản mới ingest.

Hệ quả: bộ lọc Qdrant trong `build_access_filter` yêu cầu
`valid_from <= now` đều fail khi `valid_from=None`, nên dense leg rỗng,
chỉ còn sparse leg và thông tin bị loại.

**Fix.** Tại `src/rag/container.py`:

```python
# trước
payload["valid_from"] = payload.get("valid_from")
payload["valid_to"]   = payload.get("valid_to")

# sau
payload["valid_from"] = payload.get("effective_from") or payload.get("valid_from")
payload["valid_to"]   = payload.get("effective_to") or payload.get("valid_to")
```

Sau fix, gọi lại `await container.warm_index()` để đồng bộ hóa Qdrant:

```
Warmed: 52 records
```



### 4.2. Sai lệch kích thước vector của Gemini

Lần đầu đặt `EMBEDDING_DIMENSIONS=768` (theo tài liệu cũ), nhưng
`gemini-embedding-001` thực tế trả 3072 chiều. Test trực tiếp qua API
cho kết quả:

```python
len(await provider.embed_query("học phí"))  # → 3072
```

Cập nhật `.env.rag` và `.env.rag.example` với `EMBEDDING_DIMENSIONS=3072`
và thêm ghi chú rằng `CachedDenseEmbeddingProvider` đã được điều chỉnh để
lazy-detect dimension.

### 4.3. Restart Docker = mất index

Sau khi restart container Qdrant (`docker compose up -d qdrant`), index
trong collection bị xoá trong khi PostgreSQL vẫn giữ metadata. Để phục
hồi nhanh:

```python
count = await container.warm_index()  # 52 records
```

Khuyến nghị vận hành: bật persistence volume trong `docker-compose.yml`
cho cả `qdrant` lẫn `postgres`, hoặc export collection snapshot định kỳ.

### 4.4. Truy vấn quá chung bị abstain

Với cùng cấu hình, các query dạng "Đại học Bách khoa Hà Nội có địa chỉ ở
đâu?" hay "Thủ đô của Việt Nam là gì?" đều được abstain đúng — không có
thông tin trong kho văn bản. Đây là hành vi **fail-closed** mong muốn.

---



## 5. Đo đạc chất lượng & thời gian

Sau các fix, chạy bộ 6 câu hỏi thực tế:


| #   | Truy vấn                                                     | Outcome     | Thời gian |
| --- | ------------------------------------------------------------ | ----------- | --------- |
| 1   | Học phí năm 2025-2026 của HUST là bao nhiêu?                 | `abstained` | 17.96 s   |
| 2   | Học phí cho chương trình kỹ sư chuyên sâu KSCS là bao nhiêu? | `generated` | 10.46 s   |
| 3   | Học phí CTĐT ngành Khoa học dữ liệu và trí tuệ nhân tạo      | `generated` | 10.55 s   |
| 4   | Quyết định 10232 có nội dung gì?                             | `abstained` | 2.62 s    |
| 5   | Đại học Bách khoa Hà Nội có địa chỉ ở đâu?                   | `abstained` | 3.94 s    |
| 6   | Thủ đô của Việt Nam là gì?                                   | `abstained` | 12.98 s   |


**Nhận xét:**

- Truy vấn 2, 3 (câu hỏi cụ thể có trong văn bản) → trả lời đúng, có
citation, thời gian ~10–11 s.
- Truy vấn 5, 6 (ngoài phạm vi) → abstain đúng (fail-closed).
- Truy vấn 1, 4 bị abstain dù retrieval đã trả về đúng đoạn có score cao.
Nguyên nhân: sau bước rerank (cross-encoder
`BAAI/bge-reranker-v2-m3`), các `rerank_score` rơi xuống ~0.55 / 0.24,
thấp hơn ngưỡng `partial_top_score=0.40` ở một số truy vấn. Đây là đặc
tính của cross-encoder với câu hỏi ngắn và đoạn dài tiếng Việt; có thể
nâng cao chất lượng bằng cách:
  - Bật `RERANKER_PROVIDER=lexical_fallback` để chấp nhận retrieval
  fusion score cao (≥0.65) làm bằng chứng.
  - Hoặc chỉnh `EVIDENCE_THRESHOLDS` trong `.env.rag` để giảm
  `sufficient_top_score` xuống `0.45`.



### 5.1. Phân tích thời gian

Thời gian trung bình ~10 s cho một truy vấn `generated` chủ yếu đến từ:

- Lần đầu: warm reranker model (~3–5 s), warm embedding provider (~1–2 s).
- Mỗi truy vấn: embed query (~300 ms), hybrid retrieval (~500 ms), rerank
cross-encoder 60 candidates (~600–900 ms), LLM Gemini trả lời có cấu
trúc (~2–4 s).

Khi đã warm xong, truy vấn thứ 2 trở đi giảm còn 3–6 s trong môi trường
local.

---



## 6. Khuyến nghị vận hành

1. **Không dùng** `text-embedding-004` — model này không khả dụng qua
  `v1beta` API. Dùng `gemini-embedding-001` (3072 dim).
2. **Lưu** `valid_from`**/**`valid_to` trong payload khi warm index (fix đã
  cam kết trong code).
3. **Bật persistence volume** cho Qdrant và Postgres để tránh mất index
  khi restart container.
4. **Theo dõi quota Gemini** — gọi embed hàng trăm chunks có thể chạm
  rate limit; script ingest lớn nên được throttle hoặc chuyển sang
   `sentence_transformers` local cho batch embedding.
5. **Nâng cấp retrieval/evidence gate** cho câu hỏi tiếng Việt ngắn:
  dùng `lexical_fallback` rerank hoặc hạ `sufficient_top_score` trong
   `EVIDENCE_THRESHOLDS`.

---



## 7. Tài liệu liên quan

- `docs/TESTING_RAG_PIPELINE.md` — hướng dẫn smoke test tổng quát và E2E
với `5445.pdf` cùng `sentence_transformers` embedding.
- `docs/rag_database_architecture.md` — kiến trúc as-built của module
RAG.
- `docs/pdf_processing_pipeline.md` — pipeline parse và OCR.
- `docs/DATA_PROCESSING_FLOW.md` — luồng `Upload → Parse/Chunk → Approve → Index → Publish` và các ràng buộc trạng thái.
- `docs/ARCHITECTURE_CHANGES_MULTI_PROVIDER.md` — multi-provider
embedding/LLM.
- `.env.rag.example` — tham chiếu biến môi trường đầy đủ (multi-provider).

---



## 8. Cập nhật 2026-08-13: Review luồng dữ liệu

Review yêu cầu: "Luồng chuẩn: `Upload → Parse/Chunk → Approve → Index Qdrant → Publish`. Chỉ được Publish sau khi tạo vector và lưu Qdrant thành công. Nếu
index lỗi, giữ trạng thái APPROVED và trả thông báo lỗi."

### 8.1. Gap phát hiện được


| #   | Gap                                                                                                    | Mức độ       |
| --- | ------------------------------------------------------------------------------------------------------ | ------------ |
| 1   | `publish_version` cho phép nhảy thẳng APPROVED → PUBLISHED (bypass Index)                              | **Critical** |
| 2   | `index_approved_version` không catch exception → status có thể bị âm thầm fail                         | **Critical** |
| 3   | Không có API route `/admin/documents/{id}/index` riêng                                                 | **High**     |
| 4   | `_parse_with_pdf_processor` hardcode `dpi=300`, không truyền config OCR/Preprocess                     | **High**     |
| 5   | Dockerfile chỉ cài `requirements.txt`, thiếu `pymupdf`, `easyocr`, `docling`, `opencv-python-headless` | **Critical** |




### 8.2. Fix đã áp dụng

1. `publish_version` **strict gate** (`src/db/repository.py`): chỉ chấp nhận
  `processing_status == INDEXED`. Raise `ValueError` khi chưa index.
2. `index_approved_version` **3-phase** (`src/ingestion/pipeline.py`):
  - Phase 1: read-only snapshot.
  - Phase 2: embed + Qdrant upsert trong `try / except`.
  - Phase 3: chỉ `mark_indexed` khi Phase 2 OK.
  - Khi fail: raise `RuntimeError` với message chi tiết, status vẫn `APPROVED`.
3. **API** `/admin/documents/{id}/index` (`src/api/admin_routes.py`): route
  mới cho Index step, trả 502 khi Qdrant fail với message rõ ràng.
4. **OCR config từ RAGSettings** (`src/ingestion/parser.py` + `src/rag/container.py`):
  - `DocumentParser` nhận thêm `ocr_languages`, `ocr_gpu`, `preprocess_dpi`,
   `preprocess_binary_threshold`, `detect_tables`, `vlm_enabled`, ...
  - Build `PipelineConfig` từ settings, không còn hardcode DPI.
5. **Dockerfile đầy đủ deps** (`Dockerfile`): cài `requirements-docling.txt`
  cho cả build stage (gcc, libpq-dev, libgl1, poppler-utils) và runtime
   stage (libgl1, libglib2.0-0, poppler-utils, tesseract-ocr).



### 8.3. Test mới (8 test bổ sung)


| Test                                                                 | File                                       |
| -------------------------------------------------------------------- | ------------------------------------------ |
| `test_publish_blocks_when_status_is_only_approved`                   | `tests/test_db_repository_publish_gate.py` |
| `test_publish_blocks_when_status_is_failed`                          | `tests/test_db_repository_publish_gate.py` |
| `test_publish_succeeds_only_when_indexed`                            | `tests/test_db_repository_publish_gate.py` |
| `test_publish_blocks_when_version_missing`                           | `tests/test_db_repository_publish_gate.py` |
| `test_index_approved_version_raises_runtime_when_vector_store_fails` | `tests/test_ingestion_pipeline_flow.py`    |
| `test_index_approved_version_calls_mark_indexed_only_on_success`     | `tests/test_ingestion_pipeline_flow.py`    |
| `test_publish_blocked_when_repository_rejects_unindexed_state`       | `tests/test_rag/test_admin_routes.py`      |
| `test_index_endpoint_indexes_approved_version`                       | `tests/test_rag/test_admin_routes.py`      |
| `test_index_endpoint_returns_502_when_indexing_fails`                | `tests/test_rag/test_admin_routes.py`      |


Tổng cộng: **324/324 tests pass**.

### 8.4. Re-test pipeline với HUST corpus

```bash
docker compose up -d postgres qdrant
PYTHONPATH=. python scripts/ingest_hust_corpus.py --approve-publish
```

Kết quả:


| File      | Status      | Sections | Chunks   | Notes                 |
| --------- | ----------- | -------- | -------- | --------------------- |
| 10232.pdf | `published` | 27       | 46       | QĐ học phí 2025-2026  |
| 10728.pdf | `published` | 70       | 77       | Quy định ngoại ngữ    |
| 2048.pdf  | `published` | 71       | 77       | Phân loại trình độ NN |
| 5445.pdf  | `published` | existing | existing | Quy chế đào tạo       |
| 7737.pdf  | `published` | 27       | 27       | Bộ tiêu chí CĐT kỹ sư |
| 5980.pdf  | `failed`    | –        | –        | Scan PDF, cần `--ocr` |
| 6100.pdf  | `failed`    | –        | –        | Scan PDF, cần `--ocr` |
| 7323.pdf  | `failed`    | –        | –        | Scan PDF, cần `--ocr` |




### 8.5. Query test sau fix

3/3 truy vấn cho `outcome: generated` với citations chính xác:


| #   | Query                                                                      | Top citations       | Thời gian |
| --- | -------------------------------------------------------------------------- | ------------------- | --------- |
| 1   | "Quyết định số 10232 quy định mức học phí 2025-2026 như thế nào?"          | `QĐ-ĐHBK-10232` (2) | ~15 s     |
| 2   | "Theo quy chế ĐHBK, sinh viên ra trường phải đạt chuẩn ngoại ngữ gì?"      | `10728/QĐ-ĐHBK` (1) | ~10 s     |
| 3   | "Bộ tiêu chí chương trình đào tạo kỹ sư chuyên sâu quy định điều kiện gì?" | `7737/QĐ-ĐHBK` (2)  | ~14 s     |




### 8.6. Self-check trước khi có thể chuyển Production

- [x] Publish **chỉ** được gọi từ `INDEXED` → API từ chối nếu chỉ `APPROVED`.
- [x] Index fail → status `APPROVED`, error message rõ ràng, có thể retry.
- [x] OCR config từ `.env.rag` đến tận `PipelineConfig`.
- [x] Docker có đủ deps PDF/OCR (libgl, poppler, easyocr, pymupdf).
- [x] Test bổ sung chống regression.
- [ ] Bật persistence volume cho Qdrant (chưa làm, chỉ là cấu hình).
- [ ] Fix 3 file scan PDF (5980/6100/7323) cần `--ocr` flag (chưa production).