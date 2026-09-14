# Kiểm định chất lượng truy xuất và câu trả lời RAG — 2026-09-03

## Kết luận

**KHÔNG ĐẠT — luồng RAG hiện tại chưa đủ tin cậy để tạo câu trả lời đúng nội dung.**

Kiểm định này chủ động loại trừ RBAC, phân quyền tenant, hành vi giao diện và mức
sẵn sàng sản xuất của toàn bộ bộ kiểm thử. Phạm vi chỉ đánh giá việc luồng RAG
đang chạy có truy xuất đúng tài liệu nguồn liên quan và câu trả lời sinh ra có
khớp với tài liệu đó hay không.

## Môi trường kiểm thử

- API: dịch vụ FastAPI cục bộ tại `http://127.0.0.1:8000`
- Tập tài liệu: nguồn PostgreSQL và chỉ mục truy xuất Qdrant đã cấu hình
- Bộ sinh: nhà cung cấp OpenAI đã cấu hình (`gpt-4o-mini`)
- Phương án dự phòng: Ollama, sau đó là template
- Bộ câu hỏi chuẩn: 21 câu hỏi HUST được chọn thủ công từ `tests/sweep/golden_v3.jsonl`
- Nhãn theo tập tài liệu hiện tại: được tạo chỉ đọc bằng cách đối chiếu từng dữ
  kiện kỳ vọng trong PostgreSQL

Không có khóa API, mật khẩu hoặc thông tin xác thực cơ sở dữ liệu nào được lưu
trong các kết quả này.

## Kết quả đo

Lần chạy trực tiếp 21 câu hỏi cho kết quả:

- Tìm đúng tài liệu kỳ vọng: **10/21 (47,6%)**
- Tìm đúng đoạn kỳ vọng: **9/21 (42,9%)**
- Precision tại hạng 1: **9/21 (42,9%)**
- Có chuỗi ký tự kỳ vọng theo nghĩa đen: **14/21 (66,7%)**
- Câu trả lời có độ tin cậy thấp hoặc từ chối: **6/21 (28,6%)**
- Câu trả lời sai rõ ràng hoặc không trả lời sau khi duyệt nguồn: **ít nhất 9/21 (42,9%)**

Không được coi điểm đối chiếu chuỗi ký tự là độ chính xác ngữ nghĩa. Chỉ số này
tính cả dương tính giả như Q16 và Q17, khi câu trả lời lặp lại một thuật ngữ trong
câu hỏi nhưng lại khẳng định sai rằng nguồn không tồn tại. Một số chuỗi kỳ vọng
trong bộ chuẩn cũng chỉ là tên thực thể thay vì nội dung trả lời được yêu cầu.

## Ví dụ lỗi đã xác nhận

- **Q01 — truy xuất sai chủ đề con:** câu hỏi yêu cầu toàn bộ học phí tiến sĩ,
  kỳ vọng là `26 triệu đồng/năm`; câu trả lời lại nêu học phí học lại và chuyên đề
  từ phần khác của cùng tài liệu.
- **Q05 — đọc bảng thiếu hoặc sai:** bảng nguồn có các trình độ Goethe A1, A2,
  B1, B2, C1 và C2; câu trả lời chỉ nêu `B1 trở lên`.
- **Q08 — trả lời sai với độ tin cậy cao dù đã có đúng đoạn:** nguồn ánh xạ A+
  thành `9,5–10`, nhưng câu trả lời nêu `8,5–9,4` là khoảng điểm A.
- **Q09, Q15, Q19 — từ chối sai:** hệ thống từ chối dù từng dữ kiện kỳ vọng đều
  tồn tại trong tập tài liệu PostgreSQL hiện tại.
- **Q16 — khẳng định thiếu dữ liệu sai:** hàng dữ liệu nguồn ánh xạ rõ mã sinh viên
  `20240799E` tới `KỸ THUẬT VẬT LIỆU`; câu trả lời nói không có sinh viên này.
- **Q17 — khẳng định thiếu dữ liệu sai:** tập tài liệu hiện tại có Điều 19 và các
  quy tắc cảnh báo học tập, nhưng câu trả lời nói không có quy định `5445/QĐ-ĐHBK`.
- **Q18 — sai phạm vi bằng chứng:** câu trả lời chỉ đưa ra yêu cầu ngoại ngữ từ
  tài liệu khác thay vì điều kiện tốt nghiệp trong quy định 5445.

Q14 không nằm trong số lỗi ngữ nghĩa đã xác nhận vì chuỗi kỳ vọng (`Phụ lục I`)
không mã hóa mức học phí được hỏi. Truy xuất vẫn bỏ sót tài liệu/đoạn kỳ vọng nên
ca này vẫn không đạt về truy xuất; cần củng cố nhãn chuẩn trước khi dùng để chấm
câu trả lời.

## Tính toàn vẹn của tập tài liệu và phép đánh giá

Kiểm định đối chiếu PostgreSQL chỉ đọc đã tìm thấy từng chuỗi kỳ vọng được gán
nhãn cho đủ 21 câu hỏi, đồng thời tìm thấy chuỗi đó trong đúng tài liệu kỳ vọng
cho cả 21 câu. Các trích đoạn nguồn được kiểm tra riêng cũng xác nhận dữ kiện của
những ca từ chối sai đã nêu. Do đó, không thể giải thích các lỗi này bằng việc
thiếu dữ liệu nguồn.

Toàn bộ mã đoạn được gán nhãn ban đầu đã lỗi thời (`0/21` ca còn giữ mã đoạn hiện
tại). Tập tài liệu đã được nạp hoặc chia đoạn lại. Một bản sao bộ chuẩn tạm thời
theo tập tài liệu hiện tại được tạo cho lần chạy trực tiếp; tệp chuẩn đã commit
không bị âm thầm sửa đổi.

Phép đánh giá tự động ban đầu cũng bị lệch schema: bảy dòng hồi quy không cung cấp
hai trường bắt buộc `should_abstain` và `security_category`. Các dữ liệu kiểm thử
này đã được chuyển đổi rõ ràng.

## Lỗi đã sửa để phép kiểm thử hợp lệ

Bộ sinh trực tiếp ban đầu lỗi ở mọi yêu cầu với thông báo:

`ValueError: zip() argument 2 is shorter than argument 1`

Cấu hình dự phòng có Ollama và template nhưng chưa cài gói Ollama tùy chọn. Dịch
vụ lưu một đối tượng chạy được trong khi vẫn giữ hai tên nhà cung cấp, rồi dùng
`zip` ở chế độ nghiêm ngặt. Phần triển khai hiện chỉ ghi tên các nhà cung cấp dự
phòng đã tạo thành công và giữ chúng đồng bộ với các đối tượng chạy. Một kiểm thử
hồi quy bao phủ trường hợp thiếu nhà cung cấp tùy chọn.

Bản sửa này loại bỏ lỗi hạ tầng; nó không cải thiện điểm truy xuất hoặc chất lượng
câu trả lời đã đo.

## Xác minh

- Hồi quy tập trung: **34 đạt**, 18 cảnh báo
- Riêng pipeline đánh giá: **10 đạt**, 1 cảnh báo
- Riêng kiểm thử LLM bền vững: **7 đạt**, 1 cảnh báo
- Ruff trên các tệp Python đã thay đổi: **đạt**
- `git diff --check`: không có lỗi khoảng trắng (chỉ có thông báo về kiểu xuống dòng)

Các cảnh báo là cảnh báo ngừng hỗ trợ hiện có của Pydantic và pytest-asyncio,
không làm thay đổi kết quả kiểm định.

## Tệp bằng chứng

- `rag_quality_live_20260903.jsonl`: toàn bộ 21 phản hồi trực tiếp và chỉ số truy xuất
- `rag_quality_focused_20260903.jsonl`: lần chạy tập trung lặp lại cho tám lỗi chưa rõ
- `rag_source_alignment_20260903.json`: đối chiếu nguồn chỉ đọc và các trích đoạn đã chọn

## Cổng chất lượng đề xuất tiếp theo

Chưa được công bố chất lượng câu trả lời RAG đã sẵn sàng. Trước tiên cần sửa truy
xuất cho truy vấn mã định danh, số hiệu văn bản và hàng trong bảng; sau đó bổ sung
câu trả lời tham chiếu hoặc rubric ngữ nghĩa vào bộ chuẩn. Chạy lại cùng 21 câu và
yêu cầu đồng thời đạt ngưỡng truy xuất có ý nghĩa cùng độ đúng ngữ nghĩa đã được
con người xác nhận. Chỉ số chuỗi con theo nghĩa đen không đủ làm cổng phát hành.
