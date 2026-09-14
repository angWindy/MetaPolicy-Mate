"""Tests for the heuristic document-number extractor and pipeline integration."""

from __future__ import annotations

import pytest

from src.domain.schemas import DocumentMetadata, ParsedBlock
from src.ingestion.document_number import (
    AUTO_DETECT_SENTINEL,
    DocumentNumberProbe,
    extract_document_number,
)
from src.ingestion.pipeline import IngestionPipeline


class TestExtractDocumentNumber:
    def test_single_candidate_in_header_returns_full_confidence(self):
        text = (
            "Số: 10232/QĐ-ĐHBK\n"
            "\n"
            "ĐẠI HỌC BÁCH KHOA HÀ NỘI\n"
            "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
            "\n"
            "Quyết định số 10232/QĐ-ĐHBK về việc ban hành quy chế."
        )
        probe = extract_document_number(text)
        assert probe.recommended == "10232/QĐ-ĐHBK"
        assert probe.confidence == pytest.approx(1.0)
        assert probe.needs_human_review is False
        assert probe.candidates == ("10232/QĐ-ĐHBK",)

    def test_single_candidate_without_header_flagged_for_review(self):
        text = "Căn cứ Quyết định số 10232/QĐ-ĐHBK ban hành ngày 01/08/2026."
        probe = extract_document_number(text)
        assert probe.recommended == "10232/QĐ-ĐHBK"
        assert probe.needs_human_review is True
        assert probe.confidence < 1.0

    def test_multiple_candidates_top_ranked_but_review_required(self):
        text = (
            "Căn cứ Quyết định số 10232/QĐ-ĐHBK và Thông báo số 1234/TB-ĐHBK "
            "về việc tổ chức kỳ thi."
        )
        probe = extract_document_number(text)
        assert probe.candidates == ("10232/QĐ-ĐHBK", "1234/TB-ĐHBK")
        assert probe.recommended == "10232/QĐ-ĐHBK"
        assert probe.needs_human_review is True
        assert probe.confidence == pytest.approx(0.5, abs=0.05)

    def test_no_match_marks_review_required_and_recommends_none(self):
        text = "Văn bản này không chứa số hiệu hợp lệ theo mẫu NNN/XYZ-ABC."
        probe = extract_document_number(text)
        assert probe.candidates == ()
        assert probe.recommended is None
        assert probe.needs_human_review is True
        assert probe.confidence == 0.0

    def test_empty_text_is_safe(self):
        probe = extract_document_number("")
        assert probe.matched is False
        assert probe.needs_human_review is True

    def test_ocr_style_header_supported(self):
        text = "Số hiệu: 456/CV-ABC\nNgày 02/08/2026\n\nNội dung công văn ..."
        probe = extract_document_number(text)
        assert probe.recommended == "456/CV-ABC"
        assert probe.needs_human_review is False

    def test_probe_payload_shape(self):
        probe = extract_document_number("Số: 10232/QĐ-ĐHBK\nNội dung ...")
        assert isinstance(probe, DocumentNumberProbe)
        assert isinstance(probe.candidates, tuple)
        assert all(isinstance(candidate, str) for candidate in probe.candidates)
        assert isinstance(probe.matched_pages, dict)


class TestPipelineResolution:
    @staticmethod
    def _make_blocks() -> list[ParsedBlock]:
        return [
            ParsedBlock.from_native_text(
                "Số: 10232/QĐ-ĐHBK\n\nĐẠI HỌC BÁCH KHOA HÀ NỘI\n\nNội dung ...",
                page=1,
                block_index=0,
            ),
            ParsedBlock.from_native_text(
                "Điều 1. Phạm vi điều chỉnh\nVăn bản này ...",
                page=1,
                block_index=1,
            ),
        ]

    def test_caller_supplied_value_is_preserved(self):
        meta = DocumentMetadata(
            title="Quy định",
            document_number="10232/QĐ-ĐHBK",
            owner_department="TCCB",
        )
        blocks = self._make_blocks()
        resolved, probe, warnings = IngestionPipeline._resolve_document_number(meta, blocks)
        assert resolved.document_number == "10232/QĐ-ĐHBK"
        assert probe is None
        assert warnings == []

    def test_auto_detect_sentinel_triggers_probe(self):
        meta = DocumentMetadata(
            title="Quy định",
            document_number=AUTO_DETECT_SENTINEL,
            owner_department="TCCB",
        )
        blocks = self._make_blocks()
        resolved, probe, warnings = IngestionPipeline._resolve_document_number(meta, blocks)
        assert probe is not None
        assert probe.recommended == "10232/QĐ-ĐHBK"
        assert resolved.document_number == "10232/QĐ-ĐHBK"
        # Even when confident, the persistent record on DocumentVersion.metadata_json
        # keeps an audit trail; warnings are only added when the extractor is
        # not fully sure so reviewers actually see the message they need to act on.
        assert probe.candidates == ("10232/QĐ-ĐHBK",)

    def test_auto_detect_sentinel_uncertain_match_emits_review_warning(self):
        meta = DocumentMetadata(
            title="Quy định",
            document_number=AUTO_DETECT_SENTINEL,
            owner_department="TCCB",
        )
        blocks = [
            ParsedBlock.from_native_text(
                "Căn cứ Quyết định số 10232/QĐ-ĐHBK ban hành ngày 01/08/2026.",
                page=1,
                block_index=0,
            )
        ]
        resolved, probe, warnings = IngestionPipeline._resolve_document_number(meta, blocks)
        assert probe is not None
        assert probe.recommended == "10232/QĐ-ĐHBK"
        assert probe.needs_human_review is True
        assert resolved.document_number == "10232/QĐ-ĐHBK"
        assert any("10232/QĐ-ĐHBK" in w and "REVIEW_REQUIRED" in w for w in warnings)

    def test_auto_detect_sentinel_no_match_keeps_sentinel_and_warns(self):
        meta = DocumentMetadata(
            title="Quy định",
            document_number=AUTO_DETECT_SENTINEL,
            owner_department="TCCB",
        )
        blocks = [
            ParsedBlock.from_native_text(
                "Văn bản này không có số hiệu hợp lệ.",
                page=1,
                block_index=0,
            )
        ]
        resolved, probe, warnings = IngestionPipeline._resolve_document_number(meta, blocks)
        # We keep the sentinel so the unique constraint error tells the user
        # exactly which field to fill in, instead of silently inventing a value.
        assert resolved.document_number == AUTO_DETECT_SENTINEL
        assert probe is not None
        assert probe.recommended is None
        assert any("Không tự trích xuất" in w for w in warnings)
