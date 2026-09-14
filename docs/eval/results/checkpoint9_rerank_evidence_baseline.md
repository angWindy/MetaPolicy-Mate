# Mốc 9 - Đường cơ sở xếp hạng lại bằng chứng

## Phạm vi

Đây là đường cơ sở tất định ở cấp hợp đồng từ
`tests/test_rag/test_evidence_rerank.py::test_synthetic_ndcg_at_five_improves_after_rerank`.
Báo cáo xác minh xếp hạng và chọn ngữ cảnh cuối mà không tải mô hình, gọi dịch vụ
ngoài hoặc dùng tập tài liệu sản xuất. Không được diễn giải kết quả này là chất
lượng truy xuất trên môi trường sản xuất.

Bộ dữ liệu kiểm thử có bốn đoạn liên quan đã chấm mức. Đường cơ sở hợp nhất chỉ
đặt hai đoạn vào top 5, còn điểm CrossEncoder giả lập đặt đủ bốn đoạn theo thứ tự
mức độ liên quan. nDCG dùng độ lợi lũy thừa (`2^relevance - 1`) và ngưỡng cắt 5.

## Kết quả

| Cách xếp hạng | nDCG@5 |
| --- | ---: |
| Fusion/RRF trước xếp hạng lại | 0.388782 |
| Thứ tự CrossEncoder trước bước đa dạng hóa | 1.000000 |
| Mức cải thiện tuyệt đối | +0.611218 |

Bộ dữ liệu tất định cho thấy mức cải thiện so với đường cơ sở hợp nhất và vẫn giữ
đoạn sự thật chuẩn đã gán nhãn sau bước đa dạng hóa. Bước chọn cuối cũng giới hạn
tối đa hai đoạn trên mỗi tài liệu.

## Giới hạn

Kết luận sản xuất cần bộ dữ liệu chuẩn tiếng Việt có phiên bản, suy luận
CrossEncoder thực bằng phiên bản mô hình đã cấu hình, ngữ cảnh chính sách đã xác
thực và đánh giá trên chỉ mục Qdrant cố định. Ngưỡng điểm thô và khoảng cách điểm
mặc định vẫn tắt cho tới khi phép đánh giá đó hiệu chỉnh chúng cho mô hình đã chọn.
