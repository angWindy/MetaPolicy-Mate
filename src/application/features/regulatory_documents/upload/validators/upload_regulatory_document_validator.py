from src.application.features.regulatory_documents.upload.upload_regulatory_document_command import (
    UploadRegulatoryDocumentCommand,
)
from src.shared.validation_error import ValidationError


class UploadRegulatoryDocumentValidator:
    def validate(
        self,
        request: UploadRegulatoryDocumentCommand,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        if not request.document_number.strip():
            errors.append(
                ValidationError(
                    property_name="document_number",
                    error_message=(
                        "Document number is required."
                    ),
                )
            )

        if not request.content:
            errors.append(
                ValidationError(
                    property_name="content",
                    error_message=(
                        "Source file is required."
                    ),
                )
            )
            return errors

        if not request.source_filename.lower().endswith(
            ".pdf"
        ):
            errors.append(
                ValidationError(
                    property_name="source_filename",
                    error_message=(
                        "Source file must have a .pdf extension."
                    ),
                )
            )

        if request.content_type != "application/pdf":
            errors.append(
                ValidationError(
                    property_name="content_type",
                    error_message=(
                        "Source file must be a PDF."
                    ),
                )
            )

        if not request.content.startswith(b"%PDF-"):
            errors.append(
                ValidationError(
                    property_name="content",
                    error_message="Invalid PDF file.",
                )
            )

        return errors