import asyncio
import sys
from datetime import date
from uuid import UUID

from config import get_settings
from domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from persistence.tenant.repositories.sqlalchemy_document_repository import (
    SqlAlchemyDocumentRepository,
)
from persistence.tenant.session_factory import (
    TenantSessionFactory,
)


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


async def main() -> None:
    settings = get_settings()

    factory = TenantSessionFactory()

    session = factory.create(
        settings.database_url
    )

    try:
        repository = (
            SqlAlchemyDocumentRepository(
                session
            )
        )

        document = await repository.get_by_id(
            UUID(
                "30000000-0000-0000-0000-000000000001"
            )
        )

        assert document is not None

        print("GET BY ID")
        print(
            document.document_number
        )

        documents = await repository.search(
            document_number="QCVN",
            legal_status=None,
            issued_from=None,
            issued_to=None,
            skip=0,
            limit=20,
        )

        print()
        print(
            "SEARCH QCVN:",
            len(documents),
        )

        effective_documents = (
            await repository.search(
                document_number=None,
                legal_status=(
                    DocumentLegalStatus
                    .DANG_HIEU_LUC
                ),
                issued_from=None,
                issued_to=None,
                skip=0,
                limit=20,
            )
        )

        print(
            "EFFECTIVE:",
            len(
                effective_documents
            ),
        )

        ranged = await repository.search(
            document_number=None,
            legal_status=None,
            issued_from=date(
                2022,
                1,
                1,
            ),
            issued_to=date(
                2024,
                12,
                31,
            ),
            skip=0,
            limit=20,
        )

        print(
            "DATE RANGE:",
            len(ranged),
        )

        duplicate = (
            await repository
            .exists_effective_number(
                "QCVN-06-2022-BXD"
            )
        )

        print(
            "DUPLICATE EFFECTIVE:",
            duplicate,
        )

        assert duplicate is True

        print()
        print(
            "A0-01 repository test PASS"
        )

    finally:
        await session.close()
        await factory.dispose()


asyncio.run(main())