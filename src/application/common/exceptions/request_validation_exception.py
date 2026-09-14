from collections.abc import Iterable

from src.shared.validation_error import ValidationError


class RequestValidationException(Exception):
    def __init__(
        self,
        errors: Iterable[ValidationError],
    ) -> None:
        super().__init__("Validation failed")
        self.errors: tuple[ValidationError, ...] = tuple(errors)