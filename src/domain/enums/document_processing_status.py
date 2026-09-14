"""DEPRECATED — kept for backwards compatibility.

The canonical processing-status enum now lives in
``src.domain.schemas.ProcessingStatus`` (English lowercase values). This
module re-exports it and exposes the historical Vietnamese names as
top-level constants so any existing imports keep working during the
migration. New code MUST import ``ProcessingStatus`` from
``src.domain.schemas`` directly.

Mapping (Vietnamese legacy → English canonical):

* ``CHO_XU_LY_NOI_DUNG`` → ``ProcessingStatus.RECEIVED``
* ``DANG_SO_HOA``         → ``ProcessingStatus.PARSED``
* ``DA_SO_HOA``           → ``ProcessingStatus.INDEXED``
* ``SO_HOA_THAT_BAI``     → ``ProcessingStatus.FAILED``
"""

from src.domain.schemas import ProcessingStatus


# Backwards-compatible aliases for legacy Vietnamese member names.
CHO_XU_LY_NOI_DUNG = ProcessingStatus.RECEIVED
DANG_SO_HOA = ProcessingStatus.PARSED
DA_SO_HOA = ProcessingStatus.INDEXED
SO_HOA_THAT_BAI = ProcessingStatus.FAILED


# Backwards-compatible alias of the *class itself* so that legacy imports
# like ``from src.domain.enums.document_processing_status import
# DocumentProcessingStatus`` continue to work. The returned object is
# simply the canonical ``ProcessingStatus``.
DocumentProcessingStatus = ProcessingStatus


__all__ = [
    "ProcessingStatus",
    "DocumentProcessingStatus",
    "CHO_XU_LY_NOI_DUNG",
    "DANG_SO_HOA",
    "DA_SO_HOA",
    "SO_HOA_THAT_BAI",
]
