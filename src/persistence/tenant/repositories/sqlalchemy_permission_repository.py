from sqlalchemy import (
    delete,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.permission import Permission
from src.domain.repositories.permission_repository import (
    PermissionRepository,
)
from src.persistence.tenant.models.permission import (
    PermissionModel,
)

from uuid import UUID

from src.persistence.tenant.models.role_permission import (
    RolePermissionModel,
)
from src.persistence.tenant.models.user_role import (
    UserRoleModel,
)

class SqlAlchemyPermissionRepository(
    PermissionRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        permission_id,
    ) -> Permission | None:
        model = await self._session.get(
            PermissionModel,
            permission_id,
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_by_code(
        self,
        code: str,
    ) -> Permission | None:
        result = await self._session.execute(
            select(PermissionModel).where(
                PermissionModel.code == code
            )
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_domain(model)

    async def get_all(
        self,
    ) -> list[Permission]:
        result = await self._session.execute(
            select(PermissionModel).order_by(
                PermissionModel.code
            )
        )

        return [
            self._to_domain(model)
            for model in result.scalars().all()
        ]

    async def add(
        self,
        permission: Permission,
    ) -> None:
        self._session.add(
            PermissionModel(
                id=permission.id,
                code=permission.code,
                name=permission.name,
                module=permission.module,
                description=permission.description,
            )
        )

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> list[Permission]:
        result = await self._session.execute(
            select(PermissionModel)
            .join(
                RolePermissionModel,
                RolePermissionModel.permission_id
                == PermissionModel.id,
            )
            .join(
                UserRoleModel,
                UserRoleModel.role_id
                == RolePermissionModel.role_id,
            )
            .where(
                UserRoleModel.user_id
                == user_id
            )
            .distinct()
            .order_by(
                PermissionModel.code
            )
        )

        return [
            self._to_domain(model)
            for model in result.scalars().all()
        ]

    @staticmethod
    def _to_domain(
        model: PermissionModel,
    ) -> Permission:
        return Permission(
            id=model.id,
            code=model.code,
            name=model.name,
            module=model.module,
            description=model.description,
        )

    async def get_by_role_id(
        self,
        role_id: UUID,
    ) -> list[Permission]:
        result = await self._session.execute(
            select(
                PermissionModel
            )
            .join(
                RolePermissionModel,
                (
                    RolePermissionModel
                    .permission_id
                    == PermissionModel.id
                ),
            )
            .where(
                RolePermissionModel.role_id
                == role_id
            )
            .order_by(
                PermissionModel.code
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def replace_for_role(
        self,
        role_id: UUID,
        permission_ids: list[UUID],
    ) -> None:
        await self._session.execute(
            delete(
                RolePermissionModel
            ).where(
                RolePermissionModel.role_id
                == role_id
            )
        )

        if not permission_ids:
            return

        self._session.add_all(
            [
                RolePermissionModel(
                    role_id=role_id,
                    permission_id=(
                        permission_id
                    ),
                )
                for permission_id
                in permission_ids
            ]
        )