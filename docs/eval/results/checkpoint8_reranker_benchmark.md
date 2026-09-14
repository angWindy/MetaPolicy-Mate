# Mốc 8 - Đo hiệu năng dịch vụ xếp hạng lại

## Môi trường và phạm vi

- Ngày: 2026-08-04
- Số cặp ứng viên mỗi yêu cầu: 60
- Kích thước lô cấu hình: 32
- Số vòng đo: 50, sau một lần chạy làm nóng
- Backend: bản thay thế kiểm thử `CrossEncoder.predict()` tổng hợp tất định
- Phép đo bao gồm điều phối luồng bất đồng bộ, kiểm tra đầu ra, ánh xạ ứng viên,
  sắp xếp, tạo kết quả Pydantic, ghi metadata và kiểm tra bộ ngắt mạch.

Lệnh chạy:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_reranker `
  --backend synthetic --candidates 60 --batch-size 32 --iterations 50
```

## Kết quả

| Chỉ số | Độ trễ |
| --- | ---: |
| p50 | 0.238 ms |
| p95 | 0.565 ms |
| Trung bình | 0.298 ms |

## Giới hạn

Phép đo này đánh giá chi phí dịch vụ và tính đúng của ánh xạ, không đo suy luận
mô hình nơ-ron. Môi trường ảo hiện tại không có `sentence-transformers` và chưa
tải trọng số `BAAI/bge-reranker-v2-m3`. Vì vậy, báo cáo không đưa ra kết luận về
độ trễ mô hình thực trên CPU/GPU. Sau khi cài `requirements-rag.txt` và chuẩn bị
phiên bản mô hình đã cấu hình, hãy chạy lại cùng lệnh với `--backend real` để tạo
kết quả đo suy luận theo phần cứng thực tế.
