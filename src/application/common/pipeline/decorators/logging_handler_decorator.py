import logging

from datetime import (
    datetime,
    timezone,
)
from typing import (
    Generic,
    TypeVar,
)

from src.application.common.interfaces.activity_log_service import (
    ActivityLogService,
)
from src.application.common.interfaces.request_context import (
    RequestContext,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)


TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")


class LoggingHandlerDecorator(
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
        inner: RequestHandler[
            TRequest,
            TResponse,
        ],
        logger: logging.Logger,
        activity_log_service: ActivityLogService,
        request_context: RequestContext | None,
    ) -> None:
        self._inner = inner
        self._logger = logger
        self._activity_log_service = (
            activity_log_service
        )
        self._request_context = (
            request_context
        )

    async def handle(
        self,
        request,
    ):
        request_name = (
            type(request).__name__
        )

        started_at = datetime.now(
            timezone.utc
        )

        self._logger.info(
            "Handling %s",
            request_name,
        )

        try:
            response = await (
                self._inner.handle(
                    request
                )   
            )

        except Exception as exc:
            completed_at = datetime.now(
                timezone.utc
            )

            self._logger.exception(
                "Failed handling %s",
                request_name,
            )

            try:
                await (
                    self._activity_log_service
                    .write(
                        request_name=(
                            request_name
                        ),
                        status="Failed",
                        started_at=(
                            started_at
                        ),
                        completed_at=(
                            completed_at
                        ),
                        request_context=(
                            self
                            ._request_context
                        ),
                        error_message=(
                            str(exc)
                        ),
                    )
                )

            except Exception:
                # Không được dùng lỗi logging
                # để che mất exception business.
                self._logger.exception(
                    "Failed writing activity "
                    "log for %s",
                    request_name,
                )

            raise

        completed_at = datetime.now(
            timezone.utc
        )

        try:
            await (
                self._activity_log_service
                .write(
                    request_name=request_name,
                    status="Succeeded",
                    started_at=started_at,
                    completed_at=(
                        completed_at
                    ),
                    request_context=(
                        self._request_context
                    ),
                    error_message=None,
                )
            )

        except Exception:
            # Business đã thành công.
            # Logging phụ không được đổi
            # response thành 500.
            self._logger.exception(
                "Failed writing activity "
                "log for %s",
                request_name,
            )

        self._logger.info(
            "Finished request %s",
            request_name,
        )

        return response