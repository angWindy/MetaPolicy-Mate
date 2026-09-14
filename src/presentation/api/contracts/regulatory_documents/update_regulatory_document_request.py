from datetime import date

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)


class UpdateRegulatoryDocumentRequest(
    BaseModel
):
    document_number: str = Field(
        min_length=1,
        max_length=100,
    )

    title: str = Field(
        min_length=1,
        max_length=500,
    )

    issued_by: str = Field(
        min_length=1,
        max_length=255,
    )

    issued_date: date
    effective_date: date

    # Không gửi thì giữ nguyên
    # trạng thái hiện tại.
    legal_status: (
        DocumentLegalStatus | None
    ) = None

    @model_validator(
        mode="after"
    )
    def _validate_date_order(
        self,
    ) -> "UpdateRegulatoryDocumentRequest":
        # B-P1-02: effective_date must be on or
        # after issued_date — otherwise the
        # document is "effective before it was
        # issued", which is logically impossible
        # and lets admins accidentally create
        # contradictory metadata.
        if (
            self.effective_date
            < self.issued_date
        ):
            raise ValueError(
                "effective_date must be on or "
                "after issued_date "
                f"(got issued_date="
                f"{self.issued_date.isoformat()}, "
                f"effective_date="
                f"{self.effective_date.isoformat()})."
            )
        return self