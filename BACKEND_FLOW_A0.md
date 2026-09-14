# P-234 Backend — Luồng A0-01 → A0-06 cho FE

> Hướng dẫn dành cho Frontend. Mô tả hành vi Backend hiện tại (đã PASS API test).

## 1. Tổng quan 6 UC

```mermaid
flowchart LR
    A001[A0-01<br/>Metadata] --> A002[A0-02<br/>Version + R2]
    A002 --> A003[A0-03<br/>Relations]
    A003 --> A004[A0-04<br/>Effectiveness alerts]
    A004 --> A005[A0-05<br/>Application scope]
    A005 --> A006[A0-06<br/>Changelog]
```

Audit pipeline (cho A0-06):

```mermaid
flowchart LR
    API[API/Command] --> H[Handler]
    H --> AD[AuditHandlerDecorator]
    AD --> S[AuditService]
    S --> OB[audit_outbox]
    OB --> W[AuditOutboxWorker]
    W --> LOG[audit_logs]
    LOG --> A006
```

FE không truy cập trực tiếp DB/R2; chỉ làm việc qua API và giữ đúng ID BE trả về.

---

## 2. A0-01 — Quản lý thông tin văn bản

Quản lý metadata: `document_number`, `title`, `issued_by`, `issued_date`, `effective_date`, `legal_status`.

```text
Document != file PDF
```

Document là đối tượng nghiệp vụ; file nguồn/version ở A0-02.

```mermaid
flowchart LR
    FE[FE gửi metadata] --> V[BE validate]
    V --> CHK{document_number trùng?}
    CHK -->|Có| ERR[Trả lỗi]
    CHK -->|Không| CREATE[Tạo Document]
    CREATE --> RET[Trả document_id]
```

- `document_id` là ID chính dùng xuyên suốt các UC sau.
- DB có unique index theo `lower(document_number)` (case-insensitive). FE nên hiển thị conflict từ BE thay vì tự validate client.
- Update metadata không upload/thay PDF.

---

## 3. A0-02 — Nạp / thay thế file nguồn

```mermaid
flowchart LR
    FE[FE chọn PDF] --> UP[BE đọc UploadFile]
    UP --> R2[Lưu R2]
    R2 --> VER[Tạo DocumentVersion mới]
    VER --> LINK[Liên kết version trư�c]
    LINK --> RET[Trả version]
```

```text
Document D1
├── Version V1
└── Version V2
```

Replace giữ nguyên `document_id`, tăng `version_number`.

Endpoint: `PUT /api/v1/regulatory-documents/{document_id}/source` — `multipart/form-data` field `file`.

Scope A0-05 không tự chuyển sang version mới; scope cũ vẫn gắn `source_version_id = V1`.

---

## 4. A0-03 — Quan hệ giữa các văn bản

```json
{
  "target_document_id": "...",
  "relation_type": "supersedes|amends|references",
  "note": "...",
  "confirm_conflict": false
}
```

- `supersedes` — thay thế.
- `amends` — sửa đổi/bổ sung, không thay thế.
- `confirm_conflict` chỉ gửi `true` khi BE phát hiện conflict.

```mermaid
flowchart TD
    SUB[Submit relation] --> CHECK{Conflict?}
    CHECK -->|Không| OK[Success]
    CHECK -->|Có| CONF[FE hiển thị xác nhận]
    CONF -->|User đồng ý| RESUB[Gửi lại confirm_conflict=true]
    RESUB --> OK
```

---

## 5. A0-04 — Hiệu lực và cảnh báo

```mermaid
flowchart LR
    K[Khai báo] --> BE[BE lưu alert]
    BE --> P[Xử lý dữ liệu hiệu lực]
    P --> GET[FE GET list/detail]
    GET --> UI[Hiển thị cảnh báo]
```

`effective_date_reached` là giá trị BE tính trong response, **không phải column trong DB**.

FE không tự suy luận `effective_date_reached = true → đổi document.status`. Việc chuyển trạng thái theo API/UC riêng.

---

## 6. A0-05 — Phạm vi áp dụng

```text
source_document_id
source_version_id
related_document_id
scope_type           # whole_document | specific_content
scope_detail         # null nếu whole_document, "Điều 5, Khoản 2" nếu specific_content
reference_nature     # mandatory | reference
```

Binding theo version — BE giữ lịch sử:

```mermaid
flowchart TD
    D1[Document D1] --> V1[V1]
    V1 --> S1[Scope S1]
    V1 --> S2[Scope S2]
    D1 --> V2[V2 - mới]
    V2 --> S3[Scope S3]
```

---

## 7. A0-06 — Lịch sử thay đổi

Reuse audit infrastructure:

```mermaid
flowchart LR
    CMD[Command thành công] --> DEC[AuditHandlerDecorator]
    DEC --> SVC[AuditService]
    SVC --> OB[audit_outbox]
    OB --> W[AuditOutboxWorker]
    W --> LOG[audit_logs]
    LOG --> API[Changelog API]
```

```http
GET /api/v1/regulatory-documents/{document_id}/changelog?action=...&from_at=...&to_at=...&page=1&page_size=20
GET /api/v1/regulatory-documents/{document_id}/changelog/{changelog_id}
```

Filter thời gian:

```text
created_at >= from_at AND created_at <= to_at
```

Pagination: `page >= 1`, `1 <= page_size <= 100`, `total` tổng record thỏa filter.

Changelog **read-only**. FE không POST/PUT/PATCH/DELETE.

---

## 8. Quan hệ giữa 6 UC

```mermaid
flowchart TD
    RD[RegulatoryDocument] --> MD[Metadata - A0-01]
    RD --> V[Versions / PDF / R2 - A0-02]
    RD --> REL[Document Relations - A0-03]
    RD --> AL[Effectiveness Alerts - A0-04]
    RD --> AS[Application Scopes - A0-05]
    RD --> CH[Changelog / Audit - A0-06]
```

---

## 9. Gợi ý mapping màn hình FE

| Tab | UC |
|---|---|
| Thông tin | A0-01 |
| File & phiên bản | A0-02 |
| Quan hệ văn bản | A0-03 |
| Hiệu lực & cảnh báo | A0-04 |
| Phạm vi áp dụng | A0-05 |
| Lịch sử thay đổi | A0-06 |

BE không bắt buộc layout này — chỉ là gợi ý.

---

## 10. ID FE phải phân biệt

| ID | Ý nghĩa |
|---|---|
| `document_id` | ID văn bản nghiệp vụ |
| `version_id` / `source_version_id` | ID phiên bản file nguồn |
| `target_document_id` | Document đích của A0-03 |
| `related_document_id` | Document viện dẫn � A0-05 |
| `scope_id` | ID phạm vi áp dụng |
| `changelog_id` | ID audit/changelog |
| `actor_id` | Người thực hiện |

Không dùng `version_id` thay `document_id`.

---

## 11. Business rule FE không tự làm

FE không tự:

- Quyết uniqueness `document_number`.
- Quyết supersession/relation conflict.
- Luôn gửi `confirm_conflict=true`.
- Tăng `version_number`.
- Chuyển scope cũ sang version mới.
- Đổi document.status khi tới `effective_date`.
- Tạo/sửa/xóa changelog.

Luồng đúng:

```mermaid
flowchart LR
    V[FE validate UI/format] --> API[Gọi API]
    API --> R[BE áp business rule]
    R --> OUT[FE hiển thị result/conflict/error]
```

---

## 12. Luồng tích hợp FE minh họa

```mermaid
flowchart TD
    L[Login] --> A01[A0-01: tạo Document]
    A01 --> DOC[document_id]
    DOC --> A02[A0-02: upload PDF]
    A02 --> V1[Version V1]
    V1 --> A03[A0-03: khai báo relation]
    A03 --> CF{Conflict?}
    CF -->|Có| ASK[Hỏi user]
    ASK --> A03
    CF -->|Không| A04[A0-04: theo dõi hiệu lực]
    A04 --> A05[A0-05: khai báo application scope]
    A05 --> RP{Sau này có PDF mới?}
    RP -->|Có| A02B[A0-02: replace → Version V2]
    A02B --> SCOPE[Scope cũ vẫn thuộc V1]
    RP -->|Không| A06
    A05 --> A06[A0-06: xem changelog]
```

---

## 13. Trạng thái Backend hiện tại

```text
A0-01 PASS
A0-02 PASS
A0-03 PASS
A0-04 PASS
A0-05 PASS
A0-06 PASS
```

Cả 6 UC đã được test trực tiếp qua API. Audit pipeline A0-06 hoạt động đầy đủ (Decorator → Service → outbox → Worker → logs → API).

FE có thể tích hợp dựa trên API/contract hiện tại mà không cần truy cập trực tiếp DB hoặc R2.
