from datetime import datetime
from typing import Protocol

from src.application.common.interfaces.request_context import (
    RequestContext,
)


class ActivityLogService(
    Protocol
):
    async def write(
        self,
        request_name: str,
        status: str,
        started_at: datetime,
        completed_at: datetime,
        request_context: (
            RequestContext | None
        ) = None,
        error_message: str | None = None,
    ) -> None:
        ...