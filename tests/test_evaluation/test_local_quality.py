from src.evaluation.local_quality import (
    average_precision,
    context_recall,
    extractive_faithfulness,
    token_f1,
)


def test_local_quality_metrics_are_deterministic_and_bounded():
    assert token_f1("Trưởng đơn vị phê duyệt", "Theo Điều 2: Trưởng đơn vị phê duyệt") > 0.75
    assert average_precision(["c1", "other"], {"c1"}) == 1.0
    assert context_recall(["c1"], {"c1", "c2"}) == 0.5
    assert extractive_faithfulness(
        "Theo văn bản: Nội dung đã được duyệt.", ["Nội dung đã được duyệt."]
    ) == 1.0


def test_local_quality_does_not_award_unsupported_answers():
    assert extractive_faithfulness("Câu trả lời bịa đặt", ["Bằng chứng khác"]) == 0.0
    assert average_precision(["forbidden"], set()) == 0.0
