from typing import Generic, Iterable, TypeVar

from src.application.common.exceptions.request_validation_exception import (
    RequestValidationException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.common.validation.interfaces.request_validator import (
    RequestValidator,
)


TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")


class ValidationHandlerDecorator(
    Generic[TRequest, TResponse],
):
    def __init__(
        self,
        inner: RequestHandler[TRequest, TResponse],
        validators: Iterable[RequestValidator[TRequest]],
    ) -> None:
        self._inner = inner
        self._validators = validators

    async def handle(
        self,
        request: TRequest,
    ) -> TResponse:
        failures = [
            failure
            for validator in self._validators
            for failure in validator.validate(request)
        ]

        if failures:
            raise RequestValidationException(failures)

        return await self._inner.handle(request)