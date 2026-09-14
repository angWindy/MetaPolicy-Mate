import asyncio
import sys
from datetime import date
from pathlib import Path

# Allow ``from scripts._seed_ids import ...`` when the script is
# invoked directly (the helper lives under scripts/).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from application.common.interfaces.request_context import (
    RequestContext as RequestContextProtocol,
)
from application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher as RequestDispatcherProtocol,
)
from application.dependency_injections.dependency_injection import (
    add_application,
)
from application.features.regulatory_documents.replace_source.replace_document_source_command import (
    ReplaceDocumentSourceCommand,
)
from application.features.regulatory_documents.upload.upload_regulatory_document_command import (
    UploadRegulatoryDocumentCommand,
)
from config import get_settings
from domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from domain.enums.document_processing_status import (
    DocumentProcessingStatus,
)
from domain.repositories.document_repository import (
    DocumentRepository,
)
from domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from infrastructure.dependency_injection.dependency_injection import (
    add_infrastructure,
)
from infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from infrastructure.services.request_context import (
    RequestContext,
)
from persistence.tenant.dependency_injection import (
    add_tenant_persistence,
)
from persistence.tenant.session_factory import (
    TenantSessionFactory,
)

# Demo user UUIDs are derived from the user's email via UUIDv5 (see
# scripts/_seed_ids.py for the stability contract).
from scripts._seed_ids import seed_user_id


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


async def main() -> None:
    settings = get_settings()

    # Đổi 2 path này thành 2 PDF thật bạn đang có.
    pdf_1_path = Path(
        "data/test/a0_02_source_v1.pdf"
    )

    pdf_2_path = Path(
        "data/test/a0_02_source_v2.pdf"
    )

    if not pdf_1_path.exists():
        raise RuntimeError(
            f"Missing PDF: {pdf_1_path}"
        )

    if not pdf_2_path.exists():
        raise RuntimeError(
            f"Missing PDF: {pdf_2_path}"
        )

    pdf_1 = pdf_1_path.read_bytes()
    pdf_2 = pdf_2_path.read_bytes()

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

        request_context = RequestContext(
            claims={
                "sub": str(
                    seed_user_id("admin@p234.demo")
                ),
                "email": "admin@p234.demo",
                "userType": "1",
                "SchoolId": str(
                    settings.school_id
                ),
            },
            headers={
                "x-device-id": (
                    "a0-02-dispatcher-test"
                )
            },
            ip_address="127.0.0.1",
            trace_id=(
                "a0-02-dispatcher-test"
            ),
        )

        container.register_instance(
            RequestContextProtocol,
            request_context,
        )

        dispatcher = container.get_required(
            RequestDispatcherProtocol
        )

        document_repository = (
            container.get_required(
                DocumentRepository
            )
        )

        version_repository = (
            container.get_required(
                DocumentVersionRepository
            )
        )

        print("UPLOAD NEW DOCUMENT")

        upload_result = await dispatcher.send(
            UploadRegulatoryDocumentCommand(
                document_number=(
                    "QCVN-A002-DISPATCHER-TEST"
                ),
                title=(
                    "A0-02 Dispatcher Test"
                ),
                issued_by=(
                    "Demo Authority"
                ),
                issued_date=date(
                    2026,
                    8,
                    18,
                ),
                effective_date=date(
                    2026,
                    9,
                    1,
                ),
                source_filename=(
                    pdf_1_path.name
                ),
                content_type=(
                    "application/pdf"
                ),
                content=pdf_1,
            )
        )

        print(
            "Document ID:",
            upload_result.id,
        )

        print(
            "Document number:",
            upload_result.document_number,
        )

        print(
            "Legal status:",
            upload_result.legal_status.value,
        )

        if (
            upload_result.legal_status
            != DocumentLegalStatus
            .CHO_XU_LY_NOI_DUNG
        ):
            raise RuntimeError(
                "Unexpected document legal status."
            )

        print()
        print("VERIFY VERSION 1")

        version_1 = (
            await version_repository
            .get_latest_by_document_id(
                upload_result.id
            )
        )

        if version_1 is None:
            raise RuntimeError(
                "Version 1 was not created."
            )

        print(
            "Version:",
            version_1.version_number,
        )

        print(
            "Processing status:",
            version_1.processing_status.value,
        )

        print(
            "Object key:",
            version_1.object_key,
        )

        print(
            "Checksum:",
            version_1.checksum,
        )

        print(
            "Size:",
            version_1.size_bytes,
        )

        if version_1.version_number != 1:
            raise RuntimeError(
                "Expected version number 1."
            )

        if (
            version_1.processing_status
            != DocumentProcessingStatus
            .CHO_XU_LY_NOI_DUNG
        ):
            raise RuntimeError(
                "Unexpected processing status."
            )

        if (
            version_1.replaces_version_id
            is not None
        ):
            raise RuntimeError(
                "Version 1 must not replace another version."
            )

        print()
        print("REPLACE SOURCE")

        version_2 = await dispatcher.send(
            ReplaceDocumentSourceCommand(
                document_id=(
                    upload_result.id
                ),
                source_filename=(
                    pdf_2_path.name
                ),
                content_type=(
                    "application/pdf"
                ),
                content=pdf_2,
            )
        )

        print(
            "Version:",
            version_2.version_number,
        )

        print(
            "Version ID:",
            version_2.id,
        )

        print(
            "Replaces:",
            version_2.replaces_version_id,
        )

        print(
            "Object key:",
            version_2.object_key,
        )

        if version_2.version_number != 2:
            raise RuntimeError(
                "Expected version number 2."
            )

        if (
            version_2.replaces_version_id
            != version_1.id
        ):
            raise RuntimeError(
                "Version 2 does not replace version 1."
            )

        print()
        print("VERIFY LATEST VERSION")

        latest = (
            await version_repository
            .get_latest_by_document_id(
                upload_result.id
            )
        )

        if latest is None:
            raise RuntimeError(
                "Latest version not found."
            )

        print(
            "Latest:",
            latest.version_number,
        )

        if latest.id != version_2.id:
            raise RuntimeError(
                "Latest version is not version 2."
            )

        print()
        print("VERIFY DOCUMENT STILL EXISTS")

        document = (
            await document_repository
            .get_by_id(
                upload_result.id
            )
        )

        if document is None:
            raise RuntimeError(
                "Document disappeared after replace."
            )

        print(
            "Document:",
            document.document_number,
        )

        print()
        print(
            "A0-02 Dispatcher integration test PASS"
        )

    finally:
        await session.close()
        await session_factory.dispose()


asyncio.run(main())