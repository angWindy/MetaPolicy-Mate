# PDF Processing Pipeline (post-refactor 2026-08-25, OCR handoff 2026-09-05)

> Phiên bản rút gọn, thay thế cho `NOTES_PDF_PROCESSING.md` (ghi chú thực
> nghiệm cũ) và `docs/pdf_processing_pipeline.md` (thiết kế ban đầu có OCR).

## 1. Stack hiện tại

| Bước              | Công cụ                            | Ghi chú                                          |
| ----------------- | ---------------------------------- | ------------------------------------------------ |
| PDF text          | `pypdf`                            | Text-layer digital. Mặc định cho mọi PDF.        |
| PDF + bảng        | `pypdf` + `pdfplumber`             | Backend `pypdf_table`. Bảng → Markdown.          |
| DOCX              | `python-docx`                      | Paragraph + table → Markdown.                    |
| TXT               | thuần Python                        | Hỗ trợ UTF-8/16 và CP1258.                       |
| OCR               | RapidOCR + PP-OCRv6 Vietnamese ONNX | Hybrid gate (text-extract-first, OCR fallback).  |

## 2. Nguyên tắc

1. **Digital-first (hybrid gate).** Pipeline đọc lớp text có sẵn trước
   (PyMuPDF). Trang nào có ≥ 50 ký tự text (`PipelineConfig.hybrid_text_threshold`)
   sẽ bỏ qua OCR hoàn toàn — kể cả khi `PageClassifier` ban đầu gán nhãn
   `SCAN` / `HYBRID`. Ngược lại, trang `DIGITAL` với text < 50 ký tự
   sẽ được chuyển qua nhánh OCR để bù nội dung (vd. trang bìa có nhiều
   stamp/seal ảnh). Ngưỡng chỉnh được qua env `OCR_HYBRID_TEXT_THRESHOLD`
   (mặc định 50; đặt `None` để tắt override).
2. **Hành vi ô ảnh.** Với cell chỉ có ảnh (không có text layer), pipeline
   chuyển sang nhánh OCR. OCR trả về text qua RapidOCR + PP-OCRv6
   Vietnamese ONNX (xem [`docs/OCR_BACKENDS.md`](OCR_BACKENDS.md)).
3. **Bảng là first-class.** Bảng từ `pdfplumber` được giữ nguyên Markdown
   và gắn `block_type="table"`, `source="table_parser"` để chunker không
   xé thành các khoản giả. Bảng có ảnh (scanned table) đi qua OCR cell-level.
4. **Metadata giữ nguyên.** Mỗi `ParsedBlock` có `page`, `source`,
   `confidence` (None đối với born-digital, ≥ 0 cho OCR), `bbox` (nếu
   parser cung cấp).
5. **Vietnamese diacritic là P0.** OCR pipeline giữ nguyên dấu thanh
   tiếng Việt; kiểm tra bằng diacritic ratio gate ≥ 0.05 trên các trang
   scan. Lý do và audit evidence xem
   `.cursor/plans/ocr_migration_plan_(with_deep_vietnamese_audit)_dec89d70.plan.md`.

## 3. Backend parser

`src/ingestion/parser.py` cung cấp `DocumentParser` với 4 backend:

| `parser_backend` | Hành vi                                              |
| ---------------- | ----------------------------------------------------- |
| `"auto"`         | Mặc định. Tự route file `<stem>-table.pdf` sang `pypdf_table`. |
| `"pypdf"`        | Text-only, không xử lý bảng riêng.                    |
| `"pypdf_table"`  | pypdf + pdfplumber.                                  |
| `"docling"`      | Tương thích ngược — hiện map sang `pypdf`.            |

## 4. OCR engine (RapidOCR + PP-OCRv6 Vietnamese)

`src/ingestion/pdf_processor/ocr_engine.py` đã được migrate từ PaddleOCR
sang **RapidOCR + PP-OCRv6_mobile_rec ONNX** (single-engine, không qua
factory). Public surface (`recognize` / `recognize_region` / `warmup` /
`close`) giữ nguyên để pipeline không phải đổi signature.

| Khía cạnh                | Giá trị                                        |
| ------------------------ | ---------------------------------------------- |
| Recognition model        | `data/ocr/outputs/onnx_models/rec_vi/inference.onnx` (73 MB, gitignored) |
| Dictionary               | `data/ocr/outputs/onnx_models/rec_vi/dict.txt` (18 708 chars) |
| Detection + cls models   | Bundled defaults từ `rapidocr_onnxruntime`     |
| DPI                      | 200 cho body pages, 600 cho cover page         |
| Score threshold          | 0.5                                             |
| Hybrid text gate         | 50 chars (env `OCR_HYBRID_TEXT_THRESHOLD`)     |

Xem chi tiết cài đặt, diacritic gate, A/B bench scripts tại
[`docs/OCR_BACKENDS.md`](OCR_BACKENDS.md).

## 5. Di sản

- Lịch sử thử nghiệm với EasyOCR, PaddleOCR và factory abstraction xem
  `git log src/ingestion/pdf_processor/` (factory package
  `ocr_backends/` đã được gỡ bỏ 2026-09-05; commit trước đó nếu cần
  tham khảo).
- Diacritic audit + bench reports (188, 2517, low-DPI sweep) tại
  `data/ocr/outputs/REPORT.md` và `data/ocr/outputs/bench_*.json`.

## 6. Tài liệu liên quan

- [`docs/OCR_BACKENDS.md`](OCR_BACKENDS.md) — RapidOCR + PP-OCRv6 Vietnamese
  engine, hybrid gate, diacritic gate, A/B bench scripts.
- [`docs/PDF_PROCESSING.md`](PDF_PROCESSING.md) — file này.
- `ARCHITECTURE.md` section 4.4 — kiến trúc tổng thể ingestion.
- `README.md` — quick start & dependency overview.
- [`docs/rag_database_architecture.md`](rag_database_architecture.md) —
  chi tiết schema và pipeline RAG.

## 7. Kết quả thực nghiệm (HUST batch hiện tại)

| File             | Pages | Backend       | Sections | Chunks |
| ---------------- | ----- | ------------- | -------- | ------ |
| 10232.pdf        | 7     | pypdf         | 24       | 41     |
| 10714-table.pdf  | 11    | pypdf_table   | 15       | 30     |
| 10728.pdf        | 20    | pypdf         | 51       | 77     |
| 2048-table.pdf   | 24    | pypdf_table   | 97       | 99     |
| 5445.pdf         | 34    | pypdf         | 252      | 445    |
| 7737.pdf         | 4     | pypdf         | 17       | 27     |
| 956-table.pdf    | 7     | pypdf_table   | 48       | 48     |
