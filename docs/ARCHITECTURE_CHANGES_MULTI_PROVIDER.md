# Thay đổi kiến trúc — Multi-provider Embedding/LLM & Gemini Integration

> **Cập nhật 2026-08-25:** Phần "OCR/PDF processing" (sections liên quan)
> mô tả stack OCR đã lỗi thời. Đã refactor sang `pypdf` + `pdfplumber` +
> `python-docx` (xem [`docs/PDF_PROCESSING.md`](PDF_PROCESSING.md)).

> Ghi nhận các thay đổi kiến trúc được thực hiện để hỗ trợ đa provider
> cho embedding và LLM, tích hợp Gemini (`gemini-embedding-001` +
> `gemini-2.5-flash`), và khắc phục các bug phát hiện khi vận hành với
> PDF HUST thật.

---

## 1. Bối cảnh

Trước đây hệ thống chỉ hỗ trợ `openai` cho cả embedding và LLM. Khi
chuyển sang dùng Gemini (free tier), cần:

- Mở rộng enum `embedding_provider` và `generator_provider` để chấp
  nhận nhiều provider.
- Hỗ trợ các embedding model mà kích thước vector chỉ biết sau lần gọi
  đầu tiên (lazy dimension detection).
- Refactor factory LLM để tập trung hóa việc khởi tạo và structured
  output.
- Chuẩn hóa cấu hình: gộp `Settings` (cũ) và `RAGSettings` thành một.

---

## 2. Sơ đồ trước/sau

### Trước

```
src/
├── config.py               # Settings (app-level)
├── services/
│   ├── llm.py              # ChatOpenAI trực tiếp
│   └── embeddings.py       # chỉ hỗ trợ openai/sentence_transformers/ollama
└── rag/
    ├── config.py           # RAGSettings (RAG-only)
    └── container.py
```

### Sau

```
src/
├── services/
│   ├── llm_factory.py      # build_llm() - chat model đa provider + structured output
│   ├── llm.py              # backward-compat wrapper cho build_llm()
│   └── embeddings.py       # build_embedding_provider() + GeminiEmbeddingProvider
└── rag/
    ├── config.py           # RAGSettings (hợp nhất app + RAG + OCR/PDF)
    └── container.py        # warm_index fix valid_from/effective_from
```

---

## 3. Hợp nhất cấu hình (`RAGSettings`)

`src/config.py` (Settings) bị xoá. `RAGSettings` trong `src/rag/config.py`
bây giờ chứa toàn bộ:

- **App-level**: `app_name`, `app_env`, `app_host`, `app_port`,
  `log_level`, `cors_origins`.
- **RAG**: tất cả các trường provider/embedding/retrieval/reranker.
- **OCR/PDF processing**: `ocr_enabled`, `ocr_gpu`, `ocr_languages`,
  `ocr_batch_size`, `ocr_workers`, `ocr_min_confidence`,
  `ocr_low_confidence_threshold`, `preprocess_mode`, `preprocess_dpi`,
  `preprocess_binary_threshold`, `preprocess_denoise`,
  `preprocess_sharpen`, `detect_tables`, `vlm_enabled`,
  `vlm_review_threshold`.
- **Evidence gate** (per-domain thresholds).

Tất cả consumers (`src/main.py`, `src/services/llm.py`, các script)
chuyển sang dùng `get_rag_settings()` / `RAGSettings()` trực tiếp.

---

## 4. Embedding factory

### 4.1. Provider mới: `GeminiEmbeddingProvider`

`src/services/embeddings.py` thêm provider cho Google Gemini:

```python
class GeminiEmbeddingProvider:
    def __init__(self, settings: RAGSettings) -> None:
        self.settings = settings
        self.client = GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=settings.gemini_api_key,
            task_type="retrieval_document",
        )
        self._dimensions: int | None = None  # lazy

    async def embed_query(self, text: str) -> list[float]:
        vector = await self.client.aembed_query(text)
        if self._dimensions is None:
            self._dimensions = len(vector)
        return vector
```

### 4.2. Lazy dimension detection

Một số provider (Gemini, OpenAI v3) cho phép thay đổi số chiều vector
mà không báo trước. `CachedDenseEmbeddingProvider` được chỉnh để:

- Đọc `self._dimensions` (lazy) thay vì đọc trực tiếp từ provider.
- Không gọi `validate_embedding_dimension` cho tới khi thực sự embed.
- Khi nhận vector đầu tiên, tự động ghi nhận dimension vào
  `self._dimensions`.

### 4.3. `build_embedding_provider` đa nhánh

```python
def build_embedding_provider(settings: RAGSettings) -> EmbeddingProvider:
    provider = settings.embedding_provider
    if provider == "hash":
        return HashEmbeddingProvider(...)
    if provider == "openai":
        return OpenAIEmbeddingProvider(...)
    if provider == "sentence_transformers":
        return SentenceTransformersProvider(...)
    if provider == "ollama":
        return OllamaEmbeddingProvider(...)
    if provider == "gemini":
        return GeminiEmbeddingProvider(settings)
    # ...
```

Validation cho production (`validate_production_configuration`) kiểm tra
`GEMINI_API_KEY` khi `EMBEDDING_PROVIDER=gemini`.

---

## 5. LLM factory

### 5.1. `src/services/llm_factory.py`

Đã có sẵn từ trước (xem `RAGPipeline` và `AnswerGenerator`) nhưng nay
được dùng làm điểm truy cập duy nhất:

```python
def build_llm(settings: RAGSettings, *, with_structured_output: bool = True):
    provider = settings.generator_provider
    match provider:
        case "openai":
            model = ChatOpenAI(model=settings.generator_model, ...)
        case "anthropic":
            model = ChatAnthropic(model=settings.generator_model, ...)
        case "gemini":
            model = ChatGoogleGenerativeAI(model=settings.generator_model, ...)
        case "mistral":
            model = ChatMistralAI(model=settings.generator_model, ...)
        case "ollama":
            model = ChatOllama(model=settings.generator_model, ...)
        case "template":
            return TemplateAnswerGenerator(...)
        case _:
            raise ValueError(...)
    if with_structured_output:
        return model.with_structured_output(AnswerSchema)
    return model
```

### 5.2. Lazy initialization

`AnswerGenerator` chỉ gọi `build_llm()` khi thực sự sinh câu trả lời.
Điều này giúp:

- Không tốn chi phí khởi tạo khi chỉ chạy smoke test embedding-only.
- Không validate API key khi chỉ chạy ingestion.
- Tránh import-time exception cho `template` provider.

### 5.3. Backward-compat

`src/services/llm.py` (cũ) vẫn tồn tại nhưng chỉ re-export từ factory:

```python
def build_answer_generator(settings):
    from src.services.llm_factory import build_llm
    return build_llm(settings, with_structured_output=True)
```

---

## 6. Sửa bug payload trong `warm_index`

`RAGContainer.warm_index` (trước) đọc `valid_from`/`valid_to` trong
payload, nhưng `Repository.list_published_chunks_for_index` chỉ sinh
`effective_from`/`effective_to`. Kết quả: filter trong
`build_access_filter` không match được các chunks mới.

Fix đã hợp nhất cả hai tên:

```python
payload["valid_from"] = payload.get("effective_from") or payload.get("valid_from")
payload["valid_to"]   = payload.get("effective_to") or payload.get("valid_to")
```

Đồng thời, `validate_embedding_dimension` không còn được gọi trong
`CachedDenseEmbeddingProvider` vì lazy detection đã xử lý.

---

## 7. Sửa lỗi dimension mismatch với Gemini

`gemini-embedding-001` trả về vector 3072 chiều, không phải 768 như
một số tài liệu gợi ý. Đã sửa:

- `.env.rag.example`: thêm `EMBEDDING_DIMENSIONS=3072`.
- `RAGSettings.embedding_dimensions`: thêm validation rằng giá trị
  phải là 1 trong `{768, 1024, 1536, 2048, 3072}` để phát hiện sai
  ngay từ cấu hình.

---

## 8. Hỗ trợ cấu hình OCR/PDF processing

`RAGSettings` mở rộng với các tham số điều khiển pipeline parse và OCR:

- `ocr_languages`: danh sách BCP-47 (ví dụ `vi,en`).
- `preprocess_dpi`, `preprocess_binary_threshold`,
  `preprocess_denoise`, `preprocess_sharpen` — chuẩn bị ảnh cho OCR.
- `detect_tables` — bật/tắt phát hiện bảng.
- `vlm_enabled`, `vlm_review_threshold` — chuẩn bị cho VLM review các
  trang có độ tin cậy thấp.

**Cập nhật 2026-08-13**: Toàn bộ config này được truyền từ `RAGSettings`
xuống `PDFProcessingPipeline` thông qua `RAGContainer.parser`. Trước đây
`_parse_with_pdf_processor` hardcode `dpi=300` và bỏ qua nhiều tuỳ chọn.
Bây giờ:

- `DocumentParser.__init__` nhận `ocr_languages`, `ocr_gpu`,
  `preprocess_dpi`, `preprocess_binary_threshold`, `detect_tables`,
  `vlm_enabled`, `vlm_review_threshold`.
- `RAGContainer` build `DocumentParser` từ `RAGSettings` (constructor
  nhận tất cả các trường trên).
- `_parse_with_pdf_processor` build `PipelineConfig` (gồm `OCRConfig`,
  `PreprocessConfig`, `TableConfig`) từ các trường đó; image preprocessor
  cũng được override với `PreprocessConfig(dpi=settings.preprocess_dpi,
  binary_threshold=settings.preprocess_binary_threshold, ...)`.

Kiểm chứng: `scripts/ingest_hust_corpus.py --ocr` chạy thành công với
các file scan PDF (xem `docs/DATA_PROCESSING_FLOW.md` section 4).

---

## 9. Ảnh hưởng tới các script & tests

- `scripts/ingest_document.py` chạy được với mọi provider.
- `scripts/smoke_chat_real.py` đã được điều chỉnh để nhận
  `--corpus` (cho test với fixture synthetic).
- `tests/test_services/test_embedding_factory.py` bổ sung test cho
  `HashEmbeddingProvider` và `CachedDenseEmbeddingProvider`.
- `tests/test_services/test_llm_factory.py` đã fix các expectation
  sau khi refactor `RAGSettings`.
- `tests/test_rag/test_observability.py` đã được viết lại để không
  phụ thuộc vào `caplog` + `structlog` (vốn khó cấu hình trong test
  environment).

---

## 10. Tổng kết

Thay đổi kiến trúc lần này đạt được:

- **Một cấu hình duy nhất** (`RAGSettings`) bao trùm toàn bộ ứng
  dụng, RAG, OCR/PDF.
- **Đa provider** cho embedding và LLM, không hard-code cho OpenAI.
- **Lazy init** cho LLM/embedding, tránh lỗi import-time khi thiếu
  key.
- **Lazy dimension** cho các provider động như Gemini.
- **Sửa bug payload** trong `warm_index`, đảm bảo filter truy cập
  áp dụng đúng cho văn bản mới ingest.
- **OCR/PDF config** từ `RAGSettings` được truyền tận xuống
  `PipelineConfig` (cập nhật 2026-08-13).

## 11. Cập nhật 2026-08-13: Strict Publish Gate

Review yêu cầu đảm bảo luồng `Upload → Parse/Chunk → Approve → Index →
Publish` không có chỗ nào nhảy bước. Cụ thể:

### 11.1. `publish_version` chỉ chấp nhận `INDEXED`

```python
# src/db/repository.py
if version.processing_status != ProcessingStatus.INDEXED.value:
    raise ValueError(
        "Phiên bản phải được duyệt (approved) rồi tạo vector trong Qdrant "
        "(indexed) trước khi xuất bản. Hiện tại: "
        f"processing_status={version.processing_status}."
    )
```

Đảm bảo PostgreSQL không báo `PUBLISHED` trong khi Qdrant rỗng.

### 11.2. `index_approved_version` 3-phase

- **Phase 1**: read-only snapshot (DB).
- **Phase 2**: embed + Qdrant upsert (try/except → RuntimeError nếu fail).
- **Phase 3**: chỉ `mark_indexed` khi Phase 2 OK.

Status khi fail: vẫn `APPROVED`, có thể retry.

### 11.3. API `/admin/documents/{id}/index` mới

Trả 200 với `indexed_chunks` khi thành công, 502 với message chi tiết
khi Qdrant fail.

### 11.4. Dockerfile đầy đủ deps PDF/OCR

`requirements-docling.txt` (pymupdf, easyocr, docling, opencv-python-headless)
được cài trong cả build và runtime. Có `libgl1`, `libglib2.0-0`,
`poppler-utils`, `tesseract-ocr` cho runtime.

### 11.5. Test bổ sung

9 tests mới (`tests/test_db_repository_publish_gate.py`,
`tests/test_ingestion_pipeline_flow.py`, `tests/test_rag/test_admin_routes.py`)
bảo vệ strict gate. 324/324 tests pass.

Xem `docs/DATA_PROCESSING_FLOW.md` cho spec đầy đủ.

Các tài liệu liên quan:

- `docs/rag_database_architecture.md` — kiến trúc as-built tổng thể.
- `docs/TESTING_RAG_PIPELINE.md` — hướng dẫn smoke test & E2E.
- `docs/E2E_HUST_10232_TEST.md` — log trải nghiệm thực tế với PDF.
- `docs/DATA_PROCESSING_FLOW.md` — luồng `Upload → Parse/Chunk → Approve →
  Index → Publish` và ràng buộc trạng thái.