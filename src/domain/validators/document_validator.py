"""Document number validator.

Allowed formats:
- Pure number: ``123``
- Number + type + code: ``123/QD-DHBK`` or ``1/CV-ABC-XYZ``
"""
import re
from typing import Final

# Pattern is anchored so partial matches do not pass.
DOCUMENT_NUMBER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(\d+|\d+/[A-Z\u00C0-\u0179\u01A0\u01AF\u1E80-\u1EFF\u0300\u0303\u0309\u0323\u0301\u0302\u0306\u031B"
    r"0-9]+(?:-[A-Z\u00C0-\u0179\u01A0\u01AF\u1E80-\u1EFF\u0300\u0303\u0309\u0323\u0301\u0302\u0306\u031B"
    r"0-9]+)*)$",
    flags=re.IGNORECASE,
)


def validate_document_number(value: str) -> bool:
    """Return True if the value matches an allowed document number format."""
    if not value:
        return False
    cleaned = value.strip()
    if not cleaned:
        return False
    return bool(DOCUMENT_NUMBER_PATTERN.match(cleaned))


def validate_issued_by(value: str | None) -> bool:
    """Return True if issued_by is a non-empty string."""
    if value is None:
        return False
    return bool(value.strip())


def validate_required_metadata(
    *,
    document_number: str,
    issued_by: str | None,
    issued_date,
    effective_date,
) -> list[str]:
    """Validate required metadata fields.

    Returns a list of human-readable errors. Empty list means OK.
    """
    errors: list[str] = []
    if not validate_document_number(document_number):
        errors.append(
            "Số hiệu văn bản không đúng định dạng. "
            "Định dạng hợp lệ: '123' hoặc '123/QĐ-ĐHBK'."
        )
    if not validate_issued_by(issued_by):
        errors.append(
            "Cơ quan ban hành không được để trống."
        )
    if issued_date is None:
        errors.append("Ngày ban hành không được để trống.")
    if effective_date is None:
        errors.append("Ngày có hiệu lực không được để trống.")
    if (
        issued_date is not None
        and effective_date is not None
        and effective_date < issued_date
    ):
        errors.append(
            "Ngày có hiệu lực phải sau hoặc bằng ngày ban hành."
        )
    return errors


def needs_review(
    *,
    document_number: str,
    issued_by: str | None,
    issued_date,
    effective_date,
) -> bool:
    """Determine whether the document should be auto-flagged for review."""
    errors = validate_required_metadata(
        document_number=document_number,
        issued_by=issued_by,
        issued_date=issued_date,
        effective_date=effective_date,
    )
    return len(errors) > 0
