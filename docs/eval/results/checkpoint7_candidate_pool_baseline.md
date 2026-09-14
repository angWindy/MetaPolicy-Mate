# Mốc 7 - Đường cơ sở làm sạch tập ứng viên

## Phạm vi

Báo cáo này được tạo từ bộ dữ liệu kiểm thử tất định tại
`tests/test_rag/test_candidate_pool.py::test_candidate_pool_baseline_has_zero_recall_loss`.
Đây là đường cơ sở ở cấp hợp đồng, không phải đánh giá trên tập tài liệu sản xuất.

Bộ làm sạch lần lượt thực hiện:

1. Loại trùng theo `chunk_id`.
2. Phát hiện bản sao chính xác bằng `content_hash`.
3. Phát hiện thận trọng các đoạn gần trùng trong cùng tài liệu bằng cosine TF-IDF
   với ngưỡng `0.95`.
4. Giới hạn tối đa bốn đoạn trên mỗi tài liệu, đồng thời giữ lại các đoạn định nghĩa.

Phát hiện gần trùng không so sánh ứng viên thuộc các tài liệu khác nhau và không
loại bỏ các đoạn có định vị điều, khoản hoặc mục khác nhau.

## Trước và sau khi làm sạch

| Chỉ số | Trước | Sau |
| --- | ---: | ---: |
| Số ứng viên | 8 | 5 |
| Tỷ lệ đoạn duy nhất | 0.875 | 1.000 |
| Tỷ lệ nội dung duy nhất | 0.750 | 1.000 |
| Tỷ lệ đa dạng tài liệu | 0.625 | 1.000 |
| Số đoạn tối đa trong một tài liệu | 3 | 1 |
| Recall trên ba đoạn liên quan đã gán nhãn | 1.000 | 1.000 |
| Mức giảm Recall | - | 0.000 |

Mức giảm Recall quan sát được là 0%, nằm trong ngưỡng chấp nhận tối đa 5% của Mốc 7.

## Giới hạn

Bộ dữ liệu kiểm thử đại diện cho bản sao chính xác, đoạn chồng lấn, nội dung định
nghĩa và bằng chứng chính sách khác biệt. Recall trên toàn tập tài liệu cần được
đo bằng bộ dữ liệu chuẩn có phiên bản và ngữ cảnh chính sách xác thực cố định.
Kết quả tổng hợp này không được dùng để tuyên bố chất lượng sản xuất.
