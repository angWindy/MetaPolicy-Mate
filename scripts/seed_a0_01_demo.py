import asyncio
import sys
from datetime import (
    date,
    datetime,
    timezone,
)
from uuid import UUID

from config import get_settings
from domain.entities.document import (
    Document,
)
from domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from persistence.tenant.repositories.sqlalchemy_document_repository import (
    SqlAlchemyDocumentRepository,
)
from persistence.tenant.session_factory import (
    TenantSessionFactory,
)
from persistence.tenant.unit_of_work import (
    SqlAlchemyUnitOfWork,
)


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


DOCUMENTS = [
    Document(
        id=UUID(
            "30000000-0000-0000-0000-000000000001"
        ),
        document_number="QCVN-06-2022-BXD",
        title=(
            "Quy chuẩn kỹ thuật quốc gia "
            "về an toàn cháy cho nhà "
            "và công trình"
        ),
        issued_by=(
            "Bộ Xây dựng"
        ),
        issued_date=date(
            2022,
            11,
            30,
        ),
        effective_date=date(
            2023,
            1,
            16,
        ),
        legal_status=(
            DocumentLegalStatus
            .DANG_HIEU_LUC
        ),
        created_at=(
            datetime.now(
                timezone.utc
            )
        ),
    ),
    Document(
        id=UUID(
            "30000000-0000-0000-0000-000000000002"
        ),
        document_number="TCVN-3890-2023",
        title=(
            "Phòng cháy chữa cháy - "
            "Phương tiện phòng cháy "
            "và chữa cháy cho nhà "
            "và công trình"
        ),
        issued_by=(
            "Bộ Khoa học và Công nghệ"
        ),
        issued_date=date(
            2023,
            1,
            1,
        ),
        effective_date=date(
            2023,
            1,
            1,
        ),
        legal_status=(
            DocumentLegalStatus
            .DANG_HIEU_LUC
        ),
        created_at=(
            datetime.now(
                timezone.utc
            )
        ),
    ),
    Document(
        id=UUID(
            "30000000-0000-0000-0000-000000000003"
        ),
        document_number="TCVN-DEMO-OLD",
        title="Demo replaced standard",
        issued_by="Demo",
        issued_date=date(
            2020,
            1,
            1,
        ),
        effective_date=date(
            2020,
            1,
            1,
        ),
        legal_status=(
            DocumentLegalStatus
            .BI_THAY_THE
        ),
        created_at=(
            datetime.now(
                timezone.utc
            )
        ),
    ),
]


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

        unit_of_work = (
            SqlAlchemyUnitOfWork(
                session
            )
        )

        for document in DOCUMENTS:
            existing = (
                await repository.get_by_id(
                    document.id
                )
            )

            if existing is None:
                await repository.add(
                    document
                )

        await unit_of_work.save_changes()

        print(
            "A0-01 seed completed."
        )

    finally:
        await session.close()
        await factory.dispose()


asyncio.run(main())