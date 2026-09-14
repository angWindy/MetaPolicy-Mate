from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.user import User
from src.domain.repositories.user_repository import (
    UserRepository,
)
from src.persistence.tenant.models.department import (
    DepartmentModel,
)
from src.persistence.tenant.models.user import (
    UserModel,
)


class SqlAlchemyUserRepository(
    UserRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        user_id,
    ) -> User | None:
        model = await self._session.get(
            UserModel,
            user_id,
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        result = await self._session.execute(
            select(
                UserModel
            ).where(
                func.lower(
                    UserModel.email
                )
                == email.lower()
            )
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_list(
        self,
        search: str | None,
        is_active: bool | None,
        skip: int,
        limit: int,
    ) -> list[User]:
        statement = (
            select(UserModel)
            .outerjoin(
                DepartmentModel,
                DepartmentModel.id
                == UserModel.department_id,
            )
        )

        if search:
            keyword = (
                f"%{search.strip()}%"
            )

            statement = (
                statement.where(
                    or_(
                        UserModel.email
                        .ilike(keyword),

                        UserModel.full_name
                        .ilike(keyword),

                        DepartmentModel.name
                        .ilike(keyword),

                        DepartmentModel.code
                        .ilike(keyword),
                    )
                )
            )

        if is_active is not None:
            statement = statement.where(
                UserModel.is_active
                == is_active
            )

        statement = (
            statement
            .order_by(
                UserModel.created_at.desc()
            )
            .offset(skip)
            .limit(limit)
        )

        result = await self._session.execute(
            statement
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def count(
        self,
        search: str | None,
        is_active: bool | None,
    ) -> int:
        statement = (
            select(
                func.count(
                    UserModel.id
                )
            )
            .select_from(UserModel)
            .outerjoin(
                DepartmentModel,
                DepartmentModel.id
                == UserModel.department_id,
            )
        )

        if search:
            keyword = (
                f"%{search.strip()}%"
            )

            statement = (
                statement.where(
                    or_(
                        UserModel.email
                        .ilike(keyword),

                        UserModel.full_name
                        .ilike(keyword),

                        DepartmentModel.name
                        .ilike(keyword),

                        DepartmentModel.code
                        .ilike(keyword),
                    )
                )
            )

        if is_active is not None:
            statement = statement.where(
                UserModel.is_active
                == is_active
            )

        result = await self._session.execute(
            statement
        )

        return int(
            result.scalar_one()
        )

    async def add(
        self,
        user: User,
    ) -> None:
        self._session.add(
            UserModel(
                id=user.id,
                email=user.email,
                password_hash=(
                    user.password_hash
                ),
                full_name=(
                    user.full_name
                ),
                department_id=(
                    user.department_id
                ),
                token_version=(
                    user.token_version
                ),
                is_active=(
                    user.is_active
                ),
                created_at=(
                    user.created_at
                ),
                updated_at=(
                    user.updated_at
                ),
            )
        )

    async def update(
        self,
        user: User,
    ) -> None:
        model = await self._session.get(
            UserModel,
            user.id,
        )

        if model is None:
            return

        model.email = user.email
        model.password_hash = (
            user.password_hash
        )
        model.full_name = (
            user.full_name
        )
        model.department_id = (
            user.department_id
        )
        model.token_version = (
            user.token_version
        )
        model.is_active = (
            user.is_active
        )
        model.updated_at = (
            user.updated_at
        )

    async def delete(
        self,
        user_id,
    ) -> None:
        model = await self._session.get(
            UserModel,
            user_id,
        )

        if model is None:
            return

        await self._session.delete(model)

    @staticmethod
    def _to_domain(
        model: UserModel,
    ) -> User:
        return User(
            id=model.id,
            email=model.email,
            password_hash=(
                model.password_hash
            ),
            full_name=(
                model.full_name
            ),
            department_id=(
                model.department_id
            ),
            is_admin=bool(
                model.is_admin
            ),
            token_version=(
                model.token_version
            ),
            is_active=(
                model.is_active
            ),
            created_at=(
                model.created_at
            ),
            updated_at=(
                model.updated_at
            ),
        )