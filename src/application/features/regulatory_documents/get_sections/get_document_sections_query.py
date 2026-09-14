from uuid import UUID


class GetDocumentSectionsQuery:
    def __init__(
        self,
        document_id: UUID,
    ) -> None:
        self.document_id = document_id
