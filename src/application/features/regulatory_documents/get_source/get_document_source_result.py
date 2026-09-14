from dataclasses import dataclass


@dataclass(frozen=True)
class GetDocumentSourceResult:
    content: bytes
    content_type: str
    filename: str
