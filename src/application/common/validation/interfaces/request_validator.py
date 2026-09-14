from typing import Protocol, TypeVar

from src.shared.validation_error import ValidationError


TRequest = TypeVar("TRequest", contravariant=True)


class RequestValidator(Protocol[TRequest]):
    def validate(
        self,
        request: TRequest,
    ) -> list[ValidationError]:
        ...