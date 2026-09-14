import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from src.domain.audit.audit_actor import AuditActor
from src.domain.audit.audit_context import AuditContext
from src.domain.audit.audit_data import AuditData
from src.domain.audit.audit_event import AuditEvent
from src.domain.enums.audit_action import AuditAction
from src.domain.enums.audit_actor_type import (
    AuditActorType,
)
from src.domain.enums.audit_entity import AuditEntity
from src.persistence.tenant.configurations.audit_log_configuration import (
    audit_logs,
)
from src.persistence.tenant.configurations.audit_outbox_configuration import (
    audit_outbox,
)


class AuditOutboxWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[
            AsyncSession
        ],
    ) -> None:
        self._session_factory = (
            session_factory
        )

    async def execute(
        self,
        stop_event: asyncio.Event,
    ) -> None:
        while not stop_event.is_set():
            try:
                await self._process_batch()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(
                    f"AuditOutboxWorker error: "
                    f"{exc}"
                )

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=5,
                )
            except asyncio.TimeoutError:
                pass

    async def _process_batch(
        self,
    ) -> None:
        async with (
            self._session_factory()
            as session
        ):
            result = await session.execute(
                select(audit_outbox)
                .where(
                    audit_outbox.c.status
                    == "Pending"
                )
                .order_by(
                    audit_outbox.c.created_at
                )
                .limit(10)
            )

            items = (
                result.mappings().all()
            )

            if not items:
                return

            item_ids = [
                item["id"]
                for item in items
            ]

            await session.execute(
                update(audit_outbox)
                .where(
                    audit_outbox.c.id.in_(
                        item_ids
                    )
                )
                .values(
                    status="Processing"
                )
            )

            await session.commit()

        for item in items:
            await self._process_item(
                item
            )

    async def _process_item(
        self,
        item,
    ) -> None:
        async with (
            self._session_factory()
            as session
        ):
            try:
                audit = (
                    self
                    ._deserialize_audit_event(
                        item["payload"]
                    )
                )

                if audit is None:
                    await session.execute(
                        update(
                            audit_outbox
                        )
                        .where(
                            audit_outbox.c.id
                            == item["id"]
                        )
                        .values(
                            status="Failed",
                            error=(
                                "Invalid payload"
                            ),
                        )
                    )

                    await session.commit()
                    return

                await session.execute(
                    insert(
                        audit_logs
                    ).values(
                        id=uuid4(),
                        school_id=(
                            audit.school_id
                        ),
                        actor_id=(
                            audit.actor.id
                        ),
                        actor_type=(
                            audit.actor.type.name
                        ),
                        action=(
                            audit.action.name
                        ),
                        entity=(
                            audit.entity.name
                        ),
                        entity_id=(
                            audit.entity_id
                        ),
                        old_values=(
                            self._serialize(
                                audit.data.before
                            )
                        ),
                        new_values=(
                            self._serialize(
                                audit.data.after
                            )
                        ),
                        metadata=(
                            self._serialize(
                                audit.data.extra
                            )
                        ),
                        ip_address=(
                            audit.context.ip
                        ),
                        device_id=(
                            audit.context.device_id
                        ),
                        user_agent=(
                            audit.context.user_agent
                        ),
                        trace_id=(
                            audit.context.trace_id
                        ),
                        created_at=(
                            audit.occurred_at
                        ),
                    )
                )

                await session.execute(
                    update(
                        audit_outbox
                    )
                    .where(
                        audit_outbox.c.id
                        == item["id"]
                    )
                    .values(
                        status="Processed",
                        processed_at=(
                            datetime.now(
                                timezone.utc
                            )
                        ),
                        error=None,
                    )
                )

                await session.commit()

            except Exception as exc:
                await session.rollback()

                retry_count = (
                    int(
                        item[
                            "retry_count"
                        ]
                    )
                    + 1
                )

                status = (
                    "Failed"
                    if retry_count > 3
                    else "Pending"
                )

                await session.execute(
                    update(
                        audit_outbox
                    )
                    .where(
                        audit_outbox.c.id
                        == item["id"]
                    )
                    .values(
                        status=status,
                        retry_count=(
                            retry_count
                        ),
                        error=str(exc),
                    )
                )

                await session.commit()

    @staticmethod
    def _serialize(
        value: object | None,
    ) -> str | None:
        if value is None:
            return None

        return json.dumps(
            value,
            default=str,
            separators=(",", ":"),
        )

    @staticmethod
    def _deserialize_audit_event(
        payload: str,
    ) -> AuditEvent | None:
        try:
            data = json.loads(
                payload
            )

            actor_data = (
                data.get("actor")
                or {}
            )

            context_data = (
                data.get("context")
                or {}
            )

            audit_data = (
                data.get("data")
                or {}
            )

            return AuditEvent(
                event_id=UUID(
                    data["event_id"]
                ),
                school_id=(
                    UUID(
                        data[
                            "school_id"
                        ]
                    )
                    if data.get(
                        "school_id"
                    )
                    else None
                ),
                action=AuditAction(
                    data["action"]
                ),
                entity=AuditEntity(
                    data["entity"]
                ),
                entity_id=(
                    UUID(
                        data[
                            "entity_id"
                        ]
                    )
                    if data.get(
                        "entity_id"
                    )
                    else None
                ),
                actor=AuditActor(
                    id=(
                        UUID(
                            actor_data[
                                "id"
                            ]
                        )
                        if actor_data.get(
                            "id"
                        )
                        else None
                    ),
                    type=AuditActorType(
                        actor_data.get(
                            "type",
                            (
                                AuditActorType
                                .SYSTEM.value
                            ),
                        )
                    ),
                ),
                context=AuditContext(
                    ip=context_data.get(
                        "ip"
                    ),
                    user_agent=(
                        context_data.get(
                            "user_agent"
                        )
                    ),
                    device_id=(
                        context_data.get(
                            "device_id"
                        )
                    ),
                    trace_id=(
                        context_data.get(
                            "trace_id"
                        )
                    ),
                ),
                data=AuditData(
                    before=(
                        audit_data.get(
                            "before"
                        )
                    ),
                    after=(
                        audit_data.get(
                            "after"
                        )
                    ),
                    extra=(
                        audit_data.get(
                            "extra"
                        )
                    ),
                ),
                occurred_at=(
                    datetime
                    .fromisoformat(
                        data[
                            "occurred_at"
                        ]
                    )
                ),
            )

        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None