from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol


@dataclass(frozen=True)
class DigitizedSection:
    section_type: str | None

    section_number: str | None

    heading: str | None

    heading_path: list[str]

    content: str

    page: int | None

    sort_order: int


@dataclass(frozen=True)
class DigitizedChunk:
    id: str

    chunk_index: int

    text: str

    embedding_text: str

    section_index: int | None

    metadata: dict


@dataclass(frozen=True)
class DigitizationResult:
    sections: list[
        DigitizedSection
    ]

    chunks: list[
        DigitizedChunk
    ]

    warnings: list[str]


class DocumentDigitizationService(
    Protocol
):
    async def digitize(
        self,
        *,
        document_id: str,
        version_id: str,

        filename: str,
        content: bytes,

        document_number: str,
        title: str,
        issued_by: str,

        issued_date: date,
        effective_date: date,

        version_number: int,

        # OCR engine override: "rapidocr_vi" (RapidOCR + PP-OCRv6
        # Vietnamese ONNX, default) or "pp_structure" (PP-StructureV3
        # layout-aware pipeline, opt-in for tables).
        ocr_engine: Literal["rapidocr_vi", "pp_structure"] = "rapidocr_vi",
    ) -> DigitizationResult:
        ...