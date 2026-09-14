from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.chat_session import ChatSession
from src.domain.entities.chat_turn import ChatTurn
from src.domain.repositories.chat_repository import (
    ChatRepository,
)
from src.persistence.tenant.models.chat_session import (
    ChatSessionModel,
)
from src.persistence.tenant.models.chat_turn import (
    ChatTurnModel,
)


class SqlAlchemyChatRepository(
    ChatRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_session(
        self,
        session_id: UUID,
    ) -> ChatSession | None:
        model = await self._session.get(
            ChatSessionModel,
            session_id,
        )

        if model is None:
            return None

        return self._session_to_domain(
            model
        )

    async def list_sessions(
        self,
        user_id: UUID,
    ) -> list[ChatSession]:
        result = await self._session.execute(
            select(ChatSessionModel)
            .where(ChatSessionModel.user_id == user_id)
            .order_by(ChatSessionModel.updated_at.desc())
        )

        return [
            self._session_to_domain(model)
            for model in result.scalars().all()
        ]

    async def add_session(
        self,
        session: ChatSession,
    ) -> None:
        self._session.add(
            ChatSessionModel(
                id=session.id,
                user_id=session.user_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
        )

    async def update_session(
        self,
        session: ChatSession,
    ) -> None:
        model = await self._session.get(
            ChatSessionModel,
            session.id,
        )

        if model is None:
            return

        model.updated_at = (
            session.updated_at
        )

    async def delete_session(
        self,
        session_id: UUID,
    ) -> None:
        # Delete turns first (foreign key constraint)
        await self._session.execute(
            delete(ChatTurnModel).where(
                ChatTurnModel.session_id == session_id
            )
        )
        # Delete session
        await self._session.execute(
            delete(ChatSessionModel).where(
                ChatSessionModel.id == session_id
            )
        )

    async def list_turns(
        self,
        session_id: UUID,
    ) -> list[ChatTurn]:
        result = await self._session.execute(
            select(
                ChatTurnModel
            )
            .where(
                ChatTurnModel.session_id
                == session_id
            )
            .order_by(
                ChatTurnModel.created_at.asc()
            )
        )

        return [
            self._turn_to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def add_turn(
        self,
        turn: ChatTurn,
    ) -> None:
        self._session.add(
            ChatTurnModel(
                id=turn.id,
                session_id=turn.session_id,
                question=turn.question,
                answer=turn.answer,
                citations=list(
                    turn.citations
                ),
                created_at=turn.created_at,
            )
        )

    @staticmethod
    def _session_to_domain(
        model: ChatSessionModel,
    ) -> ChatSession:
        return ChatSession(
            id=model.id,
            user_id=model.user_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _turn_to_domain(
        model: ChatTurnModel,
    ) -> ChatTurn:
        return ChatTurn(
            id=model.id,
            session_id=model.session_id,
            question=model.question,
            answer=model.answer,
            citations=list(
                model.citations or []
            ),
            created_at=model.created_at,
        )

    async def get_turn(
        self,
        turn_id: UUID,
    ) -> ChatTurn | None:
        model = await self._session.get(
            ChatTurnModel,
            turn_id,
        )

        if model is None:
            return None

        return self._turn_to_domain(
            model
        )


    async def count_turns(
        self,
    ) -> int:
        result = await self._session.execute(
            select(
                func.count(
                    ChatTurnModel.id
                )
            )
        )

        return int(
            result.scalar_one()
        )

    async def count_turns_in_session(
        self,
        session_id: UUID,
    ) -> int:
        result = await self._session.execute(
            select(
                func.count(ChatTurnModel.id)
            ).where(
                ChatTurnModel.session_id == session_id
            )
        )
        return int(result.scalar_one())