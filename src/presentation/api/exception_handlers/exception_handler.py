import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from src.application.common.exceptions.forbidden_exception import (
    ForbiddenException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.exceptions.request_validation_exception import (
    RequestValidationException,
)
from src.application.common.exceptions.unauthorized_exception import (
    UnauthorizedException,
)
from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.too_many_requests_exception import (
    TooManyRequestsException,
)
from src.shared.api_response import ApiResponse


logger = logging.getLogger(__name__)


async def exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error(
        "Unhandled exception",
        exc_info=exc,
    )

    if isinstance(
        exc,
        RequestValidationException,
    ):
        response = ApiResponse.fail(
            message="Validation failed",
            validation_errors=(
                exc.errors
            ),
        )

        status_code = 400

    elif isinstance(
        exc,
        TooManyRequestsException,
    ):
        return JSONResponse(
            status_code=429,
            content={
                "message": str(
                    exc
                ),
                "retry_after_seconds": (
                    exc
                    .retry_after_seconds
                ),
            },
            headers={
                "Retry-After": str(
                    exc
                    .retry_after_seconds
                ),
            },
        )

    elif isinstance(
        exc,
        ConflictException,
    ):
        response = ApiResponse.fail(
            message=str(exc),
        )

        status_code = 409

    elif isinstance(
        exc,
        NotFoundException,
    ):
        response = ApiResponse.fail(
            message=str(exc),
        )

        status_code = 404

    elif isinstance(
        exc,
        UnauthorizedException,
    ):
        response = ApiResponse.fail(
            message=str(exc),
        )

        status_code = 401

    elif isinstance(
        exc,
        ForbiddenException,
    ):
        response = ApiResponse.fail(
            message=str(exc),
        )

        status_code = 403

    else:
        # Chi tiết exception thật chỉ
        # được ghi vào server log phía trên.
        # Không trả str(exc) cho client.
        response = ApiResponse.fail(
            message=(
                "Internal server error"
            ),
        )

        status_code = 500

    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(
            mode="json"
        ),
    )