from typing import Protocol, TypeVar


TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")


class RequestDispatcher(Protocol):
    async def send(
        self,
        request: TRequest,
    ) -> TResponse:
        ...