import hashlib
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


@dataclass
class FileValidationResult:
    valid: bool
    checksum: str
    extension: str
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def _check_magic_bytes(extension: str, content: bytes) -> str | None:
    """Verify file magic bytes / signature match the claimed extension."""
    if extension == ".pdf":
        if not content.startswith(b"%PDF"):
            return "Định dạng PDF không hợp lệ (Magic Bytes không khớp '%PDF'). Tệp có thể giả mạo hoặc bị hỏng."
    elif extension == ".docx":
        if not content.startswith(b"PK\x03\x04") and not content.startswith(b"PK\x05\x06"):
            return "Định dạng DOCX không hợp lệ (Không chứa cấu trúc Zip header PK). Tệp có thể giả mạo hoặc bị hỏng."
    elif extension == ".txt":
        # Check for binary content or null bytes in TXT
        if b"\x00" in content[:1024]:
            return "Định dạng TXT không hợp lệ (chứa dữ liệu nhị phân hoặc byte null)."
    return None


def validate_upload(filename: str, content: bytes, max_upload_mb: int) -> FileValidationResult:
    extension = Path(filename).suffix.lower()
    checksum = hashlib.sha256(content).hexdigest()

    if extension not in SUPPORTED_EXTENSIONS:
        return FileValidationResult(
            valid=False,
            checksum=checksum,
            extension=extension,
            error=f"Định dạng {extension or '(không xác định)'} chưa được hỗ trợ.",
        )
    if not content:
        return FileValidationResult(
            valid=False,
            checksum=checksum,
            extension=extension,
            error="Tệp rỗng.",
        )
    if len(content) > max_upload_mb * 1024 * 1024:
        return FileValidationResult(
            valid=False,
            checksum=checksum,
            extension=extension,
            error=f"Tệp vượt quá giới hạn {max_upload_mb} MB.",
        )

    magic_error = _check_magic_bytes(extension, content)
    if magic_error:
        return FileValidationResult(
            valid=False,
            checksum=checksum,
            extension=extension,
            error=magic_error,
        )

    return FileValidationResult(valid=True, checksum=checksum, extension=extension)

