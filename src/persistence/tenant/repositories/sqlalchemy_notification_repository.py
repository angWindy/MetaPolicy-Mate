from uuid import UUID

from sqlalchemy import (
    func,
    select,
    update,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.notification import (
    Notification,
)
from src.domain.repositories.notification_repository import (
    NotificationRepository,
)
from src.domain.schemas import NotificationType
from src.persistence.tenant.models.notification import (
    NotificationModel,
)


class SqlAlchemyNotificationRepository(
    NotificationRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def add(
        self,
        notification: Notification,
    ) -> None:
        self._session.add(
            NotificationModel(
                id=notification.id,
                user_id=notification.user_id,
                type=notification.type.value,
                title=notification.title,
                body=notification.body,
                related_document_id=(
                    notification.related_document_id
                ),
                is_read=notification.is_read,
                created_at=notification.created_at,
            )
        )

    async def list_by_user(
        self,
        *,
        user_id: UUID,
        unread_only: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Notification], int]:
        offset = (page - 1) * page_size
        where_clauses = [
            NotificationModel.user_id == user_id
        ]
        if unread_only:
            where_clauses.append(
                NotificationModel.is_read == False  # noqa: E712
            )

        total_result = await self._session.execute(
            select(func.count(NotificationModel.id)).where(
                *where_clauses
            )
        )
        total = int(total_result.scalar_one())

        result = await self._session.execute(
            select(NotificationModel)
            .where(*where_clauses)
            .order_by(NotificationModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = [
            self._to_domain(m) for m in result.scalars().all()
        ]
        return items, total

    async def get_by_id(
        self,
        notification_id: UUID,
        user_id: UUID,
    ) -> Notification | None:
        result = await self._session.execute(
            select(NotificationModel).where(
                NotificationModel.id == notification_id,
                NotificationModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def mark_read(
        self,
        notification_id: UUID,
        user_id: UUID,
    ) -> bool:
        result = await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.id == notification_id,
                NotificationModel.user_id == user_id,
                NotificationModel.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        return result.rowcount > 0

    async def mark_all_read(
        self,
        user_id: UUID,
    ) -> int:
        result = await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.is_read == False,  # noqa: E712
            )
            .values(is_read=True)
        )
        return result.rowcount

    async def count_unread(
        self,
        user_id: UUID,
    ) -> int:
        result = await self._session.execute(
            select(func.count(NotificationModel.id)).where(
                NotificationModel.user_id == user_id,
                NotificationModel.is_read == False,  # noqa: E712
            )
        )
        return int(result.scalar_one())

    @staticmethod
    def _to_domain(
        model: NotificationModel,
    ) -> Notification:
        return Notification(
            id=model.id,
            user_id=model.user_id,
            type=NotificationType(model.type),
            title=model.title,
            body=model.body,
            related_document_id=model.related_document_id,
            is_read=model.is_read,
            created_at=model.created_at,
        )
