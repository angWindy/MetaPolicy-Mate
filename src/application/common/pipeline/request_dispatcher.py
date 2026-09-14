from typing import Any

from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher as RequestDispatcherProtocol,
)


class RequestDispatcher(RequestDispatcherProtocol):
    def __init__(
        self,
        service_provider: Any,
    ) -> None:
        self._service_provider = service_provider

    async def send(
        self,
        request: Any,
    ) -> Any:
        handler = self._service_provider.get_required_handler(
            type(request)
        )

        return await handler.handle(request)