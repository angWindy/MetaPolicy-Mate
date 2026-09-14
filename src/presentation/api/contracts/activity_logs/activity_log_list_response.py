from pydantic import BaseModel

from src.presentation.api.contracts.activity_logs.activity_log_response import (
    ActivityLogResponse,
)


class ActivityLogListResponse(
    BaseModel
):
    items: list[
        ActivityLogResponse
    ]

    total: int

    page: int
    page_size: int