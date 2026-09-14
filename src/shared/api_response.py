from typing import Any, Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    status: int
    message: str
    data: T | None = None
    error: str | None = None
    validation_errors: Any | None = None

    @classmethod
    def success(
        cls,
        data: T | None = None,
        message: str = "Success",
    ) -> "ApiResponse[T]":
        return cls(
            status=1,
            message=message,
            data=data,
        )

    @classmethod
    def fail(
        cls,
        message: str,
        error: str | None = None,
        validation_errors: Any | None = None,
    ) -> "ApiResponse[Any]":
        return cls(
            status=0,
            message=message,
            error=error,
            validation_errors=validation_errors,
        )