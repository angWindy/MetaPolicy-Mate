from fastapi import APIRouter

from src.presentation.api.routers.auth_router import (
    router as auth_router,
)
from src.presentation.api.routers.regulatory_document_router import (
    router as regulatory_document_router,
)

from src.presentation.api.routers.document_effectiveness_alert_router import (
    router as document_effectiveness_alert_router,
)

from src.presentation.api.routers.user_router import (
    router as user_router,
)

from src.presentation.api.routers.role_router import (
    router as role_router,
)

from src.presentation.api.routers.rbac_router import (
    router as rbac_router,
)

from src.presentation.api.routers.department_router import (
    router as department_router,
)

from src.presentation.api.routers.document_section_router import (
    router as document_section_router,
)
from src.presentation.api.routers.static_threshold_router import (
    router as static_threshold_router,
)
from src.presentation.api.routers.retrieval_router import (
    router as retrieval_router,
)
from src.presentation.api.routers.document_section_metadata_router import (
    router as document_section_metadata_router,
)

from src.presentation.api.routers.activity_log_router import (
    router as activity_log_router,
)

from src.presentation.api.routers.admin_router import (
    router as admin_router,
)

from src.presentation.api.routers.chat_router import (
    router as chat_router,
)

from src.presentation.api.routers.system_evaluation_router import (
    router as system_evaluation_router,
)

from src.presentation.api.routers.saved_documents_router import (
    router as saved_documents_router,
)

from src.presentation.api.routers.notification_router import (
    router as notification_router,
)

api_router = APIRouter()

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["Auth"],
)

api_router.include_router(
    regulatory_document_router,
    prefix="/regulatory-documents",
    tags=["Regulatory Documents"],
)

api_router.include_router(
    document_effectiveness_alert_router,
    prefix="/document-effectiveness-alerts",
    tags=["Document Effectiveness Alerts"],
)

api_router.include_router(
    user_router,
    prefix="/users",
    tags=["Users"],
)

api_router.include_router(
    role_router,
    prefix="/roles",
    tags=["Roles"],
)

api_router.include_router(
    rbac_router,
    prefix="/rbac",
    tags=["RBAC"],
)

api_router.include_router(
    department_router,
    prefix="/departments",
    tags=["Departments"],
)

api_router.include_router(
    document_section_router,
    prefix="/document-sections",
    tags=["Document Sections"],
)

api_router.include_router(
    static_threshold_router,
    prefix="/static-thresholds",
    tags=["Static Thresholds"],
)

api_router.include_router(
    retrieval_router,
    prefix="/retrieval",
    tags=["Retrieval"],
)

api_router.include_router(
    document_section_metadata_router,
    prefix="/document-section-metadata",
    tags=["Document Section Metadata"],
)

api_router.include_router(
    activity_log_router,
    prefix="/activity-logs",
    tags=["Activity Logs"],
)

api_router.include_router(
    admin_router,
    prefix="/admin",
    tags=["Admin"],
)

api_router.include_router(
    chat_router,
    prefix="/chat",
    tags=["Chat"],
)

api_router.include_router(
    system_evaluation_router,
    prefix="/system-evaluation",
    tags=["System Evaluation"],
)

api_router.include_router(
    saved_documents_router,
    prefix="/saved-documents",
    tags=["Saved Documents"],
)

api_router.include_router(
    notification_router,
    prefix="/notifications",
    tags=["Notifications"],
)