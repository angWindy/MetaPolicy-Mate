from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

from src.application.common.exceptions.forbidden_exception import (
    ForbiddenException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.exceptions.request_validation_exception import (
    RequestValidationException,
)
from src.application.common.interfaces.rag_chat_service import (
    RagChatActor,
    RagChatService,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.chat.ask.ask_question_command import (
    AskQuestionCommand,
    AskQuestionResult,
)
from src.application.features.chat.ask.conversation_memory import (
    build_conversation_memory,
)

from src.domain.entities.chat_session import (
    ChatSession,
)
from src.domain.entities.chat_turn import (
    ChatTurn,
)
from src.domain.repositories.chat_repository import (
    ChatRepository,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)

from src.shared.validation_error import (
    ValidationError,
)

from src.application.common.document_access_policy import (
    citations_are_accessible,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class AskQuestionHandler(
    RequestHandler[
        AskQuestionCommand,
        AskQuestionResult,
    ]
):
    def __init__(
        self,
        chat_repository: ChatRepository,
        user_repository: UserRepository,
        department_repository: (
            DepartmentRepository
        ),
        role_repository: RoleRepository,
        rag_chat_service: RagChatService,
        document_repository: (
            DocumentRepository
        ),
        document_department_repository: (
            DocumentDepartmentRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._chat_repository = (
            chat_repository
        )

        self._user_repository = (
            user_repository
        )

        self._department_repository = (
            department_repository
        )

        self._role_repository = (
            role_repository
        )

        self._rag_chat_service = (
            rag_chat_service
        )

        self._document_repository = (
            document_repository
        )

        self._document_department_repository = (
            document_department_repository
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: AskQuestionCommand,
    ) -> AskQuestionResult:
        message = (
            request.message
            .strip()
        )

        if not message:
            raise (
                RequestValidationException(
                    [
                        ValidationError(
                            property_name=(
                                "message"
                            ),
                            error_message=(
                                "Message is "
                                "required."
                            ),
                        )
                    ]
                )
            )

        user = await (
            self._user_repository
            .get_by_id(
                request.user_id
            )
        )

        if user is None:
            raise NotFoundException(
                "User not found."
            )
        
        department_code = (
            ""
        )

        if (
            user.department_id
            is not None
        ):
            department = await (
                self
                ._department_repository
                .get_by_id(
                    user.department_id
                )
            )

            if (
                department
                is not None
                and department.is_active
            ):
                department_code = (
                    department.code
                )

        roles = await (
            self._role_repository
            .get_by_user_id(
                user.id
            )
        )

        role_codes = {
            role.code.strip().lower()
            for role in roles
            if role.code.strip()
        }

        if not role_codes:
            role_codes = {
                "staff"
            }

        now = datetime.now(
            timezone.utc
        )

        if (
            request.session_id
            is None
        ):
            session = ChatSession(
                id=uuid4(),
                user_id=user.id,
                created_at=now,
                updated_at=now,
            )

            await (
                self._chat_repository
                .add_session(
                    session
                )
            )

            previous_turns = []

        else:
            session = await (
                self._chat_repository
                .get_session(
                    request.session_id
                )
            )

            if session is None:
                raise NotFoundException(
                    "Chat session not found."
                )

            if (
                session.user_id
                != user.id
            ):
                raise ForbiddenException(
                    "Chat session does "
                    "not belong to the "
                    "current user."
                )

            previous_turns = await (
                self._chat_repository
                .list_turns(
                    session.id
                )
            )

            previous_turns = (
                previous_turns[-10:]
            )

            safe_previous_turns: list[
                ChatTurn
            ] = []

            is_admin_user = bool(
                {"admin", "administrator"}
                & role_codes
            )

            for turn in previous_turns:
                allowed = await (
                    citations_are_accessible(
                        citations=list(
                            turn.citations
                        ),
                        department_id=(
                            user.department_id
                            if department_code
                            else None
                        ),
                        document_repository=(
                            self
                            ._document_repository
                        ),
                        document_department_repository=(
                            self
                            ._document_department_repository
                        ),
                        is_admin=is_admin_user,
                    )
                )

                if allowed:
                    safe_previous_turns.append(
                        turn
                    )

            previous_turns = (
                safe_previous_turns
            )

        #
        # D-04 / C-021:
        # lưu session ở PostgreSQL và phân tách rõ giữa
        # retrieval query (cho câu hỏi follow-up) và
        # conversation context (cho generator).
        #
        memory = build_conversation_memory(
            message=message,
            turns=previous_turns,
        )

        rag_result = await (
            self._rag_chat_service
            .answer(
                question=message,
                retrieval_query=(
                    memory.retrieval_query
                ),
                conversation_context=(
                    memory.prompt_context
                ),
                actor=RagChatActor(
                    user_id=user.id,
                    department=(
                        department_code
                    ),
                    roles=(
                        role_codes
                    ),
                ),
            )
        )

        turn = ChatTurn(
            id=uuid4(),
            session_id=(
                session.id
            ),
            question=message,
            answer=(
                rag_result.answer
            ),
            citations=[
                dict(item)
                for item
                in (
                    rag_result
                    .citations
                )
            ],
            created_at=now,
        )

        await (
            self._chat_repository
            .add_turn(
                turn
            )
        )

        if request.session_id is not None:
            session.updated_at = now
            await (
                self._chat_repository
                .update_session(
                    session
                )
            )

        await (
            self._unit_of_work
            .save_changes()
        )

        return AskQuestionResult(
            session_id=(
                session.id
            ),
            turn_id=turn.id,
            answer=(
                rag_result.answer
            ),
            citations=(
                rag_result.citations
            ),
            warnings=(
                rag_result.warnings
            ),
            confidence=(
                rag_result.confidence
            ),
        )