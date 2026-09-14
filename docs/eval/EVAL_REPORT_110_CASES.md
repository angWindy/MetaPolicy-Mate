# BÁO CÁO ĐÁNH GIÁ CHẤT LƯỢNG HỆ THỐNG RAG (BỘ ĐO 110 CÂU HỎI)

> **Dự án:** P-234 PolicyMeta AI  
> **Ngày đánh giá:** 04/09/2026  
> **Môi trường:** FastAPI trực tiếp + PostgreSQL + Qdrant cục bộ + mô hình LLM sản xuất
> **Bộ dữ liệu kiểm thử:** 110 câu (`golden_v7_domain_100.jsonl` + `golden_v8_negative_10.jsonl`)  
> **Chương trình thực thi:** `tests/sweep/run_sweep.py`

---

## 1. TỔNG QUAN VÀ MỤC TIÊU ĐÁNH GIÁ

Đợt kiểm thử 110 câu hỏi được thực hiện nhằm đo lường toàn diện năng lực của hệ thống RAG sau các cải tiến lớn về:
1. **Chia đoạn bảng nâng cao và kế thừa ngữ cảnh:** Không ngắt dòng bảng, lặp lại tiêu đề cột, tự động lan truyền ngữ cảnh tiêu đề và đơn vị tính (`src/retrieval/heading_context.py`).
2. **Lexical reranking & mật độ khái niệm:** Tối ưu hóa so khớp từ vựng cục bộ cho các điều khoản và bảng điểm (`src/retrieval/lexical_reranker.py`, `src/retrieval/relevance.py`).
3. **Bộ nhớ hội thoại có giới hạn:** Phân định rõ ngữ cảnh hội thoại và truy vấn truy xuất ([ask_question_handler.py](file:///d:/P-234-demo/src/application/features/chat/ask/ask_question_handler.py)), giải quyết dứt điểm trôi dạt ngữ nghĩa C-021.
4. **Phân quyền quản trị đa trường:** Mở rộng bộ nạp ứng viên để tài khoản quản trị truy cập tài liệu xuyên suốt mọi trường thành viên ([hybrid_retrieval_service.py](file:///d:/P-234-demo/src/infrastructure/ai/hybrid_retrieval_service.py)).
5. **Kiểm chứng câu trả lời theo bằng chứng:** Rà soát số liệu và danh xưng để chống ảo giác (`src/rag/answer_grounding.py`).
6. **Kiểm tra khả năng từ chối an toàn:** Bổ sung 10 câu hỏi ngoài phạm vi tài liệu để thẩm định năng lực từ chối thông minh.

---

## 2. BẢNG TỔNG HỢP CHỈ SỐ TOÀN DIỆN (110 CÂU)

| Nhóm kiểm thử | Số lượng | doc_hit (Đúng tài liệu) | evidence_hit (Đúng trích dẫn) | answer_correct (Đúng nội dung) | case_pass (Đạt cả 3) | low_confidence / abstain (Độ tin cậy thấp / từ chối) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Trong phạm vi (100 câu)** | 100 | **100 / 100 (100.0%)** | **81 / 100 (81.0%)** | **89 / 100 (89.0%)** | **79 / 100 (79.0%)** | 0 / 100 (0.0%) |
| **Ngoài phạm vi (10 câu)** | 10 | **8 / 10 (80.0%)** | **10 / 10 (100.0%)** | **8 / 10 (80.0%)** | **8 / 10 (80.0%)** | **8 / 10 (80.0%)** |
| **TỔNG CỘNG (110 câu)** | **110** | **108 / 110 (98.2%)** | **91 / 110 (82.7%)** | **97 / 110 (88.2%)** | **87 / 110 (79.1%)** | **8 / 110 (7.3%)** |

> **Ghi chú về độ chính xác thực tế:**  
> Trong 100 câu thuộc phạm vi, có 2 câu (`D73`, `D74`) bị gán trượt do dữ liệu sự thật chuẩn mâu thuẫn với văn bản quy chế gốc đã được đăng ký trong [CROSS_LAYER_CONFLICT_REGISTER.md](file:///d:/P-234-demo/CROSS_LAYER_CONFLICT_REGISTER.md) (C-023 và C-024). Mô hình trả lời đúng theo văn bản luật thực tế (năm 2022 và học kỳ 2 năm 2024-2025).
> **Nếu tính đúng theo văn bản pháp lý thực tế:** Tỷ lệ `answer_correct` đạt **99 / 110 (90.0%)**.

---

## 3. PHÂN TÍCH CHI TIẾT THEO TỪNG NHÓM CHỦ ĐỀ

### A. Nhóm Tài liệu HUCE (D67 – D70)
- **Tài liệu:** `RAW-HUCE-quyet-dinh-ban-hanh-ugas`
- **Kết quả:** **4 / 4 (100% `case_pass`)**
- **Nhận xét:** Trước khi vá lỗi, tài khoản quản trị bị hạn chế truy cập do truy vấn lọc cứng theo mã phòng ban HUST. Sau khi cấu hình quyền quản trị đa trường trong `hybrid_retrieval_service.py` và `policy.py`, 100% câu hỏi HUCE đã tìm đúng tài liệu và trả lời chính xác thông tin Hiệu trưởng, Phòng Quản lý đào tạo và Thông tư 17/2021.

### B. Nhóm Quy chế đào tạo chính quy & Chuyển trường (QĐ 5445)
- **Tài liệu:** `5445/QĐ-ĐHBK`
- **Kết quả:** Tìm đúng văn bản **100%**, tỷ lệ trả lời đúng đạt **~88%**.
- **Điểm sáng:** Câu `D85` (trọng số điểm cuối kỳ) trước đây bị trượt do bộ định vị chỉ nhận chuỗi `"50%"`; sau khi chuẩn hóa nhận diện số thập phân `"0,5"`, ca này đã đạt 100%.

### C. Nhóm Học phí & Bảng số liệu phức tạp (QĐ 10232, QĐ 956)
- **Tài liệu:** `10232/QĐ-ĐHBK`, `956/TABLE-ĐHBK`
- **Kết quả:** Nhờ cải tiến lặp tiêu đề cột và lan truyền ngữ cảnh tiền tệ, các câu hỏi khó về học phí tiến sĩ, thạc sĩ (`D18`, `D92`) đã đạt hoàn toàn.
- **Tồn tại:** Một số dòng con trong bảng có nhiều cột số liệu tương tự nhau (`D30`, `D53`, `D94`) đôi khi mô hình chọn nhầm mức học phí của chương trình liên kết kế cận.

### D. Nhóm Chuẩn ngoại ngữ & Quy đổi điểm (QĐ 10728, QĐ 2048)
- **Tài liệu:** `10728/QĐ-ĐHBK`, `2048/TABLE-ĐHBK`
- **Kết quả:** Đạt tỷ lệ trả lời đúng **> 90%**. Các câu hỏi quy đổi Aptis, TOEFL, IELTS (`D96`, `D98`) mô hình trả lời chính xác thang điểm theo Bảng 2.1.

### E. Nhóm kiểm tra phòng vệ chống ảo giác (ngoài phạm vi: N01 – N10)
- **Mục đích:** Kiểm tra xem hệ thống có biết từ chối trả lời khi gặp câu hỏi không có thông tin trong tài liệu hay không.
- **Kết quả:** **8 / 10 câu (80.0%)** từ chối chính xác và an toàn:
  - `N01` (Nồng độ cồn xe máy theo QĐ 5445): Hệ thống trả về 0 trích dẫn, phản hồi: *"Tôi không có đủ cơ sở để kết luận..."* (Đạt).
  - `N03` (Vay vốn nhà ở xã hội theo QĐ 7737): Phản hồi không đủ cơ sở (Đạt).
  - `N04` (Điểm chuẩn năm 1975): Phản hồi không đủ cơ sở (Đạt).
  - `N05` (Cấp đổi hộ chiếu tại HUCE): Phản hồi không đủ cơ sở (Đạt).
  - `N07` (Chi phí khám chữa bệnh BV Bạch Mai theo QĐ 10232): Phản hồi không đủ cơ sở (Đạt).
  - `N08` (Chứng chỉ TOPIK tiếng Hàn ĐH Ngoại ngữ theo QĐ 10728): Phản hồi không đủ cơ sở (Đạt).
  - `N09` (Bảng lương chuyên viên cao cấp theo QĐ 2048): Phản hồi không đủ cơ sở (Đạt).
  - `N10` (Giải bóng đá sinh viên theo QĐ 5445): Bước kiểm chứng câu trả lời bắt lỗi số liệu năm 2025 không có căn cứ, kích hoạt câu từ chối an toàn (Đạt).
- **2 ca bị trượt do lệch ngữ nghĩa:**
  - `N02` (Học phí ĐH Ngoại thương): Do có từ khóa *"học phí theo tín chỉ"*, bộ truy xuất vector kéo nhầm bảng học phí 5.000.000đ của ĐHBK và mô hình trả lời mức 5 triệu.
  - `N06` (Bảo lưu thi THPT trong QĐ 5445): Do có từ khóa *"bảo lưu kết quả"*, bộ truy xuất vector kéo Điều 35 (bảo lưu kết quả học tập khi nghỉ học tạm thời) và trả lời về nghỉ học tạm thời.

---

## 4. BẢNG CHI TIẾT 23 TRƯỜNG HỢP CHƯA ĐẠT CASE_PASS

Trong tổng số 110 câu, có 23 câu chưa đạt tiêu chí `case_pass` hoàn hảo (21 câu thuộc phạm vi và 2 câu ngoài phạm vi). Phân loại nguyên nhân cụ thể như sau:

| STT | Mã Câu | Loại Lỗi | Phân Tích Nguyên Nhân & Giải Pháp |
|:---:|:---:|:---:|---|
| 1 | `D24` | Thiếu trích đoạn | Câu trả lời đúng 100%, nhưng lát cắt trích đoạn ngắn bị lệch và không bao hàm đủ cụm từ định vị. |
| 2 | `D25` | Sai câu trả lời | Câu hỏi điều kiện tích lũy tín chỉ bị sót một ý phụ trong câu trả lời. |
| 3 | `D26` | Sai câu trả lời | Sót mốc thời hạn 3 tháng trong câu trả lời điều kiện. |
| 4 | `D30` | Sai câu trả lời | Nhầm lẫn giữa cột học phí hệ chuẩn và hệ chất lượng cao trong bảng đa cột. |
| 5 | `D32` | Sai câu trả lời | Trả lời đúng số tiền nhưng thiếu cụm từ viết tắt đơn vị "TCHP". |
| 6 | `D48` | Thiếu trích đoạn | Câu trả lời đúng 100%, trượt bằng chứng do trích đoạn thiếu từ khóa phụ. |
| 7 | `D50` | Thiếu trích đoạn | Câu trả lời đúng 100%, trượt bằng chứng do trích đoạn thiếu từ khóa phụ. |
| 8 | `D53` | Sai câu trả lời | Nhầm mức học phí của chuyên ngành liền kề trong bảng học phí sau đại học. |
| 9 | `D59` | Sai câu trả lời | Nhầm lẫn câu hỏi điều kiện ngoại ngữ tiếng Pháp. |
| 10 | `D60` | Thiếu trích đoạn | Câu trả lời đúng 100% (Tiếng Anh), trượt bằng chứng do trích đoạn thiếu từ khóa phụ. |
| 11 | `D62` | Sai câu trả lời | Trả lời đạt trình độ đại học nhưng chưa nói rõ cụm từ "bậc 6". |
| 12 | `D73` | Xung đột đặc tả | **Xung đột C-023:** Văn bản gốc ghi năm 2022, mô hình trả lời đúng 2022, bộ chuẩn đòi 2021/K66. |
| 13 | `D74` | Xung đột đặc tả | **Xung đột C-024:** Văn bản gốc ghi kỳ 2 2024-2025, mô hình trả lời đúng, bộ chuẩn đòi kỳ 1 2025-2026. |
| 14 | `D78` | Thiếu trích đoạn | Câu trả lời đúng 100% (ĐTBHK), trượt bằng chứng do trích đoạn không chứa đủ cặp từ so sánh. |
| 15 | `D81` | Sai câu trả lời | Trả lời quy định nghỉ học chung nhưng thiếu từ khóa "nghĩa vụ quân sự". |
| 16 | `D82` | Thiếu trích đoạn | Câu trả lời đúng 100% (45 tín chỉ), trượt bằng chứng do trích đoạn thiếu từ khóa định vị. |
| 17 | `D83` | Thiếu trích đoạn | Mô hình phát hiện thiếu căn cứ chi tiết nên từ chối đúng quy tắc an toàn. |
| 18 | `D84` | Thiếu trích đoạn | Câu trả lời đúng 100% (Điểm quá trình và cuối kỳ), trượt bằng chứng do trích đoạn thiếu từ khóa. |
| 19 | `D94` | Sai câu trả lời | Nhầm dòng học phí ngành Kỹ thuật y sinh trong bảng QĐ 10232. |
| 20 | `D96` | Thiếu trích đoạn | Câu trả lời đúng 100% (550 đến 620), trượt bằng chứng do trích đoạn thiếu từ khóa Bậc 3. |
| 21 | `D98` | Thiếu trích đoạn | Câu trả lời đúng 100% (550 điểm), trượt bằng chứng do trích đoạn thiếu từ khóa định vị. |
| 22 | `N02` | Ảo giác | Trả lời học phí 5 triệu của ĐHBK cho câu hỏi về ĐH Ngoại thương do khớp ngữ nghĩa. |
| 23 | `N06` | Ảo giác | Trả lời quy chế nghỉ học tạm thời cho câu hỏi về thi tốt nghiệp THPT. |

---

## 5. KẾT LUẬN VÀ KIẾN NGHỊ

1. **Hiệu năng vượt trội:**
   - Khả năng định vị đúng tài liệu đạt **98.2%** (100% với tài liệu nội bộ).
   - Độ chính xác nội dung câu trả lời đạt **88.2% - 90.0%**.
   - Khả năng phòng vệ từ chối câu hỏi ngoài phạm vi đạt **80.0%**.
2. **Kế hoạch tiếp theo:**
   - **Xử lý trượt trích đoạn (10 ca):** Nới rộng cửa sổ trích xuất `MAX_CITATION_EXCERPT_CHARS` từ 1000 lên 1500 ký tự hoặc tập trung trích xuất theo đoạn điều/khoản nguyên vẹn để `evidence_hit` đạt ≥ 90%.
   - **Thẩm định sự thật chuẩn (C-023, C-024):** Trình phê duyệt để sửa rubric của D73 (năm 2022) và D74 (kỳ 2 năm 2024-2025) khớp với văn bản PDF gốc.
   - **Lọc thực thể trường học ở tầng truy xuất (giải quyết N02):** Bổ sung bước kiểm tra thực thể tên trường trong câu hỏi (`Đại học Ngoại thương`) với danh sách trường được hỗ trợ trong cơ sở dữ liệu trước khi kích hoạt tìm kiếm vector.
