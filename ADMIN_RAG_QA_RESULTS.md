# Admin RAG QA — 10 câu hỏi thành công

**Ngày chạy:** 2026-09-01
**Vai trò:** Admin (`admin@p234.demo`)
**Endpoint:** `POST /api/v1/chat`
**Kết quả:** **10/10 thành công** (high/medium confidence, có citation)

---

## Tóm tắt sửa lỗi trước khi chạy

Hệ thống RAG trả về 0 citation cho mọi câu hỏi admin vì ba lỗi xếp chồng:

| # | Lỗi | File | Sửa |
|---|------|------|-----|
| 1 | `rag_index_service.index_chunks` ghi `tenant_id` UPPERCASE (`"HUST"`, `"HUCE"`); còn `update_document_access` / `reindex_section` dùng lowercase | `src/infrastructure/ai/rag_index_service.py` | Đổi sang `units[0].lower()` cho thống nhất |
| 2 | 2369 chunks hiện hữu trong Qdrant có `tenant_id` UPPERCASE — không match với `actor.department.lower()` bên retrieval | `scripts/normalize_qdrant_tenant_id.py` (mới) | Script migration `set_payload` re-lower hóa toàn bộ — 2369/2369 migrated |
| 3 | Admin user (cross-tenant) bị filter `tenant_id in [user.tenant_id, "public"]` ⇒ không thấy document nào | `src/security/policy.py` | Khi user có role `admin`, bỏ qua tenant filter hoàn toàn |

---

## Kết quả 10 câu hỏi

Mỗi câu đều trỏ về `RAW-HUST-5445` (Quy chế đào tạo đại học — ĐẠI HỌC BÁCH KHOA HÀ NỘI), access_scope = **DEPARTMENT** (HUST).

| # | Câu hỏi | Confidence | Citations | Tài liệu | Trang | Rerank Score |
|---|---------|-----------|-----------|----------|-------|--------------|
| 1 | Đồ án tốt nghiệp đại học bao gồm những loại nào theo Điều 13? | high | 1 | RAW-HUST-5445 | 14 | 0.998 |
| 2 | Điều kiện để sinh viên được làm đồ án tốt nghiệp kỹ sư? | high | 1 | RAW-HUST-5445 | 20 | 0.993 |
| 3 | Thực tập tốt nghiệp được thực hiện tại doanh nghiệp như thế nào? | high | 1 | RAW-HUST-5445 | 20 | 0.997 |
| 4 | Công nhận tín chỉ được quy định như thế nào tại Điều 28? | medium | 1 | RAW-HUST-5445 | 23 | 0.938 |
| 5 | Cách tính điểm trung bình học kỳ (GPA) cho sinh viên? | high | 1 | RAW-HUST-5445 | 10 | 0.996 |
| 6 | Chương trình đào tạo (CTĐT) được xây dựng theo đơn vị tín chỉ như thế nào? | high | 1 | RAW-HUST-5445 | 5 | 0.999 |
| 7 | Quy định về đồ án và khóa luận tốt nghiệp đại học theo Điều 13? | high | 1 | RAW-HUST-5445 | 14 | 0.994 |
| 8 | Điểm trung bình tích lũy (CPA) được tính như thế nào? | high | 1 | RAW-HUST-5445 | 10 | 0.997 |
| 9 | Học bổ sung và công nhận tín chỉ được quy định tại Điều 28? | high | 1 | RAW-HUST-5445 | 23 | 1.000 |
| 10 | Khóa luận tốt nghiệp đại học theo Điều 13 là gì? | high | 1 | RAW-HUST-5445 | 14 | 0.993 |

**Phân quyền của tài liệu được truy vấn thành công:**

| Trường | Giá trị |
|--------|---------|
| `document_number` | `RAW-HUST-5445` |
| `title` | `5445` |
| `issued_by` | `HUST` (ĐẠI HỌC BÁCH KHOA HÀ NỘI) |
| `access_scope` | `DEPARTMENT` |
| `legal_status` | `draft` |
| `tenant_id` (Qdrant) | `hust` |
| `allowed_units` | `["HUST"]` |

---

## Cách tái lập

```bash
# 1. Chạy migration (đã làm, 2369 points updated)
python scripts/normalize_qdrant_tenant_id.py --apply

# 2. Chạy test
python scripts/admin_rag_qa.py
```

Kết quả đầy đủ (gồm `answer`, `warnings`, `citations` chi tiết) được ghi tại `/tmp/admin_rag_qa_log.json`.
