import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.document_changelog_entry import (
    DocumentChangelogEntry,
)
from src.domain.repositories.document_changelog_repository import (
    DocumentChangelogRepository,
)
from src.persistence.tenant.configurations.audit_log_configuration import (
    audit_logs,
)


class SqlAlchemyDocumentChangelogRepository(
    DocumentChangelogRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_document_id(
        self,
        document_id: UUID,
        action: str | None,
        from_at: datetime | None,
        to_at: datetime | None,
        skip: int,
        limit: int,
    ) -> list[
        DocumentChangelogEntry
    ]:
        statement = (
            select(
                audit_logs
            )
            .where(
                audit_logs.c.entity_id
                == document_id
            )
            .where(
                audit_logs.c.entity
                == "REGULATORY_DOCUMENT"
            )
        )

        if action is not None:
            statement = statement.where(
                audit_logs.c.action
                == action.upper()
            )

        if from_at is not None:
            statement = statement.where(
                audit_logs.c.created_at
                >= from_at
            )

        if to_at is not None:
            statement = statement.where(
                audit_logs.c.created_at
                <= to_at
            )

        statement = (
            statement
            .order_by(
                audit_logs.c.created_at
                .desc()
            )
            .offset(skip)
            .limit(limit)
        )

        result = await self._session.execute(
            statement
        )

        return [
            self._to_domain(row)
            for row
            in result.mappings().all()
        ]

    async def count_by_document_id(
        self,
        document_id: UUID,
        action: str | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> int:
        statement = (
            select(
                func.count(
                    audit_logs.c.id
                )
            )
            .where(
                audit_logs.c.entity_id
                == document_id
            )
            .where(
                audit_logs.c.entity
                == "REGULATORY_DOCUMENT"
            )
        )

        if action is not None:
            statement = statement.where(
                audit_logs.c.action
                == action.upper()
            )

        if from_at is not None:
            statement = statement.where(
                audit_logs.c.created_at
                >= from_at
            )

        if to_at is not None:
            statement = statement.where(
                audit_logs.c.created_at
                <= to_at
            )

        result = await self._session.execute(
            statement
        )

        return int(
            result.scalar_one()
        )

    async def get_by_id(
        self,
        document_id: UUID,
        changelog_id: UUID,
    ) -> (
        DocumentChangelogEntry
        | None
    ):
        result = await self._session.execute(
            select(
                audit_logs
            )
            .where(
                audit_logs.c.id
                == changelog_id
            )
            .where(
                audit_logs.c.entity_id
                == document_id
            )
            .where(
                audit_logs.c.entity
                == "REGULATORY_DOCUMENT"
            )
            .limit(1)
        )

        row = (
            result
            .mappings()
            .one_or_none()
        )

        if row is None:
            return None

        return self._to_domain(
            row
        )

    @staticmethod
    def _deserialize(
        value: Any | None,
    ) -> Any | None:
        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            return value

        try:
            return json.loads(
                value
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return value

    @classmethod
    def _to_domain(
        cls,
        row,
    ) -> DocumentChangelogEntry:
        return DocumentChangelogEntry(
            id=row["id"],

            document_id=(
                row["entity_id"]
            ),

            action=row["action"],

            actor_id=(
                row["actor_id"]
            ),

            actor_type=(
                row["actor_type"]
            ),

            old_values=(
                cls._deserialize(
                    row["old_values"]
                )
            ),

            new_values=(
                cls._deserialize(
                    row["new_values"]
                )
            ),

            metadata=(
                cls._deserialize(
                    row["metadata"]
                )
            ),

            ip_address=(
                row["ip_address"]
            ),

            device_id=(
                row["device_id"]
            ),

            user_agent=(
                row["user_agent"]
            ),

            created_at=(
                row["created_at"]
            ),
        )