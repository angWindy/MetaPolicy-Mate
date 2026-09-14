import logging

from typing import (
    Generic,
    TypeVar,
)

from src.application.common.audit.auditable_request import (
    AuditableRequest,
)
from src.application.common.interfaces.audit_service import (
    AuditService,
)
from src.application.common.interfaces.request_context import (
    RequestContext,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.domain.audit.audit_actor import (
    AuditActor,
)
from src.domain.audit.audit_context import (
    AuditContext,
)
from src.domain.audit.audit_data import (
    AuditData,
)
from src.domain.audit.audit_event import (
    AuditEvent,
)


TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")

_logger = logging.getLogger(
    __name__
)


class AuditHandlerDecorator(
    RequestHandler[
        TRequest,
        TResponse,
    ],
    Generic[
        TRequest,
        TResponse,
    ],
):
    def __init__(
        self,
        next_handler: RequestHandler[
            TRequest,
            TResponse,
        ],
        audit_service: AuditService,
        context: RequestContext,
    ) -> None:
        self._next = next_handler
        self._audit_service = (
            audit_service
        )
        self._context = context

    async def handle(
        self,
        request: TRequest,
    ) -> TResponse:
        response = await (
            self._next.handle(request)
        )

        try:
            await self._try_audit(
                request=request,
                response=response,
            )

        except Exception:
            # Business đã hoàn tất và đã
            # commit trong handler.
            #
            # Audit phụ không được đổi
            # response thành 500.
            _logger.exception(
                "Failed writing audit event "
                "for request %s",
                type(request).__name__,
            )

        return response

    async def _try_audit(
        self,
        request: TRequest,
        response: TResponse,
    ) -> None:
        if not isinstance(
            request,
            AuditableRequest,
        ):
            return

        get_payload = getattr(
            request,
            "get_payload",
            None,
        )

        audit_after = (
            get_payload()
            if callable(get_payload)
            else request
        )

        get_audit_before = getattr(
            request,
            "get_audit_before",
            None,
        )

        audit_before = (
            get_audit_before()
            if callable(
                get_audit_before
            )
            else None
        )

        entity_id = (
            self._resolve_entity_id(
                request=request,
                response=response,
            )
        )

        await self._audit_service.emit(
            AuditEvent(
                school_id=(
                    self._context.school_id
                ),

                action=request.action,
                entity=request.entity,
                entity_id=entity_id,

                actor=AuditActor(
                    id=self._context.user_id,
                    type=(
                        self._context
                        .user_type
                    ),
                ),

                context=AuditContext(
                    ip=(
                        self._context
                        .ip_address
                    ),

                    user_agent=(
                        self._context
                        .user_agent
                    ),

                    device_id=(
                        self._context
                        .device_id
                    ),

                    trace_id=(
                        self._context
                        .trace_id
                    ),
                ),

                data=AuditData(
                    before=audit_before,
                    after=audit_after,
                ),
            )
        )

    @staticmethod
    def _resolve_entity_id(
        request: TRequest,
        response: TResponse,
    ):
        get_audit_entity_id = getattr(
            request,
            "get_audit_entity_id",
            None,
        )

        if callable(
            get_audit_entity_id
        ):
            resolved_id = (
                get_audit_entity_id(
                    response
                )
            )

            if resolved_id is not None:
                return resolved_id

        entity_id = request.entity_id

        if entity_id is not None:
            return entity_id

        return getattr(
            response,
            "id",
            None,
        )