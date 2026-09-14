from typing import Protocol, TypeVar


TRequest = TypeVar("TRequest", contravariant=True)
TResponse = TypeVar("TResponse")


class RequestHandler(Protocol[TRequest, TResponse]):
    async def handle(
        self,
        request: TRequest,
    ) -> TResponse:
        ...