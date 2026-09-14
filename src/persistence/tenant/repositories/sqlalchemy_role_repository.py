from uuid import UUID

from sqlalchemy import (
    delete,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.role import Role
from src.domain.repositories.role_repository import (
    RoleRepository,
)
from src.persistence.tenant.models.role import (
    RoleModel,
)
from src.persistence.tenant.models.user_role import (
    UserRoleModel,
)


class SqlAlchemyRoleRepository(
    RoleRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        role_id: UUID,
    ) -> Role | None:
        model = await self._session.get(
            RoleModel,
            role_id,
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_by_code(
        self,
        code: str,
    ) -> Role | None:
        result = await self._session.execute(
            select(RoleModel)
            .where(
                RoleModel.code == code
            )
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> list[Role]:
        result = await self._session.execute(
            select(RoleModel)
            .join(
                UserRoleModel,
                UserRoleModel.role_id
                == RoleModel.id,
            )
            .where(
                UserRoleModel.user_id
                == user_id
            )
            .order_by(
                RoleModel.code
            )
        )

        models = result.scalars().all()

        return [
            self._to_domain(model)
            for model in models
        ]

    async def get_all(
        self,
    ) -> list[Role]:
        result = await self._session.execute(
            select(RoleModel)
            .order_by(
                RoleModel.code
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def add(
        self,
        role: Role,
    ) -> None:
        self._session.add(
            RoleModel(
                id=role.id,
                code=role.code,
                name=role.name,
                description=(
                    role.description
                ),
                is_system=role.is_system,
                created_at=role.created_at,
            )
        )

    @staticmethod
    def _to_domain(
        model: RoleModel,
    ) -> Role:
        return Role(
            id=model.id,
            code=model.code,
            name=model.name,
            description=model.description,
            is_system=model.is_system,
            created_at=model.created_at,
        )

    async def update(
        self,
        role: Role,
    ) -> None:
        model = await self._session.get(
            RoleModel,
            role.id,
        )

        if model is None:
            return

        model.name = role.name

        model.description = (
            role.description
        )

    async def replace_for_user(
        self,
        user_id: UUID,
        role_ids: list[UUID],
    ) -> None:
        await self._session.execute(
            delete(
                UserRoleModel
            ).where(
                UserRoleModel.user_id
                == user_id
            )
        )

        if not role_ids:
            return

        self._session.add_all(
            [
                UserRoleModel(
                    user_id=user_id,
                    role_id=role_id,
                )
                for role_id in role_ids
            ]
        )

    async def delete(
        self,
        role_id: UUID,
    ) -> None:
        model = await self._session.get(
            RoleModel,
            role_id,
        )

        if model is None:
            return

        await self._session.delete(model)