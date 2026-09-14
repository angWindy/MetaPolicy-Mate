from __future__ import annotations

import re

import pytest

from tests.sweep.run_sweep import (
    _answer_matches,
    _groups_match,
    evaluate,
    retrieval_document_metrics,
)


def test_answer_rubric_accepts_typographic_decimal_variants() -> None:
    passed, failures = _answer_matches(
        "Điểm A+ nằm trong khoảng 9.5–10.",
        {
            "must_include_all": ["A+", "9,5", "10"],
            "must_include_any": [],
            "must_not_include": ["8,5"],
        },
    )

    assert passed is True
    assert failures == []


def test_answer_rubric_rejects_wrong_table_row_value() -> None:
    passed, failures = _answer_matches(
        "Điểm A+ nằm trong khoảng 8,5-9,4.",
        {
            "must_include_all": ["A+", "9,5", "10"],
            "must_include_any": [],
            "must_not_include": ["8,5", "9,4"],
        },
    )

    assert passed is False
    assert "missing:9,5" in failures
    assert "forbidden:8,5" in failures


def test_stable_evidence_groups_do_not_depend_on_chunk_uuid() -> None:
    assert _groups_match(
        "Thạc sĩ (các ngành kỹ thuật, công nghệ): 720.000 đồng/TCHP.",
        [["Thạc sĩ"], ["720.000 đồng/TCHP"]],
    )


def test_evaluate_requires_document_evidence_and_answer() -> None:
    case = {
        "id": "T01",
        "query": "Học phí tiến sĩ mỗi năm là bao nhiêu?",
        "expected_doc": "10232/QĐ-ĐHBK",
        "source_locator": {
            "document_number": "10232/QĐ-ĐHBK",
            "evidence_groups": [["Tiến sĩ"], ["26 triệu đồng/năm"]],
        },
        "reference_answer": "26 triệu đồng/năm.",
        "answer_expectations": {
            "must_include_all": ["26 triệu"],
            "must_include_any": [],
            "must_not_include": [],
        },
        "response": {
            "answer": "Học phí chương trình tiến sĩ là 26 triệu đồng/năm.",
            "citations": [
                {
                    "document_number": "10232/QĐ-ĐHBK",
                    "chunk_id": "new-uuid-after-reindex",
                    "excerpt": "Tiến sĩ: 26 triệu đồng/năm.",
                }
            ],
        },
    }

    [result] = evaluate([case], "unused")

    assert result["chunk_hit"] is None
    assert result["precision_at_1"] is None
    assert result["case_pass"] is True


def test_summary_marks_unlabeled_chunk_metrics_as_unavailable(capsys) -> None:
    from tests.sweep.run_sweep import print_summary

    print_summary(
        [
            {
                "doc_hit": True,
                "chunk_hit": None,
                "precision_at_1": None,
                "evidence_hit": True,
                "answer_correct": True,
                "case_pass": True,
                "evidence_status": None,
                "confidence": "high",
            }
        ]
    )

    output = capsys.readouterr().out
    assert "chunk_hit            = N/A" in output
    assert "precision_at_1       = N/A" in output


def test_golden_loader_rejects_legacy_uuid_only_case(tmp_path) -> None:
    from tests.sweep.run_sweep import load_golden

    golden = tmp_path / "legacy.jsonl"
    golden.write_text('{"id":"Q01","query":"x","expected_doc":"D"}\n')

    with pytest.raises(ValueError, match="missing"):
        load_golden(golden)


def test_document_precision_recall_and_f1_count_wrong_citations() -> None:
    metrics = retrieval_document_metrics(
        [
            {
                "expected_doc": "A/QD",
                "cited_doc_nums": ["A/QD", "B/QD"],
            },
            {"expected_doc": "C/QD", "cited_doc_nums": []},
            {"expected_doc": "NONE", "cited_doc_nums": ["D/QD"]},
        ]
    )

    assert metrics["true_positive"] == 1
    assert metrics["false_positive"] == 2
    assert metrics["false_negative"] == 1
    assert metrics["precision"] == pytest.approx(1 / 3)
    assert metrics["recall"] == pytest.approx(1 / 2)
    assert metrics["f1"] == pytest.approx(0.4)


def test_domain_golden_set_has_fifty_unique_cases() -> None:
    from tests.sweep.run_sweep import GOLDEN_PATH, load_golden

    cases = load_golden(GOLDEN_PATH)
    assert len(cases) == 50
    assert len({case["id"] for case in cases}) == 50


def test_domain_golden_set_excludes_student_records_and_admission_queries() -> None:
    from tests.sweep.run_sweep import GOLDEN_PATH, load_golden

    cases = load_golden(GOLDEN_PATH)
    forbidden_topics = {"admission", "student", "learner"}
    forbidden_patterns = [
        re.compile(r"\b20\d{6}[A-Z]\b", re.IGNORECASE),
        re.compile(r"\b(mã|danh sách)\s+(học viên|sinh viên|thí sinh)\b", re.IGNORECASE),
        re.compile(r"\b(ai|người nào)\s+(là|có mã)\b", re.IGNORECASE),
    ]

    assert not forbidden_topics.intersection({case["topic"] for case in cases})
    for case in cases:
        searchable = f'{case["query"]} {case["reference_answer"]}'
        assert not any(pattern.search(searchable) for pattern in forbidden_patterns)


def test_cli_default_gate_is_eighty_percent(monkeypatch) -> None:
    from tests.sweep import run_sweep

    cases = [
        {
            "id": f"D{index:02d}",
            "query": "q",
            "topic": "training",
            "expected_doc": "5445/QĐ-ĐHBK",
            "source_locator": {"evidence_groups": [["x"]]},
            "reference_answer": "x",
            "answer_expectations": {},
        }
        for index in range(1, 51)
    ]
    results = [{"case_pass": index < 40} for index in range(50)]
    monkeypatch.setattr(run_sweep, "load_golden", lambda _path: cases)
    monkeypatch.setattr(run_sweep, "evaluate", lambda *_args, **_kwargs: results)
    monkeypatch.setattr(run_sweep, "print_summary", lambda _results: None)
    monkeypatch.setattr(run_sweep.sys, "argv", ["run_sweep.py"])

    assert run_sweep.main() == 0

    results[:] = [{"case_pass": index < 39} for index in range(50)]
    assert run_sweep.main() == 1
