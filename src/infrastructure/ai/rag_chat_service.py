from src.application.common.interfaces.hybrid_retrieval_service import (
    HybridRetrievalActor,
    HybridRetrievalService,
)
from src.application.common.interfaces.rag_chat_service import (
    RagChatActor,
    RagChatResult,
)
from src.config import Settings
from src.domain.schemas import (
    ClassificationLevel,
    RetrievedChunk,
    UserContext,
)
from src.infrastructure.ai.rag_runtime import (
    get_p234_rag_runtime,
)
from src.rag.workflow import (
    RetrievalWorkflow,
)


class AiRagChatService:
    def __init__(
        self,
        settings: Settings,
        hybrid_retrieval_service: HybridRetrievalService,
    ) -> None:
        self._settings = settings
        self._hybrid_retrieval_service = (
            hybrid_retrieval_service
        )

    async def answer(
        self,
        *,
        question: str,
        retrieval_query: str,
        actor: RagChatActor,
        conversation_context: str = "",
    ) -> RagChatResult:
        runtime = (
            get_p234_rag_runtime()
        )

        user_context = UserContext(
            user_id=str(
                actor.user_id
            ),

            # AI cũ yêu cầu tenant_id.
            #
            # P-234 hiện đã chuyển sang
            # RBAC identity dựa trên
            # ``user.department_id`` /
            # ``department.code``. Tenant
            # identity cho RAG namespace
            # được lấy từ ``actor.department``
            # (mã trường của user hiện
            # đang đăng nhập). Trước đây
            # giá trị này đọc từ
            # ``settings.school_code`` — biến
            # đã được gỡ vì hard-code.
            tenant_id=(
                actor.department
                .strip()
                .lower()
                or "public"
            ),

            department=(
                actor.department
                .strip()
                .upper()
                or "PUBLIC"
            ),

            roles={
                role.strip().lower()
                for role in actor.roles
                if role.strip()
            }
            or {"staff"},

            clearance_level=(
                ClassificationLevel(
                    self._settings
                    .rag_default_clearance
                )
            ),
        )

        async def retrieve_fn(
            query: str,
            user: UserContext,
            as_of_date,
            *,
            embed_text: (
                str | None
            ) = None,
        ):
            # Authorization thực tế của P-234
            # không giao cho AI cũ.
            #
            # HybridRetrievalService của BE
            # đã filter:
            #
            # - legal status
            # - document version
            # - PUBLIC / DEPARTMENT
            # - department hiện hành
            #
            # trước khi candidate được đưa
            # vào AI workflow.
            del user

            items = await (
                self
                ._hybrid_retrieval_service
                .search(
                    query=query,

                    actor=(
                        HybridRetrievalActor(
                            user_id=(
                                actor.user_id
                            ),

                            department=(
                                actor.department
                            ),

                            roles=(
                                actor.roles
                            ),
                        )
                    ),

                    as_of_date=(
                        as_of_date
                    ),

                    embed_text=(
                        embed_text
                    ),
                )
            )

            return [
                RetrievedChunk(
                    chunk_id=(
                        item.chunk_id
                    ),

                    text=item.text,

                    score=item.score,

                    source=item.source,

                    metadata=dict(
                        item.metadata
                        or {}
                    ),
                )
                for item in items
            ]

        # Không sửa RetrievalWorkflow.
        #
        # BE chỉ adapter dữ liệu vào AI cũ.
        workflow = RetrievalWorkflow(
            settings=(
                runtime.settings
            ),

            retrieve_fn=(
                retrieve_fn
            ),

            reranker_service=(
                runtime
                .reranker_service
            ),

            generator=(
                runtime.generator
            ),

            hyde_llm=(
                runtime.hyde_llm
            ),
        )

        state = await (
            workflow.ainvoke(
                {
                    # Question hiện tại.
                    "original_query": (
                        question
                    ),

                    # D-04:
                    # retrieval_query có thể
                    # chứa session history.
                    "query": (
                        retrieval_query
                    ),

                    "conversation_context": (
                        conversation_context
                    ),

                    "user": (
                        user_context
                    ),

                    # Chat mặc định hỏi dữ liệu
                    # hiện hành.
                    "as_of_date": None,

                    # Đây mới đúng là settings
                    # nội bộ của AI workflow.
                    "settings": (
                        runtime.settings
                    ),
                }
            )
        )

        citations: list[
            dict
        ] = []

        for citation in (
            state.get(
                "citations"
            )
            or []
        ):
            if hasattr(
                citation,
                "model_dump",
            ):
                citations.append(
                    citation.model_dump(
                        mode="json"
                    )
                )

            elif isinstance(
                citation,
                dict,
            ):
                citations.append(
                    dict(citation)
                )

        return RagChatResult(
            answer=str(
                state.get(
                    "answer"
                )
                or (
                    "Tôi chưa có đủ "
                    "căn cứ để kết luận."
                )
            ),

            citations=citations,

            warnings=[
                str(item)
                for item
                in (
                    state.get(
                        "warnings"
                    )
                    or []
                )
            ],

            confidence=str(
                state.get(
                    "confidence"
                )
                or "low"
            ),
        )
