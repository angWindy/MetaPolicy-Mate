import pytest
from src.ingestion.file_validator import validate_upload
from src.ingestion.parser import DocumentParser, ParseError


def test_magic_bytes_valid_pdf():
    content = b"%PDF-1.5 fake pdf content here"
    res = validate_upload("document.pdf", content, max_upload_mb=10)
    assert res.valid is True
    assert res.error is None


def test_magic_bytes_invalid_pdf_forgery():
    content = b"this is plain text disguised as pdf"
    res = validate_upload("document.pdf", content, max_upload_mb=10)
    assert res.valid is False
    assert "Magic Bytes" in res.error


def test_magic_bytes_valid_docx():
    content = b"PK\x03\x04fake zip docx content"
    res = validate_upload("document.docx", content, max_upload_mb=10)
    assert res.valid is True
    assert res.error is None


def test_magic_bytes_invalid_docx_forgery():
    content = b"not a zip file"
    res = validate_upload("document.docx", content, max_upload_mb=10)
    assert res.valid is False
    assert "DOCX không hợp lệ" in res.error


def test_parser_parse_to_markdown_txt():
    parser = DocumentParser()
    txt_content = "Điều 1. Phạm vi điều chỉnh\nVăn bản này quy định về RAG pipeline.\n\nKhoản 1. Đối tượng áp dụng."
    md_text, warnings = parser.parse_to_markdown("quydinh.txt", txt_content.encode("utf-8"))
    assert "Điều 1" in md_text
    assert "Khoản 1" in md_text
