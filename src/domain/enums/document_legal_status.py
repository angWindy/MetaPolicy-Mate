"""DEPRECATED — kept for backwards compatibility.

The canonical legal-status enum now lives in
``src.domain.schemas.LegalStatus`` (English lowercase values). This
module re-exports it and exposes the historical Vietnamese names as
top-level constants so any existing imports keep working during the
migration. New code MUST import ``LegalStatus`` from
``src.domain.schemas`` directly.

Mapping (Vietnamese legacy → English canonical):

* ``CHO_XU_LY_NOI_DUNG`` → ``LegalStatus.DRAFT``
* ``DANG_HIEU_LUC``      → ``LegalStatus.EFFECTIVE``
* ``BI_THAY_THE``        → ``LegalStatus.SUPERSEDED``
* ``HET_HIEU_LUC``       → ``LegalStatus.EXPIRED``
"""

from src.domain.schemas import LegalStatus


# Backwards-compatible aliases for legacy Vietnamese member names.
CHO_XU_LY_NOI_DUNG = LegalStatus.DRAFT
DANG_HIEU_LUC = LegalStatus.EFFECTIVE
BI_THAY_THE = LegalStatus.SUPERSEDED
HET_HIEU_LUC = LegalStatus.EXPIRED


# Backwards-compatible alias of the *class itself* so legacy imports keep
# working.
DocumentLegalStatus = LegalStatus


__all__ = [
    "LegalStatus",
    "DocumentLegalStatus",
    "CHO_XU_LY_NOI_DUNG",
    "DANG_HIEU_LUC",
    "BI_THAY_THE",
    "HET_HIEU_LUC",
]
