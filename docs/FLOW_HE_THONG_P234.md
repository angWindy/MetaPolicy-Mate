# CÁC FLOW CHÍNH CỦA POLICYMETA AI

> Cập nhật: 03/09/2026 — Đăng ký bị vô hiệu hóa. User tạo bởi Admin qua UC-G-01.

## 1. Flow tổng thể

**Người dùng đặt câu hỏi**  
→ **FastAPI nhận yêu cầu:** kiểm tra dữ liệu đầu vào và identity  
→ **Governed RAG xử lý:** phân quyền, tìm kiếm và đánh giá bằng chứng  
→ **LLM sinh câu trả lời:** chỉ sử dụng nội dung đã truy xuất  
→ **Citation Validator kiểm tra nguồn**  
→ **Trả kết quả:** answer, citations, warnings và confidence

**Data owner tải tài liệu**  
→ **Ingestion Pipeline xử lý nội dung**  
→ **PostgreSQL lưu văn bản và metadata**  
→ **Qdrant lưu vector**  
→ **Tài liệu được phát hành cho RAG**

## 2. Flow nhập và phát hành một tài liệu

**Bước 1 — Upload**  
Data owner tải PDF, DOCX hoặc TXT cùng metadata.  
↓  
**Bước 2 — Validate**  
Kiểm tra kích thước, định dạng và magic bytes của file.  
↓  
**Bước 3 — Checksum**  
Tính SHA-256; từ chối nếu file đã tồn tại.  
↓  
**Bước 4 — Quarantine**  
Lưu file vào vùng cách ly trước khi xử lý.  
↓  
**Bước 5 — Parse/OCR**  
Đọc text trực tiếp hoặc OCR nếu tài liệu là bản scan.  
↓  
**Bước 6 — Nhận diện cấu trúc**  
Tách nội dung thành Chương, Mục, Điều, Khoản và Điểm.  
↓  
**Bước 7 — Chunking**  
Tạo chunks kèm metadata, vị trí và liên kết về section gốc.  
↓  
**Bước 8 — Review**  
Lưu phiên bản ở trạng thái `REVIEW_REQUIRED` để data owner kiểm tra.  
↓  
**Bước 9 — Approve**  
Phiên bản đạt yêu cầu được chuyển sang `APPROVED`.  
↓  
**Bước 10 — Index**  
Tạo embedding và upsert vào Qdrant; lỗi thì giữ `APPROVED` để retry.  
↓  
**Bước 11 — Publish**  
Sau khi index thành công, phiên bản chuyển `INDEXED` → `PUBLISHED`.

## 3. Flow bulk ingestion corpus HUST

**Đọc danh sách PDF**  
→ **Tính checksum từng file**  
→ **Bỏ qua file đã ingest thành công**  
→ **Parse/OCR từng file độc lập**  
→ **Ghi kết quả vào JSONL**  
→ **File thành công:** lưu `REVIEW_REQUIRED` cùng sections và chunks  
→ **File thất bại:** lưu `FAILED` và đưa vào OCR failure manifest  
→ **Resume:** lần chạy sau chỉ xử lý phần còn thiếu

> Ingest thành công chưa có nghĩa tài liệu đã được dùng cho RAG. Tài liệu vẫn phải qua review → approve → index → publish.

## 4. Flow hỏi đáp RAG

**Bước 1 — Nhận câu hỏi**  
FastAPI nhận message và tạo `request_id`.  
↓  
**Bước 2 — Tạo UserContext**  
Backend lấy tenant, vai trò, đơn vị và clearance từ identity đã xác thực.  
↓  
**Bước 3 — Tạo access filter**  
Lọc tài liệu theo quyền truy cập và thời điểm hiệu lực.  
↓  
**Bước 4 — Chuẩn hóa query**  
Chuẩn hóa Unicode, khoảng trắng và nhận diện số hiệu, biểu mẫu, Điều/Khoản.  
↓  
**Bước 5 — Hybrid retrieval**  
Chạy vector search song song với sparse search hoặc BM25.  
↓  
**Bước 6 — RRF fusion**  
Hợp nhất kết quả theo thứ hạng của hai phương pháp tìm kiếm.  
↓  
**Bước 7 — Làm sạch candidates**  
Loại đoạn trùng, gần trùng và giới hạn chunks trên mỗi văn bản.  
↓  
**Bước 8 — Rerank**  
Xếp hạng lại để chọn các đoạn phù hợp nhất.  
↓  
**Bước 9 — Mở rộng context**  
Lấy thêm heading cha, đoạn liền kề hoặc định nghĩa liên quan được phép xem.  
↓  
**Bước 10 — Evidence Gate**  
Quyết định `GENERATE`, `RETRY`, `ABSTAIN` hoặc `HUMAN_ESCALATION`.  
↓  
**Bước 11 — Generation**  
LLM sinh câu trả lời chỉ từ final contexts.  
↓  
**Bước 12 — Citation Validation**  
Kiểm tra chunk, document, version, vị trí, URL và quyền truy cập.  
↓  
**Bước 13 — Trả kết quả**  
API trả answer, citations, warnings, confidence và evidence status.

## 5. Flow phân quyền

**Identity đã xác thực**  
→ **Tạo UserContext:** tenant, roles, department, clearance  
→ **Tạo access filter:** quyền, đơn vị, classification, hiệu lực  
→ **Lọc khi retrieval:** loại tài liệu không được phép xem  
→ **Kiểm tra khi mở rộng context:** không thêm đoạn trái quyền  
→ **Kiểm tra khi tạo citation:** không trả nguồn hoặc excerpt trái quyền  
→ **Trả kết quả đã được kiểm soát**

Nếu metadata quyền thiếu hoặc không nhất quán:  
**Không xác minh được quyền** → **Loại tài liệu khỏi kết quả**

## 6. Flow Evidence Gate

**Nhận candidates sau rerank**  
→ **Kiểm tra có candidate hay không**  
→ **Kiểm tra top score và score gap**  
→ **Kiểm tra số nguồn độc lập**  
→ **Kiểm tra metadata citation và hiệu lực version**  
→ **Kiểm tra mâu thuẫn giữa các nguồn**

Kết quả rẽ nhánh:

- **Đủ bằng chứng** → `GENERATE` → sinh câu trả lời.
- **Bằng chứng yếu, còn lượt** → `RETRY` → viết lại query và tìm lại.
- **Không tìm thấy hoặc hết lượt** → `ABSTAIN` → từ chối kết luận.
- **Nguồn mâu thuẫn** → `HUMAN_ESCALATION` → chuyển reviewer.

## 7. Flow sinh câu trả lời và citation

**Final contexts đã được cấp quyền**  
→ **LLM sinh answer và `cited_chunk_ids`**  
→ **Tạo allowlist từ final contexts**  
→ **Kiểm tra từng chunk ID**  
→ **Đối chiếu document và version**  
→ **Đối chiếu page, section, Điều/Khoản và URL**  
→ **Kiểm tra lại quyền truy cập**  
→ **Tự xây Citation từ metadata**  
→ **Trả câu trả lời có nguồn hợp lệ**

Nếu bất kỳ bước nào không hợp lệ:  
**Citation sai** → **`UNVERIFIED`** → **confidence thấp** → **không trả citation**

## 8. Flow retry, abstain và human escalation

### Khi bằng chứng chưa đủ

**Bằng chứng yếu**  
→ **Kiểm tra số lượt đã dùng**  
→ **Còn lượt:** rewrite query → retrieval lại  
→ **Hết lượt:** trả “Tôi chưa có đủ căn cứ để kết luận.”

### Khi bằng chứng mâu thuẫn

**Phát hiện conflict**  
→ **Tạm dừng hoặc đánh dấu escalation**  
→ **Reviewer xem nguồn và lý do**  
→ **Retry:** chạy lại retrieval  
→ **Reject:** từ chối kết luận  
→ **Approve:** ghi nhận quyết định vào audit state

## 9. Flow provider retry và fallback

**Gọi provider chính**  
→ **Thành công:** trả kết quả  
→ **Timeout/rate limit/HTTP 5xx:** retry bằng exponential backoff  
→ **Hết lượt retry:** chuyển provider dự phòng  
→ **Provider dự phòng thành công:** trả kết quả  
→ **Tất cả provider lỗi:** dùng template generator hoặc hash embedding

Flow reranker tương tự:  
**CrossEncoder không tải được** → **chuyển sang lexical fallback**

> Template, hash embedding và lexical fallback là chế độ suy giảm, phù hợp cho kiểm thử hoặc demo; không tương đương chất lượng provider production.

---

## 10. Flow đăng ký & tạo tài khoản

### 10.1 Đăng ký công khai — VÔ HIỆU HÓA

**`POST /api/v1/auth/register`** luôn trả **403 Forbidden**.

User không thể tự đăng ký. Muốn có tài khoản phải liên hệ Admin.

### 10.2 Tạo tài khoản bởi Admin

**Actor:** Admin (role ADMIN, permission `user.manage`)

**FE:** `/admin/users` → nút "Tạo người dùng mới"
↓
**API:** `POST /api/v1/users` với body:
```json
{
  "email": "user@school.edu",
  "password": "SecurePass123",
  "full_name": "Nguyễn Văn A",
  "department_id": "uuid-of-department"
}
```
↓
**BE:** Tạo user, hash password, gán department
↓
**Response:** `201 Created` với user info

**UC reference:** Xem [USE_CASES.md](../USE_CASES.md) — UC-G-01 "Quản lý tài khoản người dùng"

### 10.3 Role assignment

Khi Admin tạo user, role được gán thủ công. Không có auto-assign theo email/school_code.
