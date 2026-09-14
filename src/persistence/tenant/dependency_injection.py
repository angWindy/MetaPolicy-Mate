from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.application.common.interfaces.audit_service import (
    AuditService as AuditServiceProtocol,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.domain.repositories.permission_repository import (
    PermissionRepository,
)
from src.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_permission_repository import (
    SqlAlchemyPermissionRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_role_repository import (
    SqlAlchemyRoleRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from src.persistence.tenant.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from src.infrastructure.audit.audit_service import (
    AuditService,
)

from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_document_repository import (
    SqlAlchemyDocumentRepository,
)

from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_document_version_repository import (
    SqlAlchemyDocumentVersionRepository,
)

from src.domain.repositories.document_relation_repository import (
    DocumentRelationRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_document_relation_repository import (
    SqlAlchemyDocumentRelationRepository,
)

from src.domain.repositories.document_effectiveness_alert_repository import (
    DocumentEffectivenessAlertRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_document_effectiveness_alert_repository import (
    SqlAlchemyDocumentEffectivenessAlertRepository,
)

from src.domain.repositories.document_application_scope_repository import (
    DocumentApplicationScopeRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_document_application_scope_repository import (
    SqlAlchemyDocumentApplicationScopeRepository,
)

from src.domain.repositories.document_changelog_repository import (
    DocumentChangelogRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_document_changelog_repository import (
    SqlAlchemyDocumentChangelogRepository,
)

from src.application.common.interfaces.activity_log_service import (
    ActivityLogService as ActivityLogServiceProtocol,
)

from src.infrastructure.activity.activity_log_service import (
    ActivityLogService,
)

from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_department_repository import (
    SqlAlchemyDepartmentRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_document_department_repository import (
    SqlAlchemyDocumentDepartmentRepository,
)
from src.domain.repositories.user_activity_log_repository import (
    UserActivityLogRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_user_activity_log_repository import (
    SqlAlchemyUserActivityLogRepository,
)

from src.application.common.interfaces.document_digitization_service import (
    DocumentDigitizationService,
)

from src.domain.repositories.document_digitization_repository import (
    DocumentDigitizationRepository,
)

from src.infrastructure.ai.document_digitization_service import (
    AiDocumentDigitizationService,
)

from src.persistence.tenant.repositories.sqlalchemy_document_digitization_repository import (
    SqlAlchemyDocumentDigitizationRepository,
)

from src.application.common.interfaces.document_metadata_extraction_service import (
    DocumentMetadataExtractionService,
)

from src.infrastructure.ai.document_metadata_extraction_service import (
    AiDocumentMetadataExtractionService,
)
from src.domain.repositories.document_section_repository import (
    DocumentSectionRepository,
)
from src.domain.repositories.document_section_version_repository import (
    DocumentSectionVersionRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_document_section_repository import (
    SqlAlchemyDocumentSectionRepository,
)
from src.persistence.tenant.repositories.sqlalchemy_document_section_version_repository import (
    SqlAlchemyDocumentSectionVersionRepository,
)
from src.domain.repositories.static_threshold_repository import (
    StaticThresholdRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_static_threshold_repository import (
    SqlAlchemyStaticThresholdRepository,
)

from src.application.common.interfaces.hybrid_retrieval_service import (
    HybridRetrievalService,
)

from src.infrastructure.ai.hybrid_retrieval_service import (
    AiHybridRetrievalService,
)

from src.application.common.interfaces.section_metadata_extraction_service import (
    SectionMetadataExtractionService,
)

from src.domain.repositories.document_section_metadata_draft_repository import (
    DocumentSectionMetadataDraftRepository,
)

from src.infrastructure.ai.section_metadata_extraction_service import (
    AiSectionMetadataExtractionService,
)

from src.persistence.tenant.repositories.sqlalchemy_document_section_metadata_draft_repository import (
    SqlAlchemyDocumentSectionMetadataDraftRepository,
)

from src.application.common.interfaces.rag_index_service import (
    RagIndexService,
)

from src.infrastructure.ai.rag_index_service import (
    AiRagIndexService,
)

from src.application.common.interfaces.rag_chat_service import (
    RagChatService,
)

from src.infrastructure.ai.rag_chat_service import (
    AiRagChatService,
)

from src.domain.repositories.chat_repository import (
    ChatRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_chat_repository import (
    SqlAlchemyChatRepository,
)

from src.domain.repositories.answer_feedback_repository import (
    AnswerFeedbackRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_answer_feedback_repository import (
    SqlAlchemyAnswerFeedbackRepository,
)

from src.domain.repositories.saved_document_repository import (
    SavedDocumentRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_saved_document_repository import (
    SqlAlchemySavedDocumentRepository,
)

from src.domain.repositories.notification_repository import (
    NotificationRepository,
)

from src.persistence.tenant.repositories.sqlalchemy_notification_repository import (
    SqlAlchemyNotificationRepository,
)

def add_tenant_persistence(
    container,
    session: AsyncSession,
) -> None:
    container.register_instance(
        AsyncSession,
        session,
    )

    container.register_scoped(
        UserRepository,
        SqlAlchemyUserRepository,
    )

    container.register_scoped(
        RoleRepository,
        SqlAlchemyRoleRepository,
    )

    container.register_scoped(
        PermissionRepository,
        SqlAlchemyPermissionRepository,
    )

    container.register_scoped(
        RefreshTokenRepository,
        SqlAlchemyRefreshTokenRepository,
    )

    container.register_scoped(
        UnitOfWork,
        SqlAlchemyUnitOfWork,
    )

    container.register_scoped(
        AuditServiceProtocol,
        AuditService,
    )

    container.register_scoped(
        ActivityLogServiceProtocol,
        ActivityLogService,
    )

    container.register_scoped(
        DocumentRepository,
        SqlAlchemyDocumentRepository,
    )

    container.register_scoped(
        DocumentVersionRepository,
        SqlAlchemyDocumentVersionRepository,
    )

    container.register_scoped(
        DocumentRelationRepository,
        SqlAlchemyDocumentRelationRepository,
    )

    container.register_scoped(
        DocumentEffectivenessAlertRepository,
        SqlAlchemyDocumentEffectivenessAlertRepository,
    )

    container.register_scoped(
        DocumentApplicationScopeRepository,
        SqlAlchemyDocumentApplicationScopeRepository,
    )

    container.register_scoped(
        DocumentChangelogRepository,
        SqlAlchemyDocumentChangelogRepository,
    )

    container.register_scoped(
        DepartmentRepository,
        SqlAlchemyDepartmentRepository,
    )

    container.register_scoped(
        DocumentDepartmentRepository,
        SqlAlchemyDocumentDepartmentRepository,
    )

    container.register_scoped(
        UserActivityLogRepository,
        SqlAlchemyUserActivityLogRepository,
    )

    container.register_scoped(
        DocumentDigitizationRepository,
        SqlAlchemyDocumentDigitizationRepository,
    )

    container.register_scoped(
        RagIndexService,
        AiRagIndexService,
    )

    container.register_scoped(
        DocumentDigitizationService,
        AiDocumentDigitizationService,
    )

    container.register_scoped(
        DocumentMetadataExtractionService,
        AiDocumentMetadataExtractionService,
    )

    container.register_scoped(
        DocumentSectionRepository,
        SqlAlchemyDocumentSectionRepository,
    )

    container.register_scoped(
        DocumentSectionVersionRepository,
        SqlAlchemyDocumentSectionVersionRepository,
    )

    container.register_scoped(
        StaticThresholdRepository,
        SqlAlchemyStaticThresholdRepository,
    )

    container.register_scoped(
        HybridRetrievalService,
        AiHybridRetrievalService,
    )

    container.register_scoped(
        DocumentSectionMetadataDraftRepository,
        SqlAlchemyDocumentSectionMetadataDraftRepository,
    )

    container.register_scoped(
        SectionMetadataExtractionService,
        AiSectionMetadataExtractionService,
    )

    container.register_scoped(
        ChatRepository,
        SqlAlchemyChatRepository,
    )

    container.register_scoped(
        RagChatService,
        AiRagChatService,
    )

    container.register_scoped(
        AnswerFeedbackRepository,
        SqlAlchemyAnswerFeedbackRepository,
    )

    container.register_scoped(
        SavedDocumentRepository,
        SqlAlchemySavedDocumentRepository,
    )

    container.register_scoped(
        NotificationRepository,
        SqlAlchemyNotificationRepository,
    )