from enum import Enum


class DocumentMetadataDraftStatus(
    str,
    Enum,
):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"