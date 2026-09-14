# KẾ HOẠCH TỔNG THỂ — PolicyMeta AI (P-234)

> Cập nhật: 16h30 03/09/2026 — Phase 1: Disable register + Landing page.
> Người viết: Cursor Agent.
> Mục tiêu: User không tự đăng ký, Admin tạo tài khoản. Landing page công khai.

> **Lưu ý cập nhật 10h35 31/08:** Neon kết nối qua biến môi trường `DATABASE_URL`
> (không phải `TENANT_DATABASE_URL`). `TENANT_DATABASE_URL` chỉ xuất hiện trong
> `render.yaml`/`backend-ci.yml` cũ và là alias — code thực tế đọc `DATABASE_URL`
> qua `src/config.py::get_settings().database_url`. Khi smoke-test hay debug
> bằng psql: `psql "$DATABASE_URL"`.

---

## 1. Tổng quan trạng thái hiện tại (audit)

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| Backend FastAPI | ✅ Khởi động OK (`/health`) | Cổng 8000, env `development` |
| Database Neon (tenant + rag_legacy) | ✅ Đã kết nối | `p234_uc_demo` (apparent) |
| Redis | ✅ Đã khởi động qua Docker (image redis:7-alpine) | `localhost:6379` |
| Qdrant | ✅ Đã khởi động qua Docker (image qdrant/qdrant:latest) | `localhost:6333` |
| Trang đăng nhập FE | ✅ Có (`/login`) + `/api/v1/auth/login` | Demo accounts sẵn |
| Trang đăng ký FE | ⚠️ **Vô hiệu hóa** | `/register` → redirect `/login` với thông báo |
| Endpoint `/auth/register` BE | ⚠️ **Vô hiệu hóa** | Luôn trả 403, Admin tạo user (UC-G-01) |
| Trang chủ (Landing) | ✅ **Mới** | Public landing page tại `/`, AuthGate dashboard tại `/documents` |
| Admin tạo user | ✅ Đã có | `POST /api/v1/users` + `/admin/users` page (UC-G-01) |
| Trang quản lý tài liệu FE | ✅ Có `/documents`, `/admin/documents` | Đã có component |
| Upload PDF (BE) | ✅ `/api/v1/regulatory-documents/upload` | Form multipart |
| Xem PDF (BE) | ✅ `/api/v1/regulatory-documents/{id}/source` | `inline` content-disposition |
| Download PDF (BE) | ✅ Cùng endpoint, đổi `attachment` | FE chưa có nút "Tải về" riêng |
| Phân quyền theo trường | ✅ Đã có (`department_id` + `document_access`) | HUST/HUCE/Cross-school đã seed |
| Phân quyền user/admin | ✅ Đã có RBAC | `user.manage` permission cho Admin |
| RAG pipeline | ✅ Chạy được (trả `abstain` đúng khi không có evidence) | OpenAI key OK |
| Lưu tài liệu (Saved Documents) | ⏳ **Sắp triển khai** | Server-side saved_documents table |
| Thông báo (Notifications) | ⏳ **Sắp triển khai** | Server-side notifications table |
| 2-cấp phê duyệt (Review + Approve) | ⏳ **Sắp triển khai** | PENDING_REVIEW → PENDING_APPROVAL → APPROVED |
| Validation số hiệu văn bản | ⏳ **Sắp triển khai** | Format: `Số/Loại-Mã` hoặc `Số thuần` |

---

## 2. Mục tiêu & điều kiện hoàn thành

| # | Mục tiêu | Điều kiện đạt |
|---|---|---|
| G1 | Web ổn định | `/health` 200; `/login`, `/documents`, `/admin/documents` mở; chat RAG chạy qua token. |
| G2 | Có trang đăng nhập | `/login` nhập email + password, có quick-login demo, lưu token. |
| G3 | Landing page công khai | `/` là landing page public, `/documents` là dashboard authenticated. |
| G4 | Không cho đăng ký tự do | `/register` → 403 (Backend) + thông báo (Frontend); Admin tạo user qua `/admin/users`. |
| G5 | Lưu tài liệu | User có thể lưu/bỏ lưu tài liệu; danh sách `/saved` dùng server-side API. |
| G6 | Thông báo | User nhận thông báo khi tài liệu cần review/duyệt; bell icon hiển thị số unread. |
| G7 | 2-cấp phê duyệt | Reviewer xem xét → PENDING_APPROVAL → Admin duyệt → APPROVED → Index → Publish. |
| G8 | Validation số hiệu | Số hiệu văn bản phải đúng format; metadata không chuẩn → tự động vào PENDING_REVIEW. |
| G9 | RAG trả lời chính xác | Pipeline chạy → trả câu trả lời có trích dẫn khi có evidence, `abstain` khi không. |

---

## 3. Kế hoạch thực thi (lần lượt)

### Giai đoạn A — Hạ tầng & tài liệu
- [x] A1. Khởi động Docker Redis + Qdrant (đã làm ở phiên này).
- [x] A2. Audit endpoints BE đang hoạt động.
- [x] A3. Viết/cập nhật `PLAN.md` (file này).
- [x] A4. Cập nhật `README.md` mô tả trang đăng ký mới.

### Giai đoạn B — Đăng ký & Phân quyền
- [x] B1. Thêm `RegisterCommand` + `RegisterHandler` (BE) — tạo user + gán role/department theo email.
- [x] B2. Thêm `POST /api/v1/auth/register` (BE) — chấp nhận `email`, `password`, `full_name`, `school_code`.
- [x] B3. Quy tắc phân role:
  - Email chứa `admin@` hoặc school_code = `ADMIN` → role ADMIN, department_id NULL (cross-school).
  - Email kết thúc bằng `@hust.edu.vn` hoặc school_code = `HUST` → role LECTURER, department HUST.
  - Email kết thúc bằng `@huce.edu.vn` hoặc school_code = `HUCE` → role LECTURER, department HUCE.
  - Email chứa `student` hoặc school_code = `STUDENT` → role STUDENT.
  - Mặc định khác → role STUDENT, department_id NULL.
- [x] B4. Trang FE `/register` — form + liên kết qua `/login`.
- [x] B5. Cập nhật `/login` để có link "Chưa có tài khoản? Đăng ký".

### Giai đoạn C — Quản lý tài liệu
- [x] C1. Verify upload endpoint với PDF mẫu.
- [x] C2. Verify endpoint `/source` trả về binary PDF đúng `Content-Type`.
- [x] C3. Bổ sung nút **"Tải về"** (download) trong `DocumentDetailActions` (dùng `Content-Disposition: attachment`).
- [x] C4. Bổ sung chỉ báo "Bạn không có quyền truy cập" khi 403.

### Giai đoạn D — RAG Accuracy
- [x] D1. Test 3-5 câu hỏi mẫu; ghi log câu trả lời + citation.
- [x] D2. Nếu câu trả lời `abstain` do thiếu dữ liệu: nạp thêm tài liệu mẫu hoặc giữ `abstain` (đúng nguyên tắc).
- [x] D3. Bổ sung "nếu có file PDF thật, có thể upload qua UI để test".

### Giai đoạn E — Smoke test & ghi nhật ký
- [x] E1. `curl` toàn bộ endpoint chính.
- [x] E2. Cập nhật `WORKLOG.md`/`JOURNAL.md` theo ngày.

---

## 4. Ghi chú triển khai

### 4.1 Khởi động nhanh

```bash
# 1. Redis + Qdrant (Docker)
docker run -d --name p234-redis -p 6379:6379 redis:7-alpine
docker run -d --name p234-qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest

# 2. Backend
uvicorn src.main:app --host 0.0.0.0 --port 8000

# 3. Frontend (dev)
cd frontend && npm install && npm run dev
# → http://localhost:3000
```

### 4.2 Tài khoản demo đã seed

| Email | Mật khẩu | Role | Trường |
|---|---|---|---|
| admin@p234.demo | P234@123 | ADMIN | Cross-school |
| hust@p234.demo | P234@123 | LECTURER | HUST |
| huce@p234.demo | P234@123 | LECTURER | HUCE |
| crossschool@p234.demo | P234@123 | ADMIN | Cross-school |

### 4.3 Quy ước phân role (file: `src/application/features/auth/register/`)

Xem chi tiết tại B3. Có thể điều chỉnh nếu sau này có yêu cầu khác.

### 4.4 Những key cần user bổ sung (nếu thiếu)

| Key | Mục đích | Hành động tạm thời |
|---|---|---|
| OPENAI_API_KEY | Embedding + LLM | Đã có (dùng GPT-4o-mini) |
| DATABASE_URL | Shared backend + RAG (schema `public` + `rag_legacy`) | Đã có (Neon) |
| REDIS_URL | Rate-limit | Đã chạy local Docker |
| QDRANT_URL | Vector store | Đã chạy local Docker |
| JWT_SECRET_KEY | Ký token | Đã có |
| R2_* | Cloudflare R2 | Placeholder → fallback LocalFileStorage |

> *Không có key nào thực sự thiếu; tất cả đang dùng giá trị mặc định có sẵn trong `.env`/`.env.rag`.*

---

## 5. Nhật ký ngày (sẽ cập nhật)

- **01h30 30/08** — Audit codebase, viết PLAN.md, kh�i động Redis + Qdrant.
- **22h56 30/08** — Sửa các file spec (cũ `P234_*.md`): bỏ mô tả role theo `school_id`, chuyển sang **RBAC identity** (school_code t� form). Nén 12 file audit thành `AUDIT_SUMMARY.md`. Toàn bộ sơ đồ text chuyển sang mermaid. Cập nhật `AGENTS.md`, `README.md`, `NOTES_DATABASE_STORAGE_VECTOR_MAPPING.md`.
- **00h14 31/08** — Đổi tên 5 file `P234_*.md` sang tiếng Anh ngắn gọn: `BACKEND_ARCHITECTURE.md`, `BACKEND_BEHAVIOR.md`, `BACKEND_FLOW_A0.md`, `FE_PCCC_GUIDE.md`, `USE_CASES.md`. Cập nhật tất cả tham chiếu.
- **07h05 31/08** — Hoàn tất GĐ 5: upload endpoint nhận `auto_digitize=true` để kick off parser → chunk → embed → Qdrant ngay sau khi persist `documents`/`document_versions`. Hybrid retrieval SQL đổi từ `rag_legacy.chunks` sang `public.document_chunks` + join `document_departments`/`departments` để ACL đúng theo phòng ban hiện hành.
- **07h20 31/08** — Hoàn tất GĐ 6: chat session/turn + ACL re-check mỗi turn đã có sẵn trong `ask_question_handler.py`. Verify qua test: 2 turn liên tiếp giữ nguyên `session_id`, `turn_id` khác nhau, citations cũ được re-check ACL trước khi dùng làm context.
- **07h35 31/08** — Hoàn tất GĐ 7: viết mới `tests/test_integration/test_backend_e2e.py` (8 test, không mock, chạy qua `httpx.AsyncClient` thật). Xoá `src/api/`, `src/agents/` và các test cũ targeting legacy code. `pytest tests/test_integration/ -v` → 8/8 pass in 72s.
- **07h50 31/08** — Hoàn tất GĐ 8: `scripts/e2e_full_smoke.py` chạy 6/6 step PASS (DB clear, register, upload, approve+publish, RAG ingestion 41 chunks, RAG ask trả abstain đúng nguyên tắc). Cập nhật JOURNAL/WORKLOG/PLAN.

**Trạng thái cuối dự án (07h50 31/08):** backend chạy thật trên conda `p234` + Docker Redis + Neon + Qdrant Cloud + Cloudflare R2. Auto_digitize hoạt động end-to-end. Chat session/turn persist + ACL re-check. 8/8 integration test pass. E2E smoke 6/6 pass. 4 commit mới (`5d8c680`, `5cb3b1e`, `b9a96f3`, phase-8) đã push lên `origin/demo`. Author `angwindy <anthang2003.nd@gmail.com>`, không co-author.
## 6. Cập nhật 10h35 31/08 — Fix bug list `BUGS_FOUND.md`

### 6.1 Bug list (ghi nhận trong BUGS_FOUND.md)

| # | Bug | Severity | Status |
|---|---|---|---|
| 1 | AuthGate renders blank page on admin routes | P0 | ✅ Fixed (singleton useSyncExternalStore + loadingFallback) |
| 2 | Demo accounts (HUST/HUCE/Cross-School) do not exist | P2 | ✅ Fixed (seeded in `e2e_full_smoke.py::reset`) |
| 3 | RAG chunks never reach Qdrant in production upload path | P0 | ✅ Fixed (`/admin/.../index` dispatches `DigitizeDocumentCommand`) |
| 4 | First GET /regulatory-documents returns 500 after smoke reset | P2 | ✅ Fixed (`eng.dispose()` + `time.sleep(1.5)`) |

### 6.2 Cập nhật quan trọng: biến môi trường Neon

- **Neon kết nối qua `DATABASE_URL`** (không phải `TENANT_DATABASE_URL`).
- Khi debug hay test thủ công bằng psql: `psql "$DATABASE_URL"`.
- `TENANT_DATABASE_URL` chỉ là alias trong `render.yaml` / `backend-ci.yml` cũ, không phải biến chính.

### 6.3 Files sẽ thay đổi để fix bug

| File | Thay đổi |
|---|---|
| `src/presentation/api/routers/admin_router.py` | ✅ Wired `/index` → `DigitizeDocumentCommand`; canonical enum values |
| `scripts/e2e_full_smoke.py` | ✅ Seeds 5 demo users + `eng.dispose()` + `time.sleep(1.5)` |
| `frontend/src/hooks/useCurrentUser.ts` | ✅ Migrated sang module-level singleton với `useSyncExternalStore` |
| `frontend/src/components/layout/AuthGate.tsx` | ✅ Thêm `loadingFallback` prop |

---

## 7. Cập nhật 21h45 31/08 — Test Refactor + Bug Hunt (phiên này)

### 7.1 Trạng thái bug list sau phiên

Xem [BUGS_FOUND.md](BUGS_FOUND.md) §0 cho bảng trạng thái đầy đủ. Tóm tắt:

| ID | Bug | Severity | Status | Verified |
|---|---|---|---|---|
| B-P1-01 | N+1 query in `citations_are_accessible()` | P1 | ✅ Fixed (this PR) | 7/7 tests pass |
| B-P1-02 | Missing date validation in `UpdateRegulatoryDocumentRequest` | P1 | ✅ Fixed (this PR) | 3/3 tests pass |
| B-P1-04 | Query-token fallback `?access_token=` | P1 | ✅ Fixed (this PR) | Audit log wired |
| B-P1-05 | Hybrid search mixed enum (`Published` + `published`) | P1 | ✅ Fixed (this PR) | SQL filter tightened |
| B-P1-03 | `allowed_roles=[]` in Qdrant payload | P1 | ⚪ Won't fix (by design — unit-based ACL) | n/a |

### 7.2 Files changed in this session

| File | Change |
|---|---|
| `src/application/common/document_access_policy.py` | Refactored `citations_are_accessible` to use batched repository methods |
| `src/domain/repositories/document_repository.py` | Added `get_by_ids()` batch method to protocol |
| `src/domain/repositories/document_department_repository.py` | Added `can_access_any()` batch method to protocol |
| `src/persistence/tenant/repositories/sqlalchemy_document_repository.py` | Implemented `get_by_ids()` |
| `src/persistence/tenant/repositories/sqlalchemy_document_department_repository.py` | Implemented `can_access_any()` |
| `src/presentation/api/contracts/regulatory_documents/update_regulatory_document_request.py` | Added `@model_validator` for date order |
| `src/presentation/api/dependencies/authentication.py` | Added audit log for query-token fallback path |
| `src/infrastructure/ai/hybrid_retrieval_service.py` | Removed legacy uppercase enum values from SQL filter |
| `tests/test_application_common/test_document_access_policy_fixes.py` | New: 7 regression tests for B-P1-01 + B-P1-02 |
| `BUGS_FOUND.md` | Rewrote with status table + per-bug root cause / fix / verification |
| `WORKLOG.md` | Added evening session log |

### 7.3 Test results

- `tests/test_application_common/`: **7/7 PASS**
- `tests/` (unit, excluding integration/RAG/e2e): **140 PASS, 1 FAIL**
  - The 1 failure is pre-existing in legacy `src/db/repository.py::Repository.publish_version`
    (production admin router enforces the stricter `INDEXED → PUBLISHED` gate correctly)
- Integration + RAG tests not run (require live backend / Qdrant Cloud / OpenAI)

---

## 8. Cập nhật 16h30 03/09/2026 — Phase 1: Disable Register + Landing Page

### 8.1 Mục tiêu Phase 1
- User không thể tự đăng ký tài khoản
- Admin mới có quyền tạo tài khoản (UC-G-01)
- Trang chủ `/` là landing page công khai

### 8.2 Files đã thay đổi

| File | Thay đổi |
|---|---|
| `src/presentation/api/routers/auth_router.py` | `POST /register` → 403 Forbidden, comment rõ Admin tạo user |
| `frontend/src/app/page.tsx` | Landing page công khai với hero, features, CTA |
| `frontend/src/app/login/page.tsx` | Xóa link "Đăng ký ngay" |
| `frontend/src/app/register/page.tsx` | Trang thông báo "Đăng ký bị vô hiệu hóa" + redirect sau 5s |
| `PLAN.md` | Cập nhật trạng thái, thêm Phase 1-3 |

### 8.3 Testing Phase 1

- [ ] API: `POST /api/v1/auth/register` → 403 Forbidden
- [ ] FE: Navigate `/register` → hiển thị thông báo + redirect sau 5s
- [ ] FE: Login page không có link "Đăng ký"
- [ ] `/` accessible without auth, hiển thị landing page
- [ ] `/documents` vẫn yêu cầu auth

---

## 9. Phase 2a: Saved Documents (Server-side) — Sắp triển khai

### 9.1 Mục tiêu
- User có thể lưu/bỏ lưu tài liệu
- Danh sách tài liệu đã lưu ở `/saved` dùng server-side API

### 9.2 Files cần tạo

| Layer | File |
|---|---|
| DB | `database/migrations/002_create_saved_documents.sql` |
| Domain | `src/domain/entities/saved_document.py` |
| Repo | `src/db/repositories/saved_document_repository.py` |
| Handler | `src/application/features/saved_documents/save_handler.py` |
| Handler | `src/application/features/saved_documents/unsave_handler.py` |
| Handler | `src/application/features/saved_documents/list_handler.py` |
| Router | `src/presentation/api/routers/saved_documents_router.py` |
| FE | `frontend/src/services/savedDocumentService.ts` |
| FE | `frontend/src/app/saved/page.tsx` |
| FE | `frontend/src/components/documents/DocumentDetailActions.tsx` (cập nhật) |

### 9.3 API endpoints

```
POST   /api/v1/saved-documents/{document_id}   # Lưu
DELETE /api/v1/saved-documents/{document_id}   # Bỏ lưu
GET    /api/v1/saved-documents?page=1&limit=20 # DS đã lưu
```

### 9.4 Testing Phase 2a

- [ ] API: `POST /saved-documents/{id}` → 201
- [ ] API: `POST /saved-documents/{id}` (duplicate) → 409
- [ ] API: `DELETE /saved-documents/{id}` → 204
- [ ] API: `GET /saved-documents` → 200 with pagination
- [ ] API: User chỉ thấy saved documents của mình
- [ ] FE: `/saved` page hiển thị đúng

---

## 10. Phase 2b: Notifications — Sắp triển khai

### 10.1 Mục tiêu
- User nhận thông báo khi tài liệu cần review/duyệt
- Bell icon hiển thị số unread

### 10.2 Files cần tạo

| Layer | File |
|---|---|
| DB | `database/migrations/003_create_notifications.sql` |
| Domain | `src/domain/entities/notification.py` |
| Domain | `src/domain/schemas.py` (thêm NotificationType enum) |
| Repo | `src/db/repositories/notification_repository.py` |
| Handler | `src/application/features/notifications/list_handler.py` |
| Handler | `src/application/features/notifications/mark_read_handler.py` |
| Handler | `src/application/features/notifications/count_handler.py` |
| Handler | `src/application/features/notifications/notify_service.py` |
| Router | `src/presentation/api/routers/notification_router.py` |
| FE | `frontend/src/services/notificationService.ts` |
| FE | `frontend/src/hooks/useNotifications.ts` |
| FE | `frontend/src/app/notifications/page.tsx` (cập nhật) |
| FE | `frontend/src/components/layout/StudentHeader.tsx` (cập nhật) |

### 10.3 API endpoints

```
GET    /api/v1/notifications?unread_only=true&page=1
POST   /api/v1/notifications/{id}/read
POST   /api/v1/notifications/read-all
GET    /api/v1/notifications/unread-count
```

### 10.4 Testing Phase 2b

- [ ] API: CRUD operations với RBAC
- [ ] Bell badge hiển thị số unread
- [ ] Mark read / mark all read

---

## 11. Phase 3: 2-Cấp Approval + Validation — Sắp triển khai

### 11.1 Mục tiêu
- Reviewer xem xét tài liệu → PENDING_APPROVAL
- Admin duyệt cuối → APPROVED → Index → Publish
- Validation số hiệu văn bản
- Tài liệu metadata không chuẩn → tự động PENDING_REVIEW

### 11.2 Status mới trong ProcessingStatus

```python
class ProcessingStatus(StrEnum):
    # ... existing ...
    PENDING_REVIEW = "pending_review"       # NEW: Chờ reviewer xem xét
    PENDING_APPROVAL = "pending_approval"  # NEW: Chờ admin duyệt
    REJECTED = "rejected"                   # NEW: Bị từ chối
```

### 11.3 State machine

```
PARSED ──metadata invalid──> PENDING_REVIEW ──reviewer OK──> PENDING_APPROVAL
                                    │                              │
                                    └──reject──> REJECTED  ├──admin approve──> APPROVED
                                                                       └──admin reject──> REJECTED
```

### 11.4 Files cần tạo/sửa

| Layer | File | Change |
|---|---|---|
| Domain | `src/domain/schemas.py` | Thêm PENDING_REVIEW, PENDING_APPROVAL, REJECTED |
| Domain | `src/domain/validators/document_validator.py` | Mới: validation số hiệu |
| DB | `database/migrations/004_add_review_columns.sql` | review_notes, reviewed_by, reviewed_at |
| Handler | `src/application/features/documents/review/complete_review_handler.py` | Mới |
| Handler | `src/application/features/documents/review/reject_handler.py` | Mới |
| Handler | `src/application/features/documents/review/republish_handler.py` | Mới |
| Router | `src/presentation/api/routers/admin_router.py` | Thêm endpoints |
| FE | `frontend/src/app/admin/review/page.tsx` | Mới: tabs theo status |
| FE | `frontend/src/components/documents/StatusBadge.tsx` | Thêm badges mới |

### 11.5 Testing Phase 3

- [ ] 2-cấp state transitions
- [ ] Permission matrix (reviewer vs admin)
- [ ] Notification triggers
- [ ] Số hiệu validation

---

## 12. Phase 4 — OCR engine swap (RapidOCR + PP-OCRv6 Vietnamese ONNX)

> Plan gốc: `.cursor/plans/ocr_migration_plan_(with_deep_vietnamese_audit)_dec89d70.plan.md`
> (đã supersede; §3 rewrite thành historical record 2026-09-06).
> Live plan: `ocr_migration_hardening_&_vietnamese_diacritic_fix_c464cd07.plan.md` (đã approve và hoàn thành 2026-09-06).

### 12.1 Quyết định

| Hướng | Lựa chọn |
|---|---|
| Engine | RapidOCR ONNX runtime (single-engine architecture) |
| Recognition model | PP-OCRv6_medium_rec (`data/ocr/outputs/onnx_models/rec_vi/inference.onnx`, 73 MB gitignored) |
| Dictionary | `dict.txt` 18 795 chars (146 Vietnamese chars đầy đủ + multilingual) |
| Detection + classification | Bundled defaults từ `rapidocr_onnxruntime` (ch_PP-OCRv4_det + ch_ppocr_mobile_v2.0_cls) |
| Hybrid gate | Text-extract ≥ 50 chars/page → bỏ qua OCR; ngược lại render + RapidOCR |
| Pipeline DPI | 200 body, 600 cover, clamp scan ≤ 200 để giữ OCR sweet-spot |
| Diacritic restoration | Wordlist-based fallback (`src/ingestion/pdf_processor/vn_diacritic_restore.py`) |

### 12.2 Files

| Layer | File | Change |
|---|---|---|
| Domain | `src/domain/schemas.py` | `ParsedBlock` accepts `text + **_unused` |
| Engine | `src/ingestion/pdf_processor/ocr_engine.py` | Single-engine RapidOCR + PP-OCRv6 |
| Pipeline | `src/ingestion/pdf_processor/pipeline.py` | Hybrid gate + DPI clamp |
| RAG config | `src/rag/config.py` | `ocr_engine: Literal["rapidocr_vi", "pp_structure"]` + `ocr_models_dir` |
| Command | `src/application/features/document_digitization/digitize/digitize_document_command.py` | `ocr_engine: Literal["rapidocr_vi", "pp_structure"]` field |
| Handler | `src/application/features/document_digitization/digitize/digitize_document_handler.py` | Pass `ocr_engine` to service |
| Service | `src/infrastructure/ai/document_digitization_service.py` | Derive `use_pp_structure` from `ocr_engine` param |
| Env | `.env.example` + `.env` | `OCR_ENGINE=rapidocr_vi`, `OCR_MODELS_DIR=ocr_models` |
| Docs | `docs/PDF_PROCESSING.md`, `docs/OCR_BACKENDS.md` | Updated |

### 12.3 Bench + acceptance

| Metric | Result |
|---|---|
| Bench full 22-PDF corpus | 22 PDFs, 6 scan pages, 0 diacritic gate failures |
| `data/ocr/outputs/bench_full_corpus/summary.json` gate | **PASS** |
| Diacritic ratio trên 13 525 chunks (Neon) | avg 0.1471 (target ≥ 0.05) |
| `docs/eval/results/rag_quality_live_110_current_20260904.jsonl` (110 Q&A baseline) | doc_hit 96.36%, case_pass 77.27%, evidence_hit 80.00% |
| Env-broken regression script | Documented at `data/ocr/outputs/eval_post_ocr_20260906/README.md` |

### 12.4 Rollback

```
git revert <rapidocr-merge-sha>
```

Không có DB migration; chunks đã ingest bằng RapidOCR vẫn valid (cùng
schema). Vietnamese quality gate đảm bảo chunks giữ nguyên diacritics.
