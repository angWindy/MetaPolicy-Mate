# Mốc 6 - Đường cơ sở truy xuất lai

## Phạm vi

Đây là đường cơ sở tất định ở cấp hợp đồng từ
`tests/test_rag/test_hybrid.py::test_synthetic_hybrid_recall_baseline_at_50_and_100`.
Báo cáo xác minh hành vi hợp nhất thứ hạng mà không sử dụng tập tài liệu sản xuất
đang chạy hoặc bộ chấm mức độ liên quan. Không được diễn giải kết quả này là chất
lượng truy xuất trên môi trường sản xuất.

Bộ dữ liệu kiểm thử chứa ba mã đoạn liên quan. Truy xuất dense và sparse đều trả
về 100 ứng viên đã xếp hạng, với vị trí các đoạn liên quan bổ sung cho nhau. RRF
cân bằng dùng `k=60`; điểm cosine hoặc điểm sparse thô không được cộng vào điểm
hợp nhất.

## Kết quả

| Bộ truy xuất | Recall@50 | Recall@100 |
| --- | ---: | ---: |
| Dense | 0.333 | 0.667 |
| Sparse | 0.667 | 0.667 |
| RRF lai cân bằng | 0.667 | 1.000 |

## Diễn giải

Ca tổng hợp cho thấy lợi ích dự kiến của việc kết hợp bảng xếp hạng dense và
sparse: RRF lai tìm được toàn bộ đoạn đã gán nhãn trong 100 vị trí đầu. Trước khi
đưa ra kết luận về chất lượng sản xuất, cần tạo đường cơ sở trên toàn bộ tập tài
liệu bằng bộ dữ liệu chuẩn có phiên bản, ngữ cảnh chính sách cố định và chỉ mục
Qdrant thực tế.
