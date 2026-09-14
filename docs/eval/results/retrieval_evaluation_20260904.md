# Báo cáo đánh giá truy xuất RAG

- Bộ dữ liệu: `docs\eval\datasets\golden_questions.regression.jsonl`
- Bộ dữ liệu hợp lệ: `True`
- Trạng thái: **KHÔNG ĐẠT (`FAIL`)**

## Thông tin lần chạy

- generated_at_utc: `2026-09-04T12:17:55.693484+00:00`
- dataset_sha256: `53eecccd7a3a0e4dddb612f384b7057d53f157b5fcb39524cad86bb805810722`
- observations_sha256: `452cccbe92472a01bb5fcd0ac1e3117431ea764e5393fe41ce2d46a67441596e`
- index_version: `synthetic-regression-20260904`
- maximum_relevance_labels_per_case: `1`

## Các chỉ số

| Chỉ số | Giá trị |
|---|---:|
| cases | 7.0 |
| observations | 7.0 |

### Giai đoạn 1 - Truy xuất ứng viên

| Chỉ số | Giá trị |
|---|---:|
| recall_at_50 | 1.0 |
| recall_at_100 | 1.0 |
| mrr | 1.0 |
| unauthorized_retrieval_rate | 0.0 |
| latency_ms | 20.53031428606898 |
| latency_p50_ms | 19.802399998297915 |
| latency_p95_ms | 31.481699999858392 |

### Giai đoạn 2 - Xếp hạng lại

| Chỉ số | Giá trị |
|---|---:|
| precision_at_5 | 0.2 |
| recall_at_5 | 1.0 |
| mrr_at_5 | 1.0 |
| ndcg_at_5 | 1.0 |
| top1_accuracy | 1.0 |
| latency_ms | 10.209224999925937 |
| latency_p50_ms | 7.346000002144137 |
| latency_p95_ms | 15.142500000365544 |

### Giai đoạn 3 - RAG có kiểm soát

| Chỉ số | Giá trị |
|---|---:|
| faithfulness | None |
| citation_correctness | 0.8571428571428571 |
| citation_id_validity | 1.0 |
| answer_relevancy | None |
| abstention_accuracy | 0.8571428571428571 |
| version_correctness | 1.0 |
| latency_p50_ms | 140.46270000108052 |
| latency_p95_ms | 229.72759999902337 |

## Kết quả theo nhóm

- `department_retrieval`: cases=1.0, recall_at_100=1.0, precision_at_5=0.2, citation_correctness=1.0, abstention_accuracy=1.0
- `exact_answer`: cases=1.0, recall_at_100=1.0, precision_at_5=0.2, citation_correctness=1.0, abstention_accuracy=1.0
- `identifier`: cases=1.0, recall_at_100=1.0, precision_at_5=0.2, citation_correctness=1.0, abstention_accuracy=1.0
- `public_retrieval`: cases=1.0, recall_at_100=1.0, precision_at_5=0.2, citation_correctness=0.0, abstention_accuracy=0.0
- `unauthorized`: cases=1.0, recall_at_100=None, precision_at_5=None, citation_correctness=1.0, abstention_accuracy=1.0
- `out_of_domain`: cases=1.0, recall_at_100=None, precision_at_5=None, citation_correctness=1.0, abstention_accuracy=1.0
- `expired_version`: cases=1.0, recall_at_100=None, precision_at_5=None, citation_correctness=1.0, abstention_accuracy=1.0

## So sánh biến thể

- `hybrid_rrf`: precision_at_5=0.2, recall_at_5=1.0, mrr_at_5=1.0, ndcg_at_5=1.0, top1_accuracy=1.0, latency_ms=10.209224999925937
- `hybrid_reranker`: precision_at_5=0.2, recall_at_5=1.0, mrr_at_5=1.0, ndcg_at_5=1.0, top1_accuracy=1.0, latency_ms=10.209224999925937

## Giới hạn

- Một lần quét trực tiếp riêng đã hoàn tất trên API cục bộ với PostgreSQL, Qdrant và Redis: 110 ca, Precision tài liệu 0,9608, Recall 0,98, F1 0,9703, tỷ lệ trúng bằng chứng 0,80, độ đúng câu trả lời 0,8636 và tỷ lệ ca đạt 0,7727.
- Toàn bộ bộ kiểm thử kho mã hoàn tất với 502 ca đạt, 39 ca không đạt và 5 lỗi trước khi các dịch vụ trực tiếp sẵn sàng. Bộ kiểm thử tập trung cho đánh giá và truy xuất lai đạt 33 ca.

## Các trường hợp chưa đạt

- dòng 4 [public_retrieval]: thiếu bằng chứng kỳ vọng trong trích dẫn; trạng thái từ chối không khớp: kỳ vọng=False, thực tế=True
- C-025: Không thể diễn giải cổng Precision@5 vì bộ dữ liệu chưa gán nhãn đầy đủ năm đoạn liên quan cho mỗi câu hỏi có đáp án.

## Cổng chất lượng phát hành

```json
{
  "status": "FAIL",
  "checks": {
    "recall_at_100": true,
    "precision_at_5": false,
    "citation_id_validity": true,
    "unauthorized_retrieval": true,
    "graph_no_bypass": true,
    "reranker_ndcg_improvement": false
  },
  "missing_metrics": []
}
```
