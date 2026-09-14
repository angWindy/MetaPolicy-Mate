# Mốc 17 - Báo cáo đánh giá

- Bộ dữ liệu: `eval\datasets\golden_questions.example.jsonl`
- Bộ dữ liệu hợp lệ: `False`
- Trạng thái: **KHÔNG ĐỦ DỮ LIỆU (`INSUFFICIENT_DATA`)**

## Các chỉ số

| Chỉ số | Giá trị |
|---|---:|

## Các lỗi

- Dòng chuẩn 1 không hợp lệ: có 8 lỗi xác thực `GoldenCase`. Khối dưới đây giữ
  nguyên thông báo Pydantic để phục vụ đối chiếu kỹ thuật:

```text
query
  Field required [type=missing, input_value={'question': 'Thời hạ...ata owner xác nhận.'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
user_context
  Field required [type=missing, input_value={'question': 'Thời hạ...ata owner xác nhận.'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
reference_answer
  Field required [type=missing, input_value={'question': 'Thời hạ...ata owner xác nhận.'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
expected_status
  Field required [type=missing, input_value={'question': 'Thời hạ...ata owner xác nhận.'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
question
  Extra inputs are not permitted [type=extra_forbidden, input_value='Thời hạn xử lý hồ sơ là bao lâu?', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden
department
  Extra inputs are not permitted [type=extra_forbidden, input_value='PUBLIC', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden
roles
  Extra inputs are not permitted [type=extra_forbidden, input_value=['staff'], input_type=list]
    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden
reference
  Extra inputs are not permitted [type=extra_forbidden, input_value='Thay bằng câu trả l...data owner xác nhận.', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden
```

## Cổng chất lượng phát hành

```json
{
  "status": "INSUFFICIENT_DATA",
  "missing_metrics": [
    "golden_labels",
    "runner_observations"
  ]
}
```
