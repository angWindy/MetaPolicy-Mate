from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.refresh_token import RefreshToken
from src.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.persistence.tenant.models.refresh_token import (
    RefreshTokenModel,
)


class SqlAlchemyRefreshTokenRepository(
    RefreshTokenRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        refresh_token_id: UUID,
    ) -> RefreshToken | None:
        model = await self._session.get(
            RefreshTokenModel,
            refresh_token_id,
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_by_hash(
        self,
        token_hash: str,
    ) -> RefreshToken | None:
        result = await self._session.execute(
            select(
                RefreshTokenModel
            ).where(
                RefreshTokenModel.token_hash
                == token_hash
            )
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_domain(model)

    async def get_by_hash_for_update(
        self,
        token_hash: str,
    ) -> RefreshToken | None:
        statement = (
            select(
                RefreshTokenModel
            )
            .where(
                RefreshTokenModel.token_hash
                == token_hash
            )
            .with_for_update()
        )

        result = await (
            self._session.execute(
                statement
            )
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def add(
        self,
        refresh_token: RefreshToken,
    ) -> None:
        self._session.add(
            RefreshTokenModel(
                id=refresh_token.id,
                user_id=refresh_token.user_id,
                token_hash=refresh_token.token_hash,
                device_id=refresh_token.device_id,
                expires_at=refresh_token.expires_at,
                revoked_at=refresh_token.revoked_at,
                replaced_by_token_id=(
                    refresh_token
                    .replaced_by_token_id
                ),
                created_at=refresh_token.created_at,
            )
        )

    async def update(
        self,
        refresh_token: RefreshToken,
    ) -> None:
        model = await self._session.get(
            RefreshTokenModel,
            refresh_token.id,
        )

        if model is None:
            return

        model.device_id = (
            refresh_token.device_id
        )

        model.expires_at = (
            refresh_token.expires_at
        )

        model.revoked_at = (
            refresh_token.revoked_at
        )

        model.replaced_by_token_id = (
            refresh_token
            .replaced_by_token_id
        )

    async def revoke_all_by_user_id(
        self,
        user_id: UUID,
    ) -> None:
        now = datetime.now(
            timezone.utc
        )

        await self._session.execute(
            update(
                RefreshTokenModel
            )
            .where(
                RefreshTokenModel.user_id
                == user_id
            )
            .where(
                RefreshTokenModel.revoked_at
                .is_(None)
            )
            .values(
                revoked_at=now
            )
        )

    @staticmethod
    def _to_domain(
        model: RefreshTokenModel,
    ) -> RefreshToken:
        return RefreshToken(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            device_id=model.device_id,
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
            replaced_by_token_id=(
                model.replaced_by_token_id
            ),
            created_at=model.created_at,
        )