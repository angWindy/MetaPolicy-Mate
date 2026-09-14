# Kịch bản Kiểm thử Hệ thống RAG (RAG System Test Scenarios)

Tài liệu tổng hợp các kịch bản kiểm thử (Test Scenarios & Test Cases) cho hệ thống **Enterprise RAG (PolicyMeta AI)**, bao gồm toàn bộ luồng xử lý từ Ingestion, Bảo mật RBAC, Hybrid Retrieval, Evidence Gate cho đến sinh câu trả lời kèm Citation.

---

## 1. Danh mục Kịch bản Kiểm thử (Test Suite Overview)

| Mã Kịch bản (Suite ID) | Tên Phân hệ (Module) | Số lượng Test Cases | Mục tiêu Kiểm thử |
| :--- | :--- | :---: | :--- |
| **TS-INGESTION** | Nạp & Tiền xử lý Dữ liệu | 5 | Kiểm tra nạp file, Magic Bytes, chuyển đổi Markdown & Idempotency. |
| **TS-SECURITY** | Phân quyền & Hiệu lực (RBAC) | 3 | Kiểm tra Pre-filter bảo mật, quyền phòng ban và thời gian hiệu lực. |
| **TS-RETRIEVAL** | Truy xuất Hybrid & Rerank | 3 | Kiểm tra BM25, Dense Vector Search, Reranking & Context Expansion. |
| **TS-GENERATION** | Evidence Gate & Citation | 4 | Kiểm tra đánh giá bằng chứng, sinh câu trả lời, Citation & Abstain. |

---

## 2. Chi tiết Kịch bản Kiểm thử (Detailed Test Cases)

### 2.1. Phân hệ Nạp Dữ liệu (Ingestion Pipeline - TS-INGESTION)

#### `TC-ING-01`: Upload file hợp lệ (PDF/DOCX/TXT)
* **Tiền điều kiện:** Người dùng có quyền Data Owner, hệ thống đang hoạt động.
* **Các bước thực hiện:**
  1. Upload tệp quy định hợp lệ `Quy_dinh_IT_2026.pdf` (chứa text layer, kích thước < 20MB).
  2. Gửi kèm metadata bắt buộc (`document_number`, `title`, `effective_from`, `allowed_departments`).
* **Kết quả mong đợi:**
  - File pass qua bước `file_validator`.
  - Hệ thống bóc tách thành công sang định dạng Unified Markdown.
  - Nhận diện đúng cấu trúc Chương/Điều/Khoản và tạo các Chunks có `UUIDv5` cố định.
  - Trạng thái phiên bản đặt thành `processing_status = review_required`.

#### `TC-ING-02`: Upload file giả mạo định dạng (Magic Bytes Signature Failure)
* **Tiền điều kiện:** File văn bản thô `.txt` được đổi tên thành `Bao_cao_gia.pdf`.
* **Các bước thực hiện:**
  1. Upload tệp `Bao_cao_gia.pdf` lên API Nạp dữ liệu.
* **Kết quả mong đợi:**
  - `file_validator` phát hiện chuỗi byte đầu không bắt đầu bằng `%PDF-`.
  - Hệ thống từ chối nạp file và trả về báo lỗi: `"Định dạng PDF không hợp lệ (Magic Bytes không khớp '%PDF'). Tệp có thể giả mạo hoặc bị hỏng."`

#### `TC-ING-03`: Upload file quá dung lượng hoặc rỗng
* **Tiền điều kiện:** Cấu hình `MAX_UPLOAD_MB = 20`.
* **Các bước thực hiện:**
  1. Thử upload tệp 0 byte `empty.txt`.
  2. Thử upload tệp `heavy_document.pdf` dung lượng 35MB.
* **Kết quả mong đợi:**
  - Tệp 0 byte bị chặn với lỗi `"Tệp rỗng."`
  - Tệp 35MB bị chặn với lỗi `"Tệp vượt quá giới hạn 20 MB."`

#### `TC-ING-04`: Upload file lặp lại (Idempotency & Checksum Check)
* **Tiền điều kiện:** Tệp `Quy_trinh_Bao_mat.pdf` đã được nạp thành công ở phiên bản 1.
* **Các bước thực hiện:**
  1. Upload lại chính tệp `Quy_trinh_Bao_mat.pdf` mà không thay đổi nội dung.
* **Kết quả mong đợi:**
  - Hệ thống tính SHA-256 Checksum và phát hiện đã tồn tại trong DB.
  - Trả về cảnh báo trùng lặp tệp và chỉ ra `version_id` đã nạp trước đó.

#### `TC-ING-05`: Bóc tách Bảng biểu sang Markdown (Table Conversion)
* **Tiền điều kiện:** Tệp `Biêu_phi_dich_vu.docx` chứa các bảng biểu biểu phí nhiều cột.
* **Các bước thực hiện:**
  1. Upload tệp `.docx` chứa bảng.
* **Kết quả mong đợi:**
  - Parser tự động chuyển các dòng/cột của bảng thành cấu trúc **Markdown Table** chuẩn (`| Header 1 | Header 2 |`).
  - Chunk sinh ra giữ nguyên cấu trúc Markdown Table không bị rách dòng.

---

### 2.2. Phân hệ Phân quyền & Hiệu lực (RBAC & Policy Filter - TS-SECURITY)

#### `TC-SEC-01`: Truy vấn tài liệu Public từ người dùng Staff
* **Tiền điều kiện:** Tài liệu `Quy_che_Noi_bu.pdf` có `access_scope = PUBLIC` (canonical 2-value `AccessScope`).
* **Các bước thực hiện:**
  1. Người dùng có `UserContext` vai trò `staff` gửi câu hỏi tìm kiếm.
* **Kết quả mong đợi:**
  - `build_policy_node` tạo filter chấp nhận cho phép truy xuất.
  - Tìm kiếm trả về kết quả thành công.

#### `TC-SEC-02`: Chặn tài liệu Confidential khác Phòng ban (Department Isolation)
* **Tiền điều kiện:** Tài liệu `Luong_Thuong_RND.pdf` thuộc `owner_department = RND`, `access_scope = DEPARTMENT` (canonical 2-value `AccessScope`), `allowed_departments = ["RND"]`.
* **Các bước thực hiện:**
  1. Người dùng thuộc phòng `HR` gửi câu hỏi hỏi đáp về lương R&D.
* **Kết quả mong đợi:**
  - `build_policy_node` tự động chèn bộ lọc Pre-filter `allowed_departments CONTAINS 'HR'`.
  - Qdrant/PostgreSQL lọc bỏ toàn bộ các Chunks của tài liệu này trước khi xếp hạng.
  - Hệ thống không trả về dữ liệu bị cấm.

#### `TC-SEC-03`: Tự động loại bỏ Văn bản hết hiệu lực (Legal Status Expiration)
* **Tiền điều kiện:** Quy định V1 có `effective_to = 2025-12-31` (đã hết hạn so với thời điểm hiện tại `2026-08-08`).
* **Các bước thực hiện:**
  1. Người dùng tra cứu quy định chung.
* **Kết quả mong đợi:**
  - Hàm `refresh_current_legal_statuses()` đánh dấu quy định V1 là `expired`.
  - Truy vấn tự động loại bỏ các Chunks hết hạn ra khỏi không gian tìm kiếm.

---

### 2.3. Phân hệ Truy xuất & Reranking (Retrieval & Rerank - TS-RETRIEVAL)

#### `TC-RET-01`: Tìm kiếm chính xác theo Mã Văn bản (Exact BM25 Match)
* **Các bước thực hiện:**
  1. Nhập câu hỏi chứa mã văn bản chính xác: `"Quy định số QĐ-2026/IT quy định gì?"`
* **Kết quả mong đợi:**
  - Nhánh Keyword Search (BM25 Sparse) trả về đúng văn bản `QĐ-2026/IT` với điểm số cao nhất.
  - Reciprocal Rank Fusion (RRF) đưa văn bản này lên vị trí đầu tập ứng viên.

#### `TC-RET-02`: Tìm kiếm Ngữ nghĩa & Cross-Encoder Rerank (Semantic Hybrid Search)
* **Các bước thực hiện:**
  1. Nhập câu hỏi dùng từ đồng nghĩa/diễn đạt khác: `"Làm sao để đăng ký nghỉ phép năm?"` (Văn bản gốc ghi *"Quy trình xin nghỉ phép thường niên"*).
* **Kết quả mong đợi:**
  - Dense Vector Search tìm thấy các chunk liên quan đến "nghỉ phép thường niên".
  - Cross-Encoder Reranker (`rerank_node`) tái xếp hạng lại tập candidates và chọn đúng chunk có độ liên quan cao nhất.

#### `TC-RET-03`: Mở rộng Ngữ cảnh (Context Expansion)
* **Các bước thực hiện:**
  1. Tra cứu một Điều khoản dài bị tách thành nhiều Chunks nhỏ.
* **Kết quả mong đợi:**
  - `expand_context_node` phát hiện chunk thắng cuộc thuộc một Điều khoản dài và tự động kéo thêm các chunk lân cận trong cùng `section_id` nếu nằm trong ngân sách Token (`context_token_budget`).

---

### 2.4. Phân hệ Evidence Gate & Sinh Câu trả lời (Generation & Citation - TS-GENERATION)

#### `TC-GEN-01`: Bằng chứng đầy đủ (Sufficient Evidence & Grounded Answer)
* **Các bước thực hiện:**
  1. Đặt câu hỏi có căn cứ rõ ràng trong tài liệu đã nạp.
* **Kết quả mong đợi:**
  - `evidence_gate_node` đánh giá trạng thái `SUFFICIENT`.
  - Generator sinh câu trả lời chính xác, 100% căn cứ trên `selected_chunks`.
  - `validate_citation_node` xác minh Citation khớp đúng `document_id`, `version_id`, `section_id`, `chunk_id`.

#### `TC-GEN-02`: Cải biên câu hỏi khi Bằng chứng yếu (Query Rewrite & Retry)
* **Các bước thực hiện:**
  1. Đặt câu hỏi quá ngắn hoặc thiếu từ khóa ngữ cảnh.
* **Kết quả mong đợi:**
  - `evidence_gate_node` đánh giá trạng thái `WEAK`.
  - Workflow chuyển sang `rewrite_query_node` bổ sung từ khóa ngữ cảnh và thực hiện truy vấn lại (`attempts < max`).

#### `TC-GEN-03`: Từ chối trả lời an toàn khi thiếu căn cứ (Safe Abstain Fallback)
* **Các bước thực hiện:**
  1. Đặt câu hỏi không hề có trong bất kỳ văn bản quy định nào của hệ thống (ví dụ: *"Giá vàng hôm nay bao nhiêu?"*).
* **Kết quả mong đợi:**
  - `evidence_gate_node` đánh giá trạng thái `NOT_FOUND`.
  - Workflow lập tức điều hướng sang `abstain_node`.
  - Trả về câu trả lời an toàn chuẩn: `"Tôi chưa có đủ căn cứ văn bản để trả lời câu hỏi này."` và `confidence = low`.

#### `TC-GEN-04`: Bắt lỗi Citation giả mạo (Citation Verification Guard)
* **Các bước thực hiện:**
  1. Giả lập trường hợp LLM sinh ra một mã `chunk_id` không tồn tại trong danh sách ứng viên đã tìm thấy.
* **Kết quả mong đợi:**
  - `validate_citation_node` phát hiện Citation không hợp lệ.
  - Hạ điểm tin cậy `outcome = unverified`, loại bỏ citation bịa đặt khỏi phản hồi cuối cùng.

---

## 3. Hướng dẫn Chạy Kiểm thử (Test Execution Guide)

### 3.1. Chạy Unit Tests tự động bằng Pytest
```bash
# Chạy bộ test Ingestion Stage 1 (Magic Bytes & Markdown Conversion)
.venv\Scripts\python.exe -m pytest tests/test_ingestion_stage1.py -v

# Chạy toàn bộ các test RAG Pipeline
.venv\Scripts\python.exe -m pytest tests/test_rag/ -v
```

### 3.2. Chạy Đánh giá Chất lượng RAG (Golden Dataset Evaluation)
```bash
# Chạy script đánh giá Retrieval & Groundedness trên tập dữ liệu chuẩn
.venv\Scripts\python.exe scripts/run_eval.py --dataset eval/golden_dataset.jsonl
```
