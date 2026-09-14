import asyncio
import sys
from datetime import date
from uuid import UUID

from application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher as RequestDispatcherProtocol,
)
from application.dependency_injections.dependency_injection import (
    add_application,
)
from application.features.regulatory_documents.get_detail.get_regulatory_document_query import (
    GetRegulatoryDocumentQuery,
)
from application.features.regulatory_documents.get_list.get_regulatory_documents_query import (
    GetRegulatoryDocumentsQuery,
)
from application.features.regulatory_documents.update.update_regulatory_document_command import (
    UpdateRegulatoryDocumentCommand,
)
from config import get_settings
from domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from infrastructure.dependency_injection.dependency_injection import (
    add_infrastructure,
)
from infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from persistence.tenant.dependency_injection import (
    add_tenant_persistence,
)
from persistence.tenant.session_factory import (
    TenantSessionFactory,
)


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


DOCUMENT_ID = UUID(
    "30000000-0000-0000-0000-000000000001"
)


async def main() -> None:
    settings = get_settings()

    session_factory = TenantSessionFactory()

    session = session_factory.create(
        settings.database_url
    )

    try:
        container = ServiceContainer()

        add_application(
            container
        )

        add_infrastructure(
            container,
            settings,
        )

        add_tenant_persistence(
            container,
            session,
        )

        dispatcher = container.get_required(
            RequestDispatcherProtocol
        )

        print("GET LIST")

        list_result = await dispatcher.send(
            GetRegulatoryDocumentsQuery(
                document_number="QCVN",
                legal_status=None,
                issued_from=None,
                issued_to=None,
                page=1,
                page_size=20,
            )
        )

        print(
            "Total:",
            list_result.total,
        )

        for item in list_result.items:
            print(
                "-",
                item.document_number,
            )

        if list_result.total < 1:
            raise RuntimeError(
                "Expected at least one QCVN document."
            )

        print()
        print("GET DETAIL")

        detail = await dispatcher.send(
            GetRegulatoryDocumentQuery(
                document_id=DOCUMENT_ID
            )
        )

        print(
            "Number:",
            detail.document_number,
        )

        print(
            "Status:",
            detail.legal_status.value,
        )

        if (
            detail.document_number
            != "QCVN-06-2022-BXD"
        ):
            raise RuntimeError(
                "Unexpected document detail."
            )

        original_title = detail.title

        print()
        print("UPDATE")

        updated = await dispatcher.send(
            UpdateRegulatoryDocumentCommand(
                document_id=DOCUMENT_ID,
                document_number=(
                    detail.document_number
                ),
                title=(
                    "A0-01 Dispatcher Test Title"
                ),
                issued_by=detail.issued_by,
                issued_date=detail.issued_date,
                effective_date=(
                    detail.effective_date
                ),
            )
        )

        print(
            "Updated title:",
            updated.title,
        )

        print(
            "Status preserved:",
            updated.legal_status.value,
        )

        if (
            updated.title
            != "A0-01 Dispatcher Test Title"
        ):
            raise RuntimeError(
                "Update did not persist."
            )

        if (
            updated.legal_status
            != DocumentLegalStatus
            .DANG_HIEU_LUC
        ):
            raise RuntimeError(
                "A0-01 must not modify legal status."
            )

        print()
        print("VERIFY DB")

        verified = await dispatcher.send(
            GetRegulatoryDocumentQuery(
                document_id=DOCUMENT_ID
            )
        )

        print(
            "Stored title:",
            verified.title,
        )

        if (
            verified.title
            != "A0-01 Dispatcher Test Title"
        ):
            raise RuntimeError(
                "Updated metadata was not persisted."
            )

        print()
        print("RESTORE TITLE")

        await dispatcher.send(
            UpdateRegulatoryDocumentCommand(
                document_id=DOCUMENT_ID,
                document_number=(
                    verified.document_number
                ),
                title=original_title,
                issued_by=verified.issued_by,
                issued_date=verified.issued_date,
                effective_date=(
                    verified.effective_date
                ),
            )
        )

        print(
            "Original title restored."
        )

        print()
        print(
            "A0-01 Dispatcher integration test PASS"
        )

    finally:
        await session.close()
        await session_factory.dispose()


asyncio.run(main())