# Báo cáo đánh giá truy xuất và câu trả lời RAG trên môi trường trực tiếp

- Thời điểm tạo (UTC): `2026-09-04T12:28:30.723674+00:00`
- API được kiểm thử: `http://127.0.0.1:8000/api/v1/chat`
- Bộ dữ liệu chuẩn: `tests\sweep\golden_v7_domain_100.jsonl, tests\sweep\golden_v8_negative_10.jsonl`
- Tổng số trường hợp: `110`
- Kết luận: **KHÔNG ĐẠT**

## Chỉ số tổng hợp

| Chỉ số | Giá trị |
|---|---:|
| Độ chính xác tài liệu - Precision micro | 96.08% |
| Độ bao phủ tài liệu - Recall micro | 98.00% |
| Điểm cân bằng tài liệu - F1 micro | 97.03% |
| Tỷ lệ tìm đúng tài liệu | 96.36% |
| Tỷ lệ trích đúng bằng chứng | 80.00% |
| Tỷ lệ câu trả lời đúng | 86.36% |
| Tỷ lệ đạt toàn bộ tiêu chí | 77.27% |
| Recall trên câu hỏi có đáp án | 98.00% |
| Tỷ lệ từ chối an toàn ngoài phạm vi | 80.00% |
| Độ trễ p50 (giây) | 3.4 |
| Độ trễ p95 (giây) | 5.1 |

## Ma trận kết quả truy xuất theo tài liệu

- Đúng và có truy xuất (True Positive): `98`
- Truy xuất nhầm tài liệu (False Positive): `4`
- Bỏ sót tài liệu đúng (False Negative): `2`

## Cách hiểu các chỉ số

- Precision cho biết trong các tài liệu được trích dẫn, bao nhiêu tài liệu khớp tài liệu chuẩn; tài liệu không liên quan được tính là False Positive.
- Recall cho biết hệ thống tìm được tài liệu chuẩn trong bao nhiêu câu hỏi có đáp án.
- F1 là trung bình điều hòa giữa Precision và Recall, dùng để cân bằng khả năng tìm đúng và tránh lấy thừa tài liệu.
- Điểm bằng chứng và điểm câu trả lời được tách riêng vì tìm đúng văn bản chưa chứng minh rằng hệ thống đã chọn đúng đoạn hoặc sinh đúng câu trả lời.
- Precision@5 theo chunk không được dùng làm kết luận phát hành vì bộ dữ liệu chưa gán nhãn đầy đủ toàn bộ chunk liên quan trong top 5 (C-025).

## Nhận xét

- Recall tài liệu tốt: hệ thống hiếm khi bỏ sót văn bản nguồn cần tìm.
- Precision tài liệu tốt: số tài liệu không liên quan lọt vào citation thấp.
- Khả năng từ chối câu hỏi ngoài phạm vi dưới 95%; cần xử lý các ca sinh câu trả lời sai trước khi phát hành.
- Chọn bằng chứng yếu hơn tìm tài liệu; cần ưu tiên chất lượng chunking, reranking và cửa sổ citation.

## Các trường hợp chưa đạt

- `D24` (đào tạo): thiếu nội dung bắt buộc: 3, thiếu một trong các nội dung: cuối mỗi học kỳ chính|cuối hai học kỳ chính, thiếu một trong các nội dung: cuối học kỳ hè
- `D25` (đào tạo): thiếu nội dung bắt buộc: 3 tháng
- `D26` (đào tạo): thiếu nội dung bắt buộc: 3 tháng
- `D30` (học phí): thiếu một trong các nội dung: 440|600
- `D32` (học phí): thiếu nội dung bắt buộc: 550, thiếu một trong các nội dung: nghìn|550.000
- `D38` (học phí): truy xuất hoặc bằng chứng không khớp
- `D48` (ngoại ngữ): truy xuất hoặc bằng chứng không khớp
- `D50` (ngoại ngữ): truy xuất hoặc bằng chứng không khớp
- `D53` (thay đổi ngữ cảnh): thiếu nội dung bắt buộc: 500, thiếu một trong các nội dung: nghìn|500.000
- `D58` (thay đổi ngữ cảnh): thiếu nội dung bắt buộc: Bậc 3
- `D59` (thay đổi ngữ cảnh): thiếu nội dung bắt buộc: tiếng Pháp, thiếu một trong các nội dung: không|Không đặt
- `D60` (thay đổi ngữ cảnh): truy xuất hoặc bằng chứng không khớp
- `D62` (thay đổi ngữ cảnh): thiếu nội dung bắt buộc: bậc 6
- `D73` (đào tạo): thiếu một trong các nội dung: khóa 66|K66|2021
- `D74` (đào tạo): thiếu nội dung bắt buộc: 2025-2026, thiếu một trong các nội dung: học kỳ 1|kỳ 1
- `D78` (đào tạo): truy xuất hoặc bằng chứng không khớp
- `D81` (đào tạo): thiếu một trong các nội dung: nghĩa vụ quân sự|quân sự
- `D82` (đào tạo): truy xuất hoặc bằng chứng không khớp
- `D83` (đào tạo): truy xuất hoặc bằng chứng không khớp
- `D84` (đào tạo): truy xuất hoặc bằng chứng không khớp
- `D94` (học phí): thiếu nội dung bắt buộc: 600, thiếu một trong các nội dung: nghìn|600.000
- `D96` (ngoại ngữ): truy xuất hoặc bằng chứng không khớp
- `D98` (ngoại ngữ): truy xuất hoặc bằng chứng không khớp
- `N02` (ngoài phạm vi): thiếu một trong các nội dung: không có đủ|chưa có đủ|không có thông tin|chưa đủ căn cứ|chưa có căn cứ|chưa được xác định|chưa thể xác minh|không tìm thấy|không đề cập
- `N06` (ngoài phạm vi): thiếu một trong các nội dung: không có đủ|chưa có đủ|không có thông tin|chưa đủ căn cứ|chưa có căn cứ|chưa được xác định|chưa thể xác minh|không tìm thấy|không đề cập

## Các xung đột nhãn đã biết

- D73 và D74 không được dùng để công bố điểm đã hiệu chỉnh cho đến khi data owner giải quyết C-023 và C-024.
- Precision@5 chỉ mang tính chẩn đoán cho đến khi C-025 được giải quyết bằng nhãn relevance đầy đủ cho top 5 hoặc chuyển sang contract Hit@5.
