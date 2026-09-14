"""Unit tests for the rule-based metadata extractor."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.ingestion.metadata_extractor import (
    _HEADING_RE,
    _PARENTHETICAL_TITLE_MULTILINE_RE,
    _PARENTHETICAL_TITLE_OCR_TOLERANT_RE,
    _PARENTHETICAL_TITLE_RE,
    _extract_title_from_header,
    extract_metadata,
)


@dataclass
class _Block:
    text: str


def test_extracts_document_number_and_parenthetical_title():
    header = (
        "BỘ GIÁO DỤC VÀ ĐÀO TẠO\n"
        "ĐẠI HỌC BÁCH KHOA HÀ NỘI\n"
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
        "Độc lập - Tự do - Hạnh phúc\n"
        "Số: 10232/QĐ-ĐHBK\n"
        "Hà Nội, ngày 24 tháng 7 năm 2025\n"
        "\n"
        "QUYẾT ĐỊNH\n"
        "(Về việc phê duyệt mức học phí năm học 2025-2026)\n"
        "\n"
        "GIÁM ĐỐC ĐẠI HỌC BÁCH KHOA HÀ NỘI\n"
    )
    result = extract_metadata(blocks=[_Block(text=header)])
    assert result.document_number == "10232/QĐ-ĐHBK"
    assert result.document_number_confidence >= 0.85
    assert result.title is not None
    assert result.title.title == "Về việc phê duyệt mức học phí năm học 2025-2026"
    assert result.title.confidence == 1.0
    assert result.title.needs_human_review is False
    # The rule extractor considers any non-`Số:` first-line result to need
    # human review, so the combined flag stays True even when individual
    # sub-probes are confident. Callers that want a strict accept signal
    # can check the per-field probes instead.


def test_extracts_title_without_parenthetical_needs_human():
    header = (
        "Số: 5445/QĐ-ĐHBK\n"
        "Hà Nội, ngày 1 tháng 1 năm 2024\n"
        "\n"
        "QUY CHẾ\n"
        "Đào tạo đại học\n"
        "Của Đại học Bách khoa Hà Nội\n"
    )
    result = extract_metadata(blocks=[_Block(text=header)])
    assert result.document_number == "5445/QĐ-ĐHBK"
    assert result.title is not None
    assert result.title.title == "Đào tạo đại học"
    assert result.title.needs_human_review is True
    # Title without parenthetical always needs human review.
    assert result.needs_human_review is True


def test_empty_text_returns_no_document_number():
    result = extract_metadata(blocks=[_Block(text="")])
    assert result.document_number is None
    assert result.document_number_confidence == 0.0
    assert result.needs_human_review is True


def test_no_recognised_number_needs_human():
    header = "Một văn bản nào đó không có số hiệu rõ ràng ở đầu."
    result = extract_metadata(blocks=[_Block(text=header)])
    assert result.document_number is None
    assert result.needs_human_review is True


def test_multiple_numbers_keep_top_candidate():
    header = (
        "Số: 10232/QĐ-ĐHBK\n"
        "Hà Nội, ngày 1 tháng 1 năm 2025\n"
        "\n"
        "QUYẾT ĐỊNH\n"
        "(Về việc phê duyệt)\n"
        "\n"
        "Theo Quyết định 7737/QĐ-ĐHBK ban hành ngày 1/1/2024.\n"
    )
    result = extract_metadata(blocks=[_Block(text=header)])
    assert result.document_number == "10232/QĐ-ĐHBK"
    # 10232 appears in two paragraphs (header + body) while 7737 only once,
    # so 10232 dominates the candidate ranking.
    assert result.document_number_confidence >= 0.5


def test_header_text_override_skips_reassembly():
    result = extract_metadata(
        blocks=[_Block(text="ignored text")],
        header_text_override="Số: 9999/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n(Về việc thử nghiệm)\n",
    )
    assert result.document_number == "9999/QĐ-ĐHBK"
    assert result.title.title == "Về việc thử nghiệm"


def test_rationale_string_summarises_findings():
    header = "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n(Về học phí)\n"
    result = extract_metadata(blocks=[_Block(text=header)])
    assert "doc=10232/QĐ-ĐHBK" in result.rationale
    assert "title=" in result.rationale


def test_filename_hint_recovers_ocr_missed_number():
    # OCR returns a non-canonical ``QD-DHBK`` form that the regex still
    # recognises, but the filename hint vouches for the canonical
    # ``QĐ-ĐHBK`` Vietnamese spelling.
    header = "Số: 5980/QD-DHBK\n\nQUYẾT ĐỊNH\n(Về việc thực tập)\n"
    result = extract_metadata(
        blocks=[_Block(text=header)],
        filename_hint="5980.pdf",
    )
    assert result.document_number == "5980/QĐ-ĐHBK"
    assert result.document_number_confidence == 1.0
    assert result.needs_human_review is False


def test_filename_hint_provides_fallback_when_no_match():
    # OCR returns nothing resembling a document number; the filename is
    # the only signal. We still flag the result for human review.
    result = extract_metadata(
        blocks=[_Block(text="Đ�I HỌC BÁCH KHOA HÀ NỘI\n\nQUYẾT ĐỊNH")],
        filename_hint="7323.pdf",
    )
    assert result.document_number == "7323/QĐ-ĐHBK"
    assert result.document_number_confidence == 0.80
    assert result.needs_human_review is True


def test_filename_hint_disagrees_with_ocr_flags_human_review():
    # OCR sees a number that disagrees with the filename; drop the OCR
    # guess and surface the filename hint at zero confidence so a human
    # reviewer takes a second look.
    header = "Số: 9999/QĐ-ĐHBK\n\nQUYẾT Đ�NH"
    result = extract_metadata(
        blocks=[_Block(text=header)],
        filename_hint="5980.pdf",
    )
    assert result.document_number == "5980/QĐ-ĐHBK"
    assert result.document_number_confidence == 0.0
    assert result.needs_human_review is True


def test_filename_hint_ignored_for_non_hust_filename():
    # Filenames without a leading number get the hint stripped.
    header = "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n(Về học phí)"
    result = extract_metadata(
        blocks=[_Block(text=header)],
        filename_hint="regulations.pdf",
    )
    # Behaves exactly as before (no hint applied).
    assert result.document_number == "10232/QĐ-ĐHBK"
    assert "filename_hint" not in result.rationale


# ─────────────────────────────────────────────────────────────────────────────
# Regression tests for OCR-tolerant regex (heading + parenthetical)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "line",
    [
        "QUYẾT ĐỊNH",
        "  QUYẾT ĐỊNH  ",
        "• QUYẾT ĐỊNH",
        "- QUYẾT ĐỊNH .",
        "QUYẾT ĐỊNH .|",
        "THÔNG BÁO",
        "* THÔNG BÁO *",
        "§ BÁO CÁO §",
        "QUY CHẾ\n",
        "‣ KẾ HOẠCH",
    ],
)
def test_heading_re_tolerates_ocr_noise(line: str) -> None:
    """The heading regex must accept OCR noise (leading bullets, trailing
    punctuation, stray pipes) on the same line, otherwise real scans with
    bordered headings fall back to the lower-confidence heuristics."""
    assert _HEADING_RE.search(line) is not None, f"line {line!r} did not match"


@pytest.mark.parametrize(
    "line",
    [
        # OCR-stuck: heading word merged into the next word.
        "QUYẾT ĐỊNHTRƯỜNG",
        # Random mid-sentence mention.
        "theo QUYẾT ĐỊNH số 123/QĐ.",
        # Empty.
        "",
    ],
)
def test_heading_re_rejects_negative_cases(line: str) -> None:
    assert _HEADING_RE.search(line) is None, f"line {line!r} should not match"


@pytest.mark.parametrize(
    ("header", "expected_title"),
    [
        # Bullet at the start of the heading line.
        (
            "Số: 10232/QĐ-ĐHBK\n\n• QUYẾT ĐỊNH\n(Về việc ban hành học phí)\n",
            "Về việc ban hành học phí",
        ),
        # Trailing punctuation on the heading line.
        (
            "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH .\n(Về việc ban hành ?)\n",
            "Về việc ban hành",
        ),
        # Stray pipe / OCR-tail on the heading line.
        (
            "Số: 10232/QĐ-ĐHBK\n\nTHÔNG BÁO |\n(Về lịch thi học kỳ)\n",
            "Về lịch thi học kỳ",
        ),
        # Trailing pipe on the parenthetical line.
        (
            "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n(Về học phí) |\n",
            "Về học phí",
        ),
        # Both lines have noise.
        (
            "Số: 10232/QĐ-ĐHBK\n\n- QUYẾT ĐỊNH .\n(Về học phí) ?\n",
            "Về học phí",
        ),
    ],
)
def test_extract_title_with_ocr_noise(header: str, expected_title: str) -> None:
    result = extract_metadata(blocks=[_Block(text=header)])
    assert result.title is not None
    assert result.title.title == expected_title
    assert result.title.confidence == 1.0
    assert result.title.needs_human_review is False


def test_extract_title_pure_paren_noise_punctuation_marker() -> None:
    """A parenthetical that opens with a stray punctuation char (``(. ...)``)
    should still be matched, otherwise OCR-broken opens reject valid titles."""
    header = "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n(. Về việc ban hành học phí .)\n"
    result = extract_metadata(blocks=[_Block(text=header)])
    assert result.title is not None
    assert "Về việc ban hành học phí" in result.title.title


def test_heading_re_suffix_does_not_swallow_whole_sentence() -> None:
    """The trailing-noise suffix is bounded by ``{0,30}`` so a heading-like
    word followed by a full sentence is *not* matched as a heading line.
    """
    text = (
        "QUYẾT ĐỊNH ban hành năm 2025 về một số chính sách mới "
        "đối với cán bộ giảng viên trong toàn trường."
    )
    assert _HEADING_RE.search(text) is None


def test_parenthetical_re_does_not_match_unbalanced() -> None:
    """An unbalanced parenthesis (only the opening or only the closing)
    must not match — otherwise the search would happily extract anything
    between the first ``(`` and the next ``)`` on the same line."""
    assert _PARENTHETICAL_TITLE_RE.search("(unbalanced") is None
    assert _PARENTHETICAL_TITLE_RE.search("unbalanced)") is None


def test_extract_title_from_header_handles_ocr_noise_directly() -> None:
    """Calling ``_extract_title_from_header`` directly keeps the same
    contraction contract as ``extract_metadata`` but isolates the regex
    behaviour so a failure here points at the regex and not the higher
    level document-number pipeline."""
    text = (
        "BỘ GIÁO DỤC VÀ ĐÀO TẠO\n"
        "ĐẠI HỌC BÁCH KHOA HÀ NỘI\n"
        "Số: 10232/QĐ-ĐHBK\n"
        "\n"
        "• QUYẾT ĐỊNH .\n"
        "(Về việc phê duyệt mức học phí)\n"
    )
    result = _extract_title_from_header(text)
    assert result.raw == "Về việc phê duyệt mức học phí"
    assert result.confidence == 1.0
    assert result.needs_human_review is False


# ─────────────────────────────────────────────────────────────────────────────
# Multi-line parenthetical + OCR bracket misread fallbacks
# ─────────────────────────────────────────────────────────────────────────────


def test_strict_paren_re_does_not_match_across_lines() -> None:
    """The strict (single-line) ``_PARENTHETICAL_TITLE_RE`` must reject a
    parenthetical whose *content* spans more than one line — that's the
    job of the multiline variant. Pinning this down prevents a future
    refactor from silently making the strict regex permissive."""
    text = (
        "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n"
        "(Về việc ban hành\nhọc phí năm học 2025)\n"
    )
    assert _PARENTHETICAL_TITLE_RE.search(text) is None


def test_multiline_paren_re_matches_inner_wrap() -> None:
    text = (
        "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n"
        "(Về việc ban hành\nhọc phí năm học 2025)\n"
    )
    m = _PARENTHETICAL_TITLE_MULTILINE_RE.search(text)
    assert m is not None
    assert "Về việc ban hành" in m.group(1)
    assert "học phí năm học 2025" in m.group(1)


def test_ocr_tolerant_paren_re_accepts_common_brackets() -> None:
    """OCR routinely misreads ``(`` as ``1`` / ``I`` / ``l`` / ``|`` and the
    half-width katakana ``｢`` on Vietnamese scans. The tolerant regex must
    accept those substitutions as a fallback."""
    samples = [
        "1Về việc ban hành học phí1",
        "IVề việc ban hành học phíI",
        "lVề việc ban hành học phíl",
        "|Về việc ban hành học phí|",
        "｢Về việc ban hành học phí｣",
    ]
    for sample in samples:
        assert _PARENTHETICAL_TITLE_OCR_TOLERANT_RE.search(sample) is not None, (
            f"{sample!r} did not match the OCR-tolerant bracket pattern"
        )


def test_ocr_tolerant_paren_re_does_not_match_in_middle_of_word() -> None:
    """The OCR-tolerant variant must still respect the line-start anchor;
    a stray ``1`` mid-sentence must not accidentally open a fake
    parenthetical."""
    text = "Số: 12.345/QĐ\n\nQUYẾT ĐỊNH\nMã số 1ghx7, vui lòng kiểm tra\n"
    assert _PARENTHETICAL_TITLE_OCR_TOLERANT_RE.search(text) is None


@pytest.mark.parametrize(
    ("text", "expected_raw", "expected_rationale", "expected_conf"),
    [
        # Inner-wrap falls through to multiline.
        (
            "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n(Về việc ban hành\nhọc phí)\n",
            "Về việc ban hành\nhọc phí",
            "parenthetical-multiline",
            0.85,
        ),
        # 1...1 OCR brackets fall through to tolerant.
        (
            "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n1Về việc ban hành học phí1\n",
            "Về việc ban hành học phí",
            "parenthetical-ocr-tolerant",
            0.7,
        ),
        # I...I OCR brackets fall through to tolerant.
        (
            "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\nIVề việc ban hành học phíI\n",
            "Về việc ban hành học phí",
            "parenthetical-ocr-tolerant",
            0.7,
        ),
        # ｢...｣ OCR brackets fall through to tolerant.
        (
            "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n｢Về việc ban hành học phí｣\n",
            "Về việc ban hành học phí",
            "parenthetical-ocr-tolerant",
            0.7,
        ),
    ],
)
def test_extract_title_falls_back_when_strict_fails(
    text: str,
    expected_raw: str,
    expected_rationale: str,
    expected_conf: float,
) -> None:
    result = _extract_title_from_header(text)
    assert result.raw == expected_raw
    assert result.rationale == expected_rationale
    assert abs(result.confidence - expected_conf) < 0.001
    # Strict-tier matches stay clean; fallback matches always need review.
    if expected_rationale != "parenthetical-after-heading":
        assert result.needs_human_review is True


def test_strict_match_takes_precedence_over_fallbacks() -> None:
    """Even if a tolerant/brackets-misread match *would* also apply, the
    strict pattern always wins so a clean scan doesn't get flagged for
    human review unnecessarily."""
    text = "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n(Về việc ban hành học phí)\n"
    result = _extract_title_from_header(text)
    assert result.confidence == 1.0
    assert result.needs_human_review is False
    assert result.rationale == "parenthetical-after-heading"


def test_heading_re_does_not_consume_opening_paren_on_next_line() -> None:
    """The heading-regex suffix was originally ``[\\s\\W_]{0,30}`` and would
    happily chew through ``\\n(`` on the next line. The fix uses
    ``[^\\w\\n]{0,30}`` so the heading match stays anchored to its own line
    and does NOT eat the opening parenthesis of the parenthetical that
    follows. Confirm by checking the heading match's ``end()`` is before
    the paren match's ``start()``.
    """
    text = "Số: 10232/QĐ-ĐHBK\n\nQUYẾT ĐỊNH\n(\nVề việc ban hành học phí\n)\n"
    heading = _HEADING_RE.search(text)
    paren = _PARENTHETICAL_TITLE_MULTILINE_RE.search(text)
    assert heading is not None
    assert paren is not None
    assert heading.end() <= paren.start(), (
        f"Heading match ({heading.end()=}) eats into paren match "
        f"({paren.start()=}); the heading match should end on its own line."
    )
