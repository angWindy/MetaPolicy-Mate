from src.application.features.regulatory_documents.changelog.get_list.get_document_changelog_query import (
    GetDocumentChangelogQuery,
)
from src.shared.validation_error import (
    ValidationError,
)


class GetDocumentChangelogValidator:
    def validate(
        self,
        request: GetDocumentChangelogQuery,
    ) -> list[ValidationError]:
        errors: list[
            ValidationError
        ] = []

        if (
            request.from_at is not None
            and request.to_at is not None
            and request.from_at
            > request.to_at
        ):
            errors.append(
                ValidationError(
                    property_name=(
                        "from_at"
                    ),
                    error_message=(
                        "from_at must be "
                        "less than or equal "
                        "to to_at."
                    ),
                )
            )

        return errors