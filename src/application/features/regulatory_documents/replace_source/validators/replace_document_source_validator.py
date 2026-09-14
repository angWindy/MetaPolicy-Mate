from src.application.features.regulatory_documents.replace_source.replace_document_source_command import (
    ReplaceDocumentSourceCommand,
)
from src.shared.validation_error import ValidationError


class ReplaceDocumentSourceValidator:
    def validate(
        self,
        request: ReplaceDocumentSourceCommand,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

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